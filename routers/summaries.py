"""
Summary generation and management routes.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from core.security import get_current_active_user
from db_config import get_db
from models.models import User, Summary, PhysicalFile
from schemas.summary import (
    SummaryRead, SummaryCreate, SummaryUpdate, 
    SummaryGenerateRequest, SummaryGenerateTextRequest,
    SummaryGenerateResponse
)
from services.summary_service import SummaryGeneratorService

router = APIRouter(prefix="/summaries", tags=["Summaries"])


@router.post("/generate", response_model=SummaryGenerateResponse)
async def generate_combined_summary(
    request: SummaryGenerateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Generate a summary from both files and text using AI.
    
    - Requires access to the files
    - Combines files with provided text
    - Uses AI to generate a comprehensive summary
    - Saves the summary to the database
    """
    # Initialize the summary generator service
    summary_service = SummaryGeneratorService(db)
    
    # Generate the summary
    try:
        summary = await summary_service.generate_summary(
            user=current_user,
            physical_file_ids=request.physical_file_ids,
            custom_instructions=request.custom_instructions
        )
        
        return SummaryGenerateResponse(
            message="Summary generated successfully",
            summary=summary
        )
    except HTTPException as e:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log the error and return a generic error message
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate summary: {str(e)}"
        )


@router.get("/", response_model=List[SummaryRead])
async def get_user_summaries(
    skip: int = Query(0, ge=0, description="Number of summaries to skip"),
    limit: int = Query(100, ge=1, le=100, description="Number of summaries to return"),
    search: Optional[str] = Query(None, description="Search by title"),
    file_id: Optional[int] = Query(None, description="Filter by file ID"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get list of summaries created by the current user.
    """
    query = db.query(Summary).filter(Summary.user_id == current_user.id)
    
    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(Summary.title.ilike(search_term))
    
    # Filter by file ID
    if file_id:
        query = query.filter(Summary.physical_file_id == file_id)
    
    summaries = query.order_by(Summary.created_at.desc()).offset(skip).limit(limit).all()
    return summaries


@router.get("/{summary_id}", response_model=SummaryRead)
async def get_summary_by_id(
    summary_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific summary by ID.
    """
    summary = db.query(Summary).filter(
        Summary.id == summary_id
    ).first()
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found"
        )
    
    # Check if user has access to the summary
    if summary.user_id != current_user.id:
        # Check if summary is shared via a community (not implemented yet)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this summary"
        )
    
    return summary


@router.put("/{summary_id}", response_model=SummaryRead)
async def update_summary(
    summary_id: int,
    summary_update: SummaryUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update a summary.
    """
    summary = db.query(Summary).filter(
        Summary.id == summary_id,
        Summary.user_id == current_user.id
    ).first()
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found or you don't have permission to update it"
        )
    
    # Update fields if provided
    update_data = summary_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(summary, field, value)
    
    db.commit()
    db.refresh(summary)
    
    return summary


@router.delete("/{summary_id}")
async def delete_summary(
    summary_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a summary.
    """
    summary = db.query(Summary).filter(
        Summary.id == summary_id,
        Summary.user_id == current_user.id
    ).first()
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found or you don't have permission to delete it"
        )
    
    db.delete(summary)
    db.commit()
    
    return {"message": "Summary deleted successfully"} 