"""
Router for MCQ and Quiz functionality.
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, delete
from db_config import get_async_db
from core.security import get_current_user
from models.models import (
    User, QuestionTag, McqQuestion, McqQuestionTagLink, 
)
from schemas.mcq import (
    _convert_question_to_read,
    # Question schemas  
    McqQuestionCreate, McqQuestionRead, McqQuestionUpdate,
)

router = APIRouter(prefix="/mcqs", tags=["MCQs"])



# ============ MCQ Question Endpoints ============

@router.post("/questions", response_model=McqQuestionRead, status_code=status.HTTP_201_CREATED)
async def create_question(
    question: McqQuestionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new MCQ question."""
    # Create the question
    question_data = question.model_dump(exclude={"tag_ids"})
    db_question = McqQuestion(**question_data, user_id=current_user.id)
    db.add(db_question)
    await db.commit()
    await db.refresh(db_question)
    
    # Link with tags
    if question.tag_ids:
        for tag_id in question.tag_ids:
            tag_stmt = select(QuestionTag).where(QuestionTag.id == tag_id)
            tag_result = await db.execute(tag_stmt)
            tag = tag_result.scalar_one_or_none()
            if tag:
                tag_link = McqQuestionTagLink(question_id=db_question.id, tag_id=tag_id)
                db.add(tag_link)
        await db.commit()
    
    # Reload with tags
    question_stmt = select(McqQuestion).options(
        selectinload(McqQuestion.tag_links).selectinload(McqQuestionTagLink.tag)
    ).where(McqQuestion.id == db_question.id)
    question_result = await db.execute(question_stmt)
    db_question = question_result.scalar_one()
    
    return _convert_question_to_read(db_question)


@router.get("/questions", response_model=List[McqQuestionRead])
async def list_questions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tag_id: Optional[int] = Query(None),
    difficulty: Optional[str] = Query(None),
    my_questions: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """List MCQ questions with filtering options."""
    stmt = select(McqQuestion).options(
        selectinload(McqQuestion.tag_links).selectinload(McqQuestionTagLink.tag)
    )
    
    if my_questions:
        stmt = stmt.where(McqQuestion.user_id == current_user.id)
    
    if tag_id:
        stmt = stmt.join(McqQuestionTagLink).where(McqQuestionTagLink.tag_id == tag_id)
    
    if difficulty:
        stmt = stmt.where(McqQuestion.difficulty_level == difficulty)
    
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    questions = result.scalars().all()
    
    return [_convert_question_to_read(q) for q in questions]


@router.get("/questions/{question_id}", response_model=McqQuestionRead)
async def get_question(
    question_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Get a specific MCQ question."""
    stmt = select(McqQuestion).options(
        selectinload(McqQuestion.tag_links).selectinload(McqQuestionTagLink.tag)
    ).where(McqQuestion.id == question_id)
    
    result = await db.execute(stmt)
    question = result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    
    return _convert_question_to_read(question)


@router.put("/questions/{question_id}", response_model=McqQuestionRead)
async def update_question(
    question_id: int,
    question_update: McqQuestionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update an MCQ question."""
    stmt = select(McqQuestion).where(McqQuestion.id == question_id)
    result = await db.execute(stmt)
    question = result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    
    # Check ownership or admin rights
    if question.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this question"
        )
    
    # Update question fields
    update_data = question_update.model_dump(exclude_unset=True, exclude={"tag_ids"})
    for field, value in update_data.items():
        setattr(question, field, value)
    
    question.updated_at = datetime.now(timezone.utc)
    
    # Update tag associations if provided
    if question_update.tag_ids is not None:
        # Remove existing tag links
        delete_stmt = delete(McqQuestionTagLink).where(McqQuestionTagLink.question_id == question_id)
        await db.execute(delete_stmt)
        
        # Add new tag links
        for tag_id in question_update.tag_ids:
            tag_stmt = select(QuestionTag).where(QuestionTag.id == tag_id)
            tag_result = await db.execute(tag_stmt)
            tag = tag_result.scalar_one_or_none()
            if tag:
                tag_link = McqQuestionTagLink(question_id=question_id, tag_id=tag_id)
                db.add(tag_link)
    
    await db.commit()
    await db.refresh(question)
    
    # Reload with tags
    question_stmt = select(McqQuestion).options(
        selectinload(McqQuestion.tag_links).selectinload(McqQuestionTagLink.tag)
    ).where(McqQuestion.id == question_id)
    question_result = await db.execute(question_stmt)
    question = question_result.scalar_one()
    
    return _convert_question_to_read(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete an MCQ question."""
    stmt = select(McqQuestion).where(McqQuestion.id == question_id)
    result = await db.execute(stmt)
    question = result.scalar_one_or_none()
    
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    
    # Check ownership or admin rights
    if question.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this question"
        )
    
    await db.delete(question)
    await db.commit()


