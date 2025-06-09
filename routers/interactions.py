"""
Router for Content Interactions (Comments and Ratings).
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import Integer, func, and_, select

from db_config import get_async_db
from core.security import get_current_user
from models.models import (
    User, ContentComment, ContentRating, ContentTypeEnum, 
    RatingValueEnum, Summary, McqQuiz, PhysicalFile
)
from schemas.comment import (
    ContentCommentCreate, ContentCommentRead, ContentCommentUpdate,
    CommentThreadResponse, CommentCreateResponse
)
from schemas.rating import (
    ContentRatingCreate, ContentRatingRead, ContentRatingUpdate,
    ContentRatingStats, RatingCreateResponse
)
from services.notification_service import NotificationService

router = APIRouter(prefix="/interactions", tags=["Content Interactions"])


async def _verify_content_exists(content_type: ContentTypeEnum, content_id: int, db: AsyncSession) -> bool:
    """Verify that the content exists."""
    if content_type == ContentTypeEnum.summary:
        stmt = select(Summary).where(Summary.id == content_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None
    elif content_type == ContentTypeEnum.quiz:
        stmt = select(McqQuiz).where(McqQuiz.id == content_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None
    elif content_type == ContentTypeEnum.file:
        stmt = select(PhysicalFile).where(PhysicalFile.id == content_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None
    return False


def _convert_comment_to_read(comment: ContentComment, include_replies: bool = False) -> ContentCommentRead:
    """Convert ContentComment model to read schema with author details."""
    comment_read = ContentCommentRead.model_validate(comment)
    
    # Add author details
    if hasattr(comment, 'author') and comment.author:
        comment_read.author_username = comment.author.username
        comment_read.author_first_name = comment.author.first_name
        comment_read.author_last_name = comment.author.last_name
    
    # Add reply count and replies if requested
    if include_replies and hasattr(comment, 'replies'):
        comment_read.replies = [
            _convert_comment_to_read(reply, include_replies=False) 
            for reply in comment.replies if not reply.is_deleted
        ]
        comment_read.reply_count = len(comment_read.replies)
    
    return comment_read


# ============ Comments Endpoints ============

@router.post("/comments", response_model=CommentCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    comment_data: ContentCommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new comment on content."""
    # Verify content exists
    if not await _verify_content_exists(comment_data.content_type, comment_data.content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{comment_data.content_type.value.title()} not found"
        )
    
    # Verify parent comment exists if provided
    if comment_data.parent_comment_id:
        parent_stmt = select(ContentComment).where(
            ContentComment.id == comment_data.parent_comment_id,
            ContentComment.content_type == comment_data.content_type,
            ContentComment.content_id == comment_data.content_id,
            ContentComment.is_deleted == False
        )
        parent_result = await db.execute(parent_stmt)
        parent_comment = parent_result.scalar_one_or_none()
        
        if not parent_comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found"
            )
    
    # Create comment
    new_comment = ContentComment(
        author_id=current_user.id,
        content_type=comment_data.content_type,
        content_id=comment_data.content_id,
        comment_text=comment_data.comment_text,
        parent_comment_id=comment_data.parent_comment_id
    )
    
    db.add(new_comment)
    await db.commit()
    await db.refresh(new_comment)
    
    # Load comment with author
    comment_stmt = select(ContentComment).options(
        selectinload(ContentComment.author)
    ).where(ContentComment.id == new_comment.id)
    comment_result = await db.execute(comment_stmt)
    comment_with_author = comment_result.scalar_one()
    
    # Send notification for reply
    if comment_data.parent_comment_id:
        notification_service = NotificationService(db)
        parent_stmt = select(ContentComment).where(
            ContentComment.id == comment_data.parent_comment_id
        )
        parent_result = await db.execute(parent_stmt)
        parent_comment = parent_result.scalar_one_or_none()
        
        if parent_comment and parent_comment.author_id != current_user.id:
            await notification_service.notify_comment_reply(
                original_comment_author_id=parent_comment.author_id,
                reply_author_id=current_user.id,
                content_type=comment_data.content_type,
                content_id=comment_data.content_id,
                reply_text=comment_data.comment_text
            )
    
    return CommentCreateResponse(
        message="Comment created successfully",
        comment=_convert_comment_to_read(comment_with_author)
    )


@router.get("/comments", response_model=CommentThreadResponse)
async def get_comments(
    content_type: ContentTypeEnum = Query(...),
    content_id: int = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    include_replies: bool = Query(True),
    db: AsyncSession = Depends(get_async_db)
):
    """Get comments for specific content."""
    # Verify content exists
    if not await _verify_content_exists(content_type, content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{content_type.value.title()} not found"
        )
    
    # Get top-level comments (no parent)
    stmt = select(ContentComment).options(
        selectinload(ContentComment.author)
    ).where(
        ContentComment.content_type == content_type,
        ContentComment.content_id == content_id,
        ContentComment.parent_comment_id.is_(None),
        ContentComment.is_deleted == False
    ).order_by(ContentComment.created_at.desc())
    
    # Get total count
    count_stmt = select(func.count(ContentComment.id)).where(
        ContentComment.content_type == content_type,
        ContentComment.content_id == content_id,
        ContentComment.parent_comment_id.is_(None),
        ContentComment.is_deleted == False
    )
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar()
    
    # Get paginated comments
    paginated_stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(paginated_stmt)
    comments = result.scalars().all()
    
    # If including replies, load them
    if include_replies:
        for comment in comments:
            replies_stmt = select(ContentComment).options(
                selectinload(ContentComment.author)
            ).where(
                ContentComment.parent_comment_id == comment.id,
                ContentComment.is_deleted == False
            ).order_by(ContentComment.created_at.asc())
            
            replies_result = await db.execute(replies_stmt)
            replies = replies_result.scalars().all()
            comment.replies = replies
    
    comment_reads = [_convert_comment_to_read(comment, include_replies) for comment in comments]
    
    return CommentThreadResponse(
        comments=comment_reads,
        total_count=total_count,
        has_more=(skip + limit) < total_count
    )


@router.put("/comments/{comment_id}", response_model=ContentCommentRead)
async def update_comment(
    comment_id: int,
    update_data: ContentCommentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update a comment."""
    stmt = select(ContentComment).options(
        selectinload(ContentComment.author)
    ).where(ContentComment.id == comment_id)
    result = await db.execute(stmt)
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Check ownership or admin rights
    if comment.author_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this comment"
        )
    
    # Check if comment is deleted
    if comment.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update deleted comment"
        )
    
    # Update comment
    comment.comment_text = update_data.comment_text
    comment.is_edited = True
    comment.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(comment)
    
    return _convert_comment_to_read(comment)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete (soft delete) a comment."""
    stmt = select(ContentComment).where(ContentComment.id == comment_id)
    result = await db.execute(stmt)
    comment = result.scalar_one_or_none()
    
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Check ownership or admin rights
    if comment.author_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this comment"
        )
    
    # Soft delete
    comment.is_deleted = True
    comment.updated_at = datetime.now(timezone.utc)
    
    await db.commit()


# ============ Ratings Endpoints ============

@router.post("/ratings", response_model=RatingCreateResponse)
async def create_or_update_rating(
    rating_data: ContentRatingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Create or update a rating for content."""
    # Verify content exists
    if not await _verify_content_exists(rating_data.content_type, rating_data.content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{rating_data.content_type.value.title()} not found"
        )
    
    # Check if user already rated this content
    existing_stmt = select(ContentRating).where(
        ContentRating.user_id == current_user.id,
        ContentRating.content_type == rating_data.content_type,
        ContentRating.content_id == rating_data.content_id
    )
    existing_result = await db.execute(existing_stmt)
    existing_rating = existing_result.scalar_one_or_none()
    
    if existing_rating:
        # Update existing rating
        existing_rating.rating = rating_data.rating
        existing_rating.review_text = rating_data.review_text
        existing_rating.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(existing_rating)
        
        return RatingCreateResponse(
            message="Rating updated successfully",
            rating=ContentRatingRead.model_validate(existing_rating)
        )
    else:
        # Create new rating
        new_rating = ContentRating(
            user_id=current_user.id,
            content_type=rating_data.content_type,
            content_id=rating_data.content_id,
            rating=rating_data.rating,
            review_text=rating_data.review_text
        )
        
        db.add(new_rating)
        await db.commit()
        await db.refresh(new_rating)
        
        return RatingCreateResponse(
            message="Rating created successfully",
            rating=ContentRatingRead.model_validate(new_rating)
        )


@router.get("/ratings", response_model=List[ContentRatingRead])
async def get_content_ratings(
    content_type: ContentTypeEnum = Query(...),
    content_id: int = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db)
):
    """Get all ratings for specific content."""
    # Verify content exists
    if not await _verify_content_exists(content_type, content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{content_type.value.title()} not found"
        )

    stmt = select(ContentRating).options(
        selectinload(ContentRating.user)
    ).where(
        ContentRating.content_type == content_type,
        ContentRating.content_id == content_id
    ).order_by(ContentRating.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    ratings = result.scalars().all()

    rating_reads = []
    for rating in ratings:
        rating_read = ContentRatingRead.model_validate(rating)
        # Add user details
        if rating.user:
            rating_read.username = rating.user.username
            rating_read.first_name = rating.user.first_name
            rating_read.last_name = rating.user.last_name
        rating_reads.append(rating_read)

    return rating_reads


@router.get("/ratings/stats", response_model=ContentRatingStats)
async def get_content_rating_stats(
    content_type: ContentTypeEnum = Query(...),
    content_id: int = Query(...),
    db: AsyncSession = Depends(get_async_db)
):
    """Get rating statistics for content."""
    # Verify content exists
    if not await _verify_content_exists(content_type, content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{content_type.value.title()} not found"
        )
    
    # Get rating statistics
    stats_stmt = select(
        func.avg(ContentRating.rating.cast(Integer)).label('average_rating'),
        func.count(ContentRating.id).label('total_ratings'),
        func.count(func.distinct(ContentRating.user_id)).label('unique_raters')
    ).where(
        ContentRating.content_type == content_type,
        ContentRating.content_id == content_id
    )
    
    stats_result = await db.execute(stats_stmt)
    stats = stats_result.first()
    
    # Get rating distribution
    distribution_stmt = select(
        ContentRating.rating,
        func.count(ContentRating.id).label('count')
    ).where(
        ContentRating.content_type == content_type,
        ContentRating.content_id == content_id
    ).group_by(ContentRating.rating)
    
    distribution_result = await db.execute(distribution_stmt)
    rating_distribution = {str(row.rating): row.count for row in distribution_result}
    
    # Total count
    count_stmt = select(func.count(ContentRating.id)).where(
        ContentRating.content_type == content_type,
        ContentRating.content_id == content_id
    )
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar()
    
    return ContentRatingStats(
        average_rating=float(stats.average_rating) if stats.average_rating else 0.0,
        total_ratings=stats.total_ratings,
        unique_raters=stats.unique_raters,
        rating_distribution=rating_distribution
    )


@router.delete("/ratings/{rating_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rating(
    rating_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a rating."""
    stmt = select(ContentRating).where(ContentRating.id == rating_id)
    result = await db.execute(stmt)
    rating = result.scalar_one_or_none()
    
    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rating not found"
        )
    
    # Check ownership or admin rights
    if rating.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this rating"
        )
    
    await db.delete(rating)
    await db.commit() 
