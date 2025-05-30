"""
Router for Content Interactions (Comments and Ratings).
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import Integer, func, and_

from db_config import get_db
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


def _verify_content_exists(content_type: ContentTypeEnum, content_id: int, db: Session) -> bool:
    """Verify that the content exists."""
    if content_type == ContentTypeEnum.summary:
        return db.query(Summary).filter(Summary.id == content_id).first() is not None
    elif content_type == ContentTypeEnum.quiz:
        return db.query(McqQuiz).filter(McqQuiz.id == content_id).first() is not None
    elif content_type == ContentTypeEnum.file:
        return db.query(PhysicalFile).filter(PhysicalFile.id == content_id).first() is not None
    return False


def _convert_comment_to_read(comment: ContentComment, include_replies: bool = False) -> ContentCommentRead:
    """Convert ContentComment model to read schema with author details."""
    comment_read = ContentCommentRead.from_orm(comment)
    
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
    db: Session = Depends(get_db)
):
    """Create a new comment on content."""
    # Verify content exists
    if not _verify_content_exists(comment_data.content_type, comment_data.content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{comment_data.content_type.value.title()} not found"
        )
    
    # Verify parent comment exists if provided
    if comment_data.parent_comment_id:
        parent_comment = db.query(ContentComment).filter(
            ContentComment.id == comment_data.parent_comment_id,
            ContentComment.content_type == comment_data.content_type,
            ContentComment.content_id == comment_data.content_id,
            ContentComment.is_deleted == False
        ).first()
        
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
    db.commit()
    db.refresh(new_comment)
    
    # Load comment with author
    comment_with_author = db.query(ContentComment).options(
        joinedload(ContentComment.author)
    ).filter(ContentComment.id == new_comment.id).first()
    
    # Send notification for reply
    if comment_data.parent_comment_id:
        notification_service = NotificationService(db)
        parent_comment = db.query(ContentComment).filter(
            ContentComment.id == comment_data.parent_comment_id
        ).first()
        
        if parent_comment and parent_comment.author_id != current_user.id:
            notification_service.notify_comment_reply(
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
    db: Session = Depends(get_db)
):
    """Get comments for specific content."""
    # Verify content exists
    if not _verify_content_exists(content_type, content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{content_type.value.title()} not found"
        )
    
    # Get top-level comments (no parent)
    query = db.query(ContentComment).options(
        joinedload(ContentComment.author)
    ).filter(
        ContentComment.content_type == content_type,
        ContentComment.content_id == content_id,
        ContentComment.parent_comment_id.is_(None),
        ContentComment.is_deleted == False
    )
    
    total_count = query.count()
    
    comments = query.order_by(
        ContentComment.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    # If including replies, load them
    if include_replies:
        for comment in comments:
            replies = db.query(ContentComment).options(
                joinedload(ContentComment.author)
            ).filter(
                ContentComment.parent_comment_id == comment.id,
                ContentComment.is_deleted == False
            ).order_by(ContentComment.created_at.asc()).all()
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
    db: Session = Depends(get_db)
):
    """Update a comment (by author only)."""
    comment = db.query(ContentComment).options(
        joinedload(ContentComment.author)
    ).filter(
        ContentComment.id == comment_id,
        ContentComment.is_deleted == False
    ).first()
    
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Check ownership
    if comment.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own comments"
        )
    
    # Update comment
    if update_data.comment_text:
        comment.comment_text = update_data.comment_text
        comment.is_edited = True
        comment.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(comment)
    
    return _convert_comment_to_read(comment)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft delete a comment (by author only)."""
    comment = db.query(ContentComment).filter(
        ContentComment.id == comment_id,
        ContentComment.is_deleted == False
    ).first()
    
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # Check ownership or admin role
    if comment.author_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own comments"
        )
    
    # Soft delete
    comment.is_deleted = True
    comment.updated_at = datetime.now(timezone.utc)
    
    db.commit()


# ============ Ratings Endpoints ============

@router.post("/ratings", response_model=RatingCreateResponse)
async def create_or_update_rating(
    rating_data: ContentRatingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update a rating for content."""
    # Verify content exists
    if not _verify_content_exists(rating_data.content_type, rating_data.content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{rating_data.content_type.value.title()} not found"
        )
    
    # Check if user already rated this content
    existing_rating = db.query(ContentRating).filter(
        ContentRating.user_id == current_user.id,
        ContentRating.content_type == rating_data.content_type,
        ContentRating.content_id == rating_data.content_id
    ).first()
    
    if existing_rating:
        # Update existing rating
        existing_rating.rating = rating_data.rating
        existing_rating.review_text = rating_data.review_text
        existing_rating.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing_rating)
        rating = existing_rating
        message = "Rating updated successfully"
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
        db.commit()
        db.refresh(new_rating)
        rating = new_rating
        message = "Rating created successfully"
    
    # Load rating with user
    rating_with_user = db.query(ContentRating).options(
        joinedload(ContentRating.user)
    ).filter(ContentRating.id == rating.id).first()
    
    # Get rating stats
    stats = await get_content_rating_stats(
        content_type=rating_data.content_type,
        content_id=rating_data.content_id,
        db=db
    )
    
    rating_read = ContentRatingRead.from_orm(rating_with_user)
    if rating_with_user.user:
        rating_read.username = rating_with_user.user.username
        rating_read.first_name = rating_with_user.user.first_name
        rating_read.last_name = rating_with_user.user.last_name
    
    return RatingCreateResponse(
        message=message,
        rating=rating_read,
        stats=stats
    )


@router.get("/ratings", response_model=List[ContentRatingRead])
async def get_content_ratings(
    content_type: ContentTypeEnum = Query(...),
    content_id: int = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get ratings for specific content."""
    # Verify content exists
    if not _verify_content_exists(content_type, content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{content_type.value.title()} not found"
        )
    
    ratings = db.query(ContentRating).options(
        joinedload(ContentRating.user)
    ).filter(
        ContentRating.content_type == content_type,
        ContentRating.content_id == content_id
    ).order_by(ContentRating.created_at.desc()).offset(skip).limit(limit).all()
    
    rating_reads = []
    for rating in ratings:
        rating_read = ContentRatingRead.from_orm(rating)
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
    db: Session = Depends(get_db)
):
    """Get rating statistics for specific content."""
    # Verify content exists
    if not _verify_content_exists(content_type, content_id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{content_type.value.title()} not found"
        )
    
    # Get rating statistics
    ratings = db.query(ContentRating).filter(
        ContentRating.content_type == content_type,
        ContentRating.content_id == content_id
    ).all()
    
    if ratings:
        # Calculate average manually
        rating_values = [int(rating.rating.value) for rating in ratings]
        average_rating = sum(rating_values) / len(rating_values)
        total_ratings = len(ratings)
    else:
        average_rating = None
        total_ratings = 0
    
    # Get rating breakdown
    rating_breakdown = {}
    for rating_value in RatingValueEnum:
        count = db.query(ContentRating).filter(
            ContentRating.content_type == content_type,
            ContentRating.content_id == content_id,
            ContentRating.rating == rating_value
        ).count()
        rating_breakdown[rating_value.value] = count
    
    return ContentRatingStats(
        content_type=content_type,
        content_id=content_id,
        average_rating=average_rating,
        total_ratings=total_ratings,
        rating_breakdown=rating_breakdown
    )


@router.delete("/ratings/{rating_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rating(
    rating_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a rating (by author only)."""
    rating = db.query(ContentRating).filter(ContentRating.id == rating_id).first()
    
    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rating not found"
        )
    
    # Check ownership
    if rating.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own ratings"
        )
    
    db.delete(rating)
    db.commit() 