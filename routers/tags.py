"""
Router for MCQ and Quiz functionality.
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from db_config import get_db
from core.security import get_current_user
from models.models import (
    User, QuestionTag,
)
from schemas.mcq import (
    # Tag schemas
    QuestionTagCreate, QuestionTagRead, QuestionTagUpdate,
)

router = APIRouter(prefix="/tags", tags=["Tags"])

# ============ Question Tag Endpoints ============

@router.post("/tags", response_model=QuestionTagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag: QuestionTagCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new question tag."""
    # Check if tag already exists
    existing_tag = db.query(QuestionTag).filter(QuestionTag.name == tag.name).first()
    if existing_tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tag with this name already exists"
        )
    
    db_tag = QuestionTag(**tag.dict())
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag


@router.get("/tags", response_model=List[QuestionTagRead])
async def list_tags(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List all question tags."""
    query = db.query(QuestionTag)
    
    if search:
        query = query.filter(QuestionTag.name.ilike(f"%{search}%"))
    
    tags = query.offset(skip).limit(limit).all()
    return tags


@router.get("/tags/{tag_id}", response_model=QuestionTagRead)
async def get_tag(tag_id: int, db: Session = Depends(get_db)):
    """Get a specific question tag."""
    tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.put("/tags/{tag_id}", response_model=QuestionTagRead)
async def update_tag(
    tag_id: int,
    tag_update: QuestionTagUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a question tag."""
    tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    
    # Check if new name conflicts with existing tag
    if tag_update.name and tag_update.name != tag.name:
        existing_tag = db.query(QuestionTag).filter(QuestionTag.name == tag_update.name).first()
        if existing_tag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tag with this name already exists"
            )
    
    update_data = tag_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tag, field, value)
    
    tag.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a question tag."""
    tag = db.query(QuestionTag).filter(QuestionTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    
    db.delete(tag)
    db.commit()

