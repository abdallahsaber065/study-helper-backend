"""
Router for MCQ and Quiz functionality.
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from db_config import get_db
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
    db: Session = Depends(get_db)
):
    """Create a new MCQ question."""
    # Create the question
    question_data = question.dict(exclude={"tag_ids"})
    db_question = McqQuestion(**question_data, user_id=current_user.id)
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    
    # Link with tags
    if question.tag_ids:
        for tag_id in question.tag_ids:
            tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
            if tag:
                tag_link = McqQuestionTagLink(question_id=db_question.id, tag_id=tag_id)
                db.add(tag_link)
        db.commit()
    
    # Reload with tags
    db_question = db.query(McqQuestion).options(
        joinedload(McqQuestion.tag_links).joinedload(McqQuestionTagLink.tag)
    ).filter(McqQuestion.id == db_question.id).first()
    
    return _convert_question_to_read(db_question)


@router.get("/questions", response_model=List[McqQuestionRead])
async def list_questions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tag_id: Optional[int] = Query(None),
    difficulty: Optional[str] = Query(None),
    my_questions: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List MCQ questions with filtering options."""
    query = db.query(McqQuestion).options(
        joinedload(McqQuestion.tag_links).joinedload(McqQuestionTagLink.tag)
    )
    
    if my_questions:
        query = query.filter(McqQuestion.user_id == current_user.id)
    
    if tag_id:
        query = query.join(McqQuestionTagLink).filter(McqQuestionTagLink.tag_id == tag_id)
    
    if difficulty:
        query = query.filter(McqQuestion.difficulty_level == difficulty)
    
    questions = query.offset(skip).limit(limit).all()
    return [_convert_question_to_read(q) for q in questions]


@router.get("/questions/{question_id}", response_model=McqQuestionRead)
async def get_question(
    question_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific MCQ question."""
    question = db.query(McqQuestion).options(
        joinedload(McqQuestion.tag_links).joinedload(McqQuestionTagLink.tag)
    ).filter(McqQuestion.id == question_id).first()
    
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    
    return _convert_question_to_read(question)


@router.put("/questions/{question_id}", response_model=McqQuestionRead)
async def update_question(
    question_id: int,
    question_update: McqQuestionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an MCQ question."""
    question = db.query(McqQuestion).filter(McqQuestion.id == question_id).first()
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    
    # Check ownership or admin rights
    if question.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this question"
        )
    
    # Update question fields
    update_data = question_update.dict(exclude_unset=True, exclude={"tag_ids"})
    for field, value in update_data.items():
        setattr(question, field, value)
    
    question.updated_at = datetime.now(timezone.utc)
    
    # Update tag associations if provided
    if question_update.tag_ids is not None:
        # Remove existing tag links
        db.query(McqQuestionTagLink).filter(McqQuestionTagLink.question_id == question_id).delete()
        
        # Add new tag links
        for tag_id in question_update.tag_ids:
            tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
            if tag:
                tag_link = McqQuestionTagLink(question_id=question_id, tag_id=tag_id)
                db.add(tag_link)
    
    db.commit()
    db.refresh(question)
    
    # Reload with tags
    question = db.query(McqQuestion).options(
        joinedload(McqQuestion.tag_links).joinedload(McqQuestionTagLink.tag)
    ).filter(McqQuestion.id == question_id).first()
    
    return _convert_question_to_read(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an MCQ question."""
    question = db.query(McqQuestion).filter(McqQuestion.id == question_id).first()
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    
    # Check ownership or admin rights
    if question.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this question"
        )
    
    db.delete(question)
    db.commit()


