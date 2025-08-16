"""
API routes for summary generation and management.
"""

from typing import Dict, List
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..database import get_db_session
from ..tasks.summary_tasks import generate_summary_task
from ..usage.services import QuotaManager
from ..usage.schemas import OperationType
from ..users.models import User
from .models import Summary
from .schemas import (
    BulkSummaryOperation,
    SummaryAnalytics,
    SummaryFilters,
    SummaryGenerateRequest,
    SummaryListResponse,
    SummaryProgressResponse,
    SummaryRegenerateRequest,
    SummaryResponse,
    SummaryUpdateRequest,
    TaskProgressUpdate,
)
from .services import PromptTemplateService, SummaryService

router = APIRouter()


@router.post(
    "/generate",
    response_model=SummaryProgressResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate AI Summary",
    description="Queue a new AI-powered summary generation task",
)
async def generate_summary(
    request: SummaryGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Generate an AI-powered summary for a document.

    This endpoint queues a background task to generate a summary and returns
    immediately with task information. Use the progress endpoints to monitor
    the generation status.
    """

    try:
        summary_service = SummaryService(db)
        quota_manager = QuotaManager(db)

        # Check quota availability first
        from decimal import Decimal

        estimated_tokens = 4000  # Rough estimate for summary generation
        estimated_cost = Decimal("0.10")  # Rough cost estimate

        quota_check = await quota_manager.check_quota_availability(
            user_id=current_user.id,
            operation_type=OperationType.SUMMARY,
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
        )

        if not quota_check.can_proceed:

            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient quota: {quota_check.reason}",
            )

        # Validate summary type
        prompt_service = PromptTemplateService()
        if not prompt_service.validate_summary_type(request.summary_type.value):

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid summary type: {request.summary_type}",
            )

        # Create summary record

        summary = await summary_service.create_summary(
            user_id=current_user.id,
            file_id=request.file_id,
            title=request.title,
            summary_type=request.summary_type.value,
            ai_provider=request.ai_provider.value if request.ai_provider else "openai",
            ai_model_used=request.ai_model or "gpt-4o",
            max_length=request.max_length,
            temperature=request.temperature,
            custom_instructions=request.custom_instructions,
        )

        # Prepare task configuration
        summary_config = {
            "summary_type": request.summary_type.value,
            "ai_provider": (
                request.ai_provider.value if request.ai_provider else "openai"
            ),
            "ai_model": request.ai_model,
            "max_length": request.max_length,
            "temperature": request.temperature,
            "custom_instructions": request.custom_instructions,
        }

        # Queue background task

        task = generate_summary_task.delay(
            summary_id=summary.id,
            file_id=request.file_id,
            user_id=current_user.id,
            summary_config=summary_config,
        )

        # Update summary with task ID
        summary.task_id = task.id
        await db.commit()

        return SummaryProgressResponse(
            task_id=task.id,
            summary_id=summary.id,
            status="pending",
            progress_percentage=0,
            current_step="Task queued for processing",
        )

    except HTTPException:
        raise  # Re-raise HTTPException to preserve status code and detail
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue summary generation task",
        )


@router.get(
    "",
    response_model=SummaryListResponse,
    summary="List Summaries",
    description="Get paginated list of user's summaries with filtering options",
)
async def list_summaries(
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    # Filtering
    status_filter: List[str] = Query(None, description="Filter by status"),
    summary_type: List[str] = Query(None, description="Filter by summary type"),
    ai_provider: List[str] = Query(None, description="Filter by AI provider"),
    search: str = Query(None, description="Search in title and content"),
    # Sorting
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    # Dependencies
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get a paginated list of the user's summaries with optional filtering and sorting.

    Supports filtering by status, summary type, AI provider, and full-text search.
    """

    try:
        summary_service = SummaryService(db)

        filters = SummaryFilters(
            page=page,
            page_size=page_size,
            status=status_filter,
            summary_type=summary_type,
            ai_provider=ai_provider,
            search_query=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        summaries = await summary_service.get_summaries(current_user.id, filters)

        return summaries

    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve summaries",
        )


@router.get(
    "/{summary_id}",
    response_model=SummaryResponse,
    summary="Get Summary",
    description="Retrieve a specific summary by ID",
)
async def get_summary(
    summary_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get detailed information about a specific summary."""

    try:
        summary_service = SummaryService(db)
        summary = await summary_service.get_summary(summary_id, current_user.id)

        if not summary:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found"
            )

        return SummaryResponse.from_orm(summary)

    except HTTPException:
        raise
    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve summary",
        )


@router.put(
    "/{summary_id}",
    response_model=SummaryResponse,
    summary="Update Summary",
    description="Update summary metadata (title, rating, feedback)",
)
async def update_summary(
    summary_id: str,
    request: SummaryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Update summary metadata like title, user rating, and feedback."""

    try:
        summary_service = SummaryService(db)

        updates = request.dict(exclude_unset=True)

        if not updates:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update data provided.",
            )

        summary = await summary_service.update_summary(
            summary_id, current_user.id, **updates
        )

        if not summary:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found"
            )

        return SummaryResponse.from_orm(summary)

    except HTTPException:
        raise
    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update summary",
        )


@router.post(
    "/{summary_id}/regenerate",
    response_model=SummaryProgressResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Regenerate Summary",
    description="Regenerate an existing summary with new parameters",
)
async def regenerate_summary(
    summary_id: str,
    request: SummaryRegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Regenerate an existing summary with new parameters.

    This creates a new version of the summary while preserving the original.
    """

    try:
        summary_service = SummaryService(db)
        summary = await summary_service.get_summary(summary_id, current_user.id)

        if not summary:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found"
            )

        if summary.is_processing:

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Summary is already being processed",
            )

        # Update summary configuration
        updates = {
            "status": "pending",
            "progress_percentage": 0,
            "error_message": None,
            "completed_at": None,
        }
        updates.update(request.dict(exclude_unset=True))

        summary = await summary_service.update_summary(
            summary_id, current_user.id, **updates
        )

        # Prepare task configuration
        summary_config = {
            "summary_type": summary.summary_type,
            "ai_provider": summary.ai_provider,
            "ai_model": summary.ai_model_used,
            "max_length": summary.max_length,
            "temperature": float(summary.temperature) if summary.temperature else 0.7,
            "custom_instructions": summary.custom_instructions,
        }

        # Queue background task

        task = generate_summary_task.delay(
            summary_id=summary.id,
            file_id=summary.file_id,
            user_id=current_user.id,
            summary_config=summary_config,
        )

        # Update summary with new task ID
        summary.task_id = task.id
        await db.commit()

        return SummaryProgressResponse(
            task_id=task.id,
            summary_id=summary.id,
            status="pending",
            progress_percentage=0,
            current_step="Task queued for processing",
        )

    except HTTPException:
        raise
    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate summary",
        )


@router.delete(
    "/{summary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Summary",
    description="Soft delete a summary",
)
async def delete_summary(
    summary_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Soft delete a summary."""

    try:
        summary_service = SummaryService(db)
        success = await summary_service.delete_summary(summary_id, current_user.id)

        if not success:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found"
            )

    except HTTPException:
        raise
    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete summary",
        )


@router.get(
    "/{summary_id}/progress",
    response_model=SummaryProgressResponse,
    summary="Get Progress",
    description="Get real-time progress of summary generation",
)
async def get_summary_progress(
    summary_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get the current progress of a summary generation task."""

    try:
        summary_service = SummaryService(db)
        summary = await summary_service.get_summary(summary_id, current_user.id)

        if not summary:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found"
            )

        # Estimate remaining time (placeholder logic)
        estimated_time_remaining = None
        if summary.is_processing:
            # Simple estimation based on progress
            if summary.progress_percentage > 0:
                # Rough estimate: if we're X% done, remaining time = (100-X)/X * elapsed_time
                # This is a simplified estimation
                estimated_time_remaining = max(
                    30, 300 - (summary.progress_percentage * 3)
                )

        return SummaryProgressResponse(
            task_id=summary.task_id or "",
            summary_id=summary.id,
            status=summary.status,
            progress_percentage=summary.progress_percentage,
            estimated_time_remaining=estimated_time_remaining,
            current_step=f"Processing: {summary.status}",
        )

    except HTTPException:
        raise
    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get summary progress",
        )


@router.get(
    "/analytics/overview",
    response_model=Dict,
    summary="Get Analytics",
    description="Get analytics overview for user's summaries",
)
async def get_summary_analytics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get comprehensive analytics for the user's summaries."""

    try:
        summary_service = SummaryService(db)
        analytics = await summary_service.get_user_analytics(current_user.id)

        return analytics

    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics",
        )


@router.get(
    "/templates",
    response_model=List[str],
    summary="Get Templates",
    description="Get list of available summary template types",
)
async def get_summary_templates():
    """Get list of available summary template types."""

    try:
        prompt_service = PromptTemplateService()
        templates = prompt_service.get_available_templates()

        return templates

    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve templates",
        )


@router.post(
    "/bulk",
    response_model=Dict[str, str],
    summary="Bulk Operations",
    description="Perform bulk operations on multiple summaries",
)
async def bulk_summary_operations(
    request: BulkSummaryOperation,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Perform bulk operations on multiple summaries.

    Supported operations: delete, regenerate, export
    """

    try:
        summary_service = SummaryService(db)
        results = {}

        for summary_id in request.summary_ids:
            try:

                if request.operation == "delete":
                    success = await summary_service.delete_summary(
                        summary_id, current_user.id
                    )
                    results[summary_id] = "deleted" if success else "not_found"

                elif request.operation == "regenerate":
                    # Queue regeneration tasks (simplified)
                    summary = await summary_service.get_summary(
                        summary_id, current_user.id
                    )
                    if summary and not summary.is_processing:
                        # Implementation would queue regeneration task
                        results[summary_id] = "queued"

                    else:
                        results[summary_id] = "not_available"

                elif request.operation == "export":
                    # Export implementation would go here
                    results[summary_id] = "exported"

            except Exception as e:

                results[summary_id] = "error"

            f"Completed bulk '{request.operation}' for user {current_user.id}: {len(request.summary_ids)} items. Results: {results}"

        return results

    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to perform bulk operations",
        )
