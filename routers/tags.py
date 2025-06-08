"""
Router for Question Tags Management.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from db_config import get_async_db
from core.security import get_current_user
from models.models import (
    User, QuestionTag, McqQuestion, McqQuestionTagLink
)
from schemas.mcq import QuestionTagCreate, QuestionTagRead, QuestionTagUpdate

router = APIRouter(prefix="/tags", tags=["Question Tags"])


@router.post("/", response_model=QuestionTagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_data: QuestionTagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new question tag."""
    # Check if tag with same name already exists
    stmt = select(QuestionTag).where(QuestionTag.name == tag_data.name)
    result = await db.execute(stmt)
    existing_tag = result.scalar_one_or_none()
    
    if existing_tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tag with name '{tag_data.name}' already exists"
        )
    
    # Create new tag
    new_tag = QuestionTag(
        name=tag_data.name,
        description=tag_data.description
    )
    
    db.add(new_tag)
    await db.commit()
    await db.refresh(new_tag)
    
    return QuestionTagRead.from_orm(new_tag)


@router.get("/", response_model=List[QuestionTagRead])
async def list_tags(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search tags by name or description"),
    db: AsyncSession = Depends(get_async_db)
):
    """Get all question tags with optional search."""
    stmt = select(QuestionTag)
    
    # Apply search filter
    if search:
        search_filter = or_(
            QuestionTag.name.ilike(f"%{search}%"),
            QuestionTag.description.ilike(f"%{search}%")
        )
        stmt = stmt.where(search_filter)
    
    # Apply pagination and ordering
    stmt = stmt.offset(skip).limit(limit).order_by(QuestionTag.name)
    
    result = await db.execute(stmt)
    tags = result.scalars().all()
    
    return [QuestionTagRead.from_orm(tag) for tag in tags]


@router.get("/{tag_id}", response_model=QuestionTagRead)
async def get_tag(tag_id: int, db: AsyncSession = Depends(get_async_db)):
    """Get a specific tag by ID."""
    stmt = select(QuestionTag).where(QuestionTag.id == tag_id)
    result = await db.execute(stmt)
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        )
    
    return QuestionTagRead.from_orm(tag)


@router.put("/{tag_id}", response_model=QuestionTagRead)
async def update_tag(
    tag_id: int,
    update_data: QuestionTagUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update a question tag."""
    # Get the tag
    stmt = select(QuestionTag).where(QuestionTag.id == tag_id)
    result = await db.execute(stmt)
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        )
    
    # Check if new name conflicts with existing tag
    if update_data.name and update_data.name != tag.name:
        name_check_stmt = select(QuestionTag).where(
            QuestionTag.name == update_data.name,
            QuestionTag.id != tag_id
        )
        name_check_result = await db.execute(name_check_stmt)
        existing_tag = name_check_result.scalar_one_or_none()
        
        if existing_tag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tag with name '{update_data.name}' already exists"
            )
    
    # Update tag fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(tag, field, value)
    
    await db.commit()
    await db.refresh(tag)
    
    return QuestionTagRead.from_orm(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a question tag."""
    # Get the tag
    stmt = select(QuestionTag).where(QuestionTag.id == tag_id)
    result = await db.execute(stmt)
    tag = result.scalar_one_or_none()
    
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        )
    
    # Check if tag is being used by questions
    usage_stmt = select(func.count(McqQuestionTagLink.question_id)).where(
        McqQuestionTagLink.tag_id == tag_id
    )
    usage_result = await db.execute(usage_stmt)
    usage_count = usage_result.scalar()
    
    if usage_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete tag. It is being used by {usage_count} question(s)"
        )
    
    await db.delete(tag)
    await db.commit()

