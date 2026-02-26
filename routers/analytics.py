"""
Router for Content Analytics.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db_config import get_async_db
from core.security import get_current_user
from models.models import User, ContentTypeEnum
from schemas.analytics import (
    ContentAnalyticsRead, AnalyticsIncrement, ContentAnalyticsSummary,
    AnalyticsDashboard, ContentEngagementMetrics
)
from services.analytics_service import ContentAnalyticsService

router = APIRouter(prefix="/analytics", tags=["Content Analytics"])


@router.post("/content/{content_type}/{content_id}/increment", response_model=ContentAnalyticsRead)
async def increment_content_metric(
    content_type: ContentTypeEnum,
    content_id: int,
    increment_data: AnalyticsIncrement,
    db: AsyncSession = Depends(get_async_db)
):
    """Increment a specific metric for content."""
    analytics_service = ContentAnalyticsService(db)
    
    return analytics_service.increment_metric(
        content_type=content_type,
        content_id=content_id,
        metric=increment_data.metric,
        increment=increment_data.increment
    )


@router.get("/content/{content_type}/{content_id}", response_model=ContentAnalyticsRead)
async def get_content_analytics(
    content_type: ContentTypeEnum,
    content_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Get analytics for specific content."""
    analytics_service = ContentAnalyticsService(db)
    
    return analytics_service.get_analytics(
        content_type=content_type,
        content_id=content_id
    )


@router.get("/content/{content_type}/{content_id}/engagement", response_model=ContentEngagementMetrics)
async def get_content_engagement_metrics(
    content_type: ContentTypeEnum,
    content_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Get detailed engagement metrics for content."""
    analytics_service = ContentAnalyticsService(db)
    
    return analytics_service.get_content_engagement_metrics(
        content_type=content_type,
        content_id=content_id
    )


@router.get("/top-content", response_model=List[ContentAnalyticsSummary])
async def get_top_content(
    content_type: Optional[ContentTypeEnum] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    metric: str = Query("engagement", pattern="^(engagement|views|likes|comments|shares)$"),
    db: AsyncSession = Depends(get_async_db)
):
    """Get top performing content."""
    analytics_service = ContentAnalyticsService(db)
    
    return analytics_service.get_top_content(
        content_type=content_type,
        limit=limit,
        metric=metric
    )


@router.get("/dashboard", response_model=AnalyticsDashboard)
async def get_analytics_dashboard(
    user_id: Optional[int] = Query(None, description="Filter by user (admin only)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get dashboard analytics with aggregated metrics."""
    analytics_service = ContentAnalyticsService(db)
    
    # If user_id is specified and it's not the current user, check admin rights
    if user_id and user_id != current_user.id:
        if current_user.role.value != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required to view other users' analytics"
            )
    
    # If no user_id specified, use current user for non-admins
    if not user_id and current_user.role.value != "admin":
        user_id = current_user.id
    
    return analytics_service.get_dashboard_analytics(user_id=user_id)


@router.post("/sync-comment-counts")
async def sync_comment_counts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Synchronize comment counts with actual comment data (admin only)."""
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    analytics_service = ContentAnalyticsService(db)
    analytics_service.sync_comment_counts()
    
    return {"message": "Comment counts synchronized successfully"}


@router.post("/cleanup-orphaned")
async def cleanup_orphaned_analytics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Remove analytics for content that no longer exists (admin only)."""
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    analytics_service = ContentAnalyticsService(db)
    orphaned_count = analytics_service.cleanup_orphaned_analytics()
    
    return {
        "message": f"Cleaned up {orphaned_count} orphaned analytics records",
        "orphaned_count": orphaned_count
    }


@router.post("/view/{content_type}/{content_id}")
async def track_content_view(
    content_type: ContentTypeEnum,
    content_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Track a content view (public endpoint for easy integration)."""
    analytics_service = ContentAnalyticsService(db)
    
    analytics_service.increment_metric(
        content_type=content_type,
        content_id=content_id,
        metric="view",
        increment=1
    )
    
    return {"message": "View tracked successfully"}


@router.post("/like/{content_type}/{content_id}")
async def track_content_like(
    content_type: ContentTypeEnum,
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Track a content like (requires authentication)."""
    analytics_service = ContentAnalyticsService(db)
    
    analytics_service.increment_metric(
        content_type=content_type,
        content_id=content_id,
        metric="like",
        increment=1
    )
    
    return {"message": "Like tracked successfully"}


@router.post("/share/{content_type}/{content_id}")
async def track_content_share(
    content_type: ContentTypeEnum,
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Track a content share (requires authentication)."""
    analytics_service = ContentAnalyticsService(db)
    
    analytics_service.increment_metric(
        content_type=content_type,
        content_id=content_id,
        metric="share",
        increment=1
    )
    
    return {"message": "Share tracked successfully"} 