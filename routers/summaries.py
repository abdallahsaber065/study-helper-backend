"""
Summary generation and management routes.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
# Import AsyncSession and select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, desc # Import select and desc

from core.security import get_current_active_user
# Import the async database dependency
from db_config import get_async_db
from models.models import User, Summary, PhysicalFile
from schemas.summary import (
    SummaryRead, SummaryCreate, SummaryUpdate,
    SummaryGenerateRequest, SummaryGenerateTextRequest,
    SummaryGenerateResponse
)
from services.summary_service import SummaryGeneratorService
from services.community_service import CommunityService # Import CommunityService

router = APIRouter(prefix="/summaries", tags=["Summaries"])


@router.post("/generate", response_model=SummaryGenerateResponse)
async def generate_combined_summary(
    request: SummaryGenerateRequest,
    community_id: Optional[int] = Query(None, description="Community ID to associate summary with"),
    current_user: User = Depends(get_current_active_user),
    # Use async database dependency
    db: AsyncSession = Depends(get_async_db)
):
    """
    Generate a summary from both files and text using AI.

    - Requires access to the files
    - Combines files with provided text
    - Uses AI to generate a comprehensive summary
    - Saves the summary to the database
    - Optionally associates with a community (requires admin/moderator access)
    """
    # Check community access if community_id is provided
    if community_id:
        # CommunityService needs to be async now
        community_service = CommunityService(db)
        try:
            # Assuming _check_admin_or_moderator is sync or doesn't hit DB async within router
            # If it hits DB, it needs to be awaited or logic moved to service
            # Based on previous changes, CommunityService is async, this check likely is too.
            await community_service._check_admin_or_moderator(current_user.id, community_id) # Corrected call to pass user_id
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or moderator access required to create community summaries"
            )

    # Initialize the summary generator service (already uses async db)
    summary_service = SummaryGeneratorService(db)

    # Generate the summary
    try:
        # This call is already awaited
        summary = await summary_service.generate_summary(
            user=current_user,
            physical_file_ids=request.physical_file_ids,
            custom_instructions=request.custom_instructions,
            community_id=community_id
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
    # Use async database dependency
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get list of summaries created by the current user.
    """
    # Use select statement
    stmt = select(Summary).where(Summary.user_id == current_user.id)

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(Summary.title.ilike(search_term))

    # Filter by file ID
    if file_id:
        stmt = stmt.where(Summary.physical_file_id == file_id)

    # Order, offset, limit and execute asynchronously
    stmt = stmt.order_by(desc(Summary.created_at)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    # Get all results
    summaries = result.scalars().all()

    return summaries


@router.get("/{summary_id}", response_model=SummaryRead)
async def get_summary_by_id(
    summary_id: int,
    current_user: User = Depends(get_current_active_user),
    # Use async database dependency
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific summary by ID.
    """
    # Use select statement
    stmt = select(Summary).where(Summary.id == summary_id)

    # Execute asynchronously and get one result or none
    result = await db.execute(stmt)
    summary = result.scalar_one_or_none()

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found"
        )

    # Check if user has access to the summary
    # This logic needs to be updated if community access check becomes complex async operation
    if summary.user_id != current_user.id:
         # Check if summary is shared via a community - This check is more complex and likely async.
         # Need to check Community.summaries relationship or CommunityMember table
         from services.community_service import CommunityService
         community_service = CommunityService(db)
         has_access = await community_service.has_summary_access(summary_id, current_user.id)
         if not has_access:
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
    # Use async database dependency
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update a summary.
    """
    # Use select statement to find the summary for the current user
    stmt = select(Summary).where(
        Summary.id == summary_id,
        Summary.user_id == current_user.id
    )
    result = await db.execute(stmt)
    summary = result.scalar_one_or_none()

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found or you don't have permission to update it"
        )

    # Update fields if provided
    update_data = summary_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(summary, field, value)

    # Commit changes asynchronously
    await db.commit()
    # Refresh asynchronously
    await db.refresh(summary)

    return summary


@router.delete("/{summary_id}")
async def delete_summary(
    summary_id: int,
    current_user: User = Depends(get_current_active_user),
    # Use async database dependency
    db: AsyncSession = Depends(get_async_db)
):
    """
    Delete a summary.
    """
    # Use select statement to find the summary for the current user
    stmt = select(Summary).where(
        Summary.id == summary_id,
        Summary.user_id == current_user.id
    )
    result = await db.execute(stmt)
    summary = result.scalar_one_or_none()

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found or you don't have permission to delete it"
        )

    # Delete the summary asynchronously
    await db.delete(summary)
    # Commit changes asynchronously
    await db.commit()

    return {"message": "Summary deleted successfully"} 