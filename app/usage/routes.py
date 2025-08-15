"""
API routes for usage tracking and quota management.
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..database import get_db_session
from ..users.models import User
from .models import UserQuota
from .schemas import (
    BillingPeriodResponse,
    OperationType,
    QuotaCheckResponse,
    QuotaHistoryResponse,
    QuotaResponse,
    QuotaUpdateRequest,
    UsageFilters,
    UsageListResponse,
    UsageStatsResponse,
)
from .services import QuotaManager, UsageTracker

logger = logging.getLogger(__name__)

router = APIRouter()


# Quota Management Endpoints
@router.get(
    "/quota",
    response_model=QuotaResponse,
    summary="Get Current Quota",
    description="Get current month's quota information for the authenticated user",
)
async def get_current_quota(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get the current user's quota information."""
    try:
        quota_manager = QuotaManager(db)
        quota = await quota_manager.get_or_create_quota(current_user.id)
        
        return QuotaResponse.from_orm(quota)
        
    except Exception as e:
        logger.error(f"Error getting quota for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve quota information"
        )


@router.get(
    "/quota/{quota_month}",
    response_model=QuotaResponse,
    summary="Get Historical Quota",
    description="Get quota information for a specific month (YYYY-MM-01 format)",
)
async def get_historical_quota(
    quota_month: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get quota information for a specific month."""
    try:
        quota_manager = QuotaManager(db)
        quota = await quota_manager.get_or_create_quota(current_user.id, quota_month)
        
        return QuotaResponse.from_orm(quota)
        
    except Exception as e:
        logger.error(f"Error getting historical quota: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve quota information"
        )


@router.post(
    "/quota/check",
    response_model=QuotaCheckResponse,
    summary="Check Quota Availability",
    description="Check if user has sufficient quota for an operation",
)
async def check_quota(
    operation_type: OperationType,
    estimated_tokens: int = Query(0, ge=0, description="Estimated token usage"),
    estimated_cost: float = Query(0.0, ge=0.0, description="Estimated cost in USD"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Check if user has sufficient quota for an operation."""
    try:
        from decimal import Decimal
        
        quota_manager = QuotaManager(db)
        
        check_result = await quota_manager.check_quota_availability(
            user_id=current_user.id,
            operation_type=operation_type,
            estimated_tokens=estimated_tokens,
            estimated_cost=Decimal(str(estimated_cost)),
        )
        
        return check_result
        
    except Exception as e:
        logger.error(f"Error checking quota: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check quota availability"
        )


@router.get(
    "/quota/history",
    response_model=List[QuotaHistoryResponse],
    summary="Get Quota History",
    description="Get history of quota changes for the user",
)
async def get_quota_history(
    limit: int = Query(50, ge=1, le=500, description="Number of history records to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get quota change history for the user."""
    try:
        quota_manager = QuotaManager(db)
        history = await quota_manager.get_quota_history(current_user.id, limit)
        
        return history
        
    except Exception as e:
        logger.error(f"Error getting quota history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve quota history"
        )


@router.get(
    "/billing-period",
    response_model=BillingPeriodResponse,
    summary="Get Billing Period",
    description="Get current billing period information",
)
async def get_billing_period(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get current billing period information."""
    try:
        quota_manager = QuotaManager(db)
        period_info = await quota_manager.get_billing_period_info(current_user.id)
        
        return period_info
        
    except Exception as e:
        logger.error(f"Error getting billing period: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve billing period information"
        )


# Usage Tracking Endpoints
@router.get(
    "/records",
    response_model=UsageListResponse,
    summary="Get Usage Records",
    description="Get paginated list of usage records with filtering options",
)
async def get_usage_records(
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=1000, description="Items per page"),
    
    # Filtering
    operation_types: Optional[List[OperationType]] = Query(None, description="Filter by operation types"),
    ai_providers: Optional[List[str]] = Query(None, description="Filter by AI providers"),
    date_from: Optional[date] = Query(None, description="Start date filter"),
    date_to: Optional[date] = Query(None, description="End date filter"),
    min_cost: Optional[float] = Query(None, ge=0, description="Minimum cost filter"),
    max_cost: Optional[float] = Query(None, ge=0, description="Maximum cost filter"),
    min_tokens: Optional[int] = Query(None, ge=0, description="Minimum token filter"),
    max_tokens: Optional[int] = Query(None, ge=0, description="Maximum token filter"),
    
    # Sorting
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    
    # Dependencies
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get paginated usage records with filtering options."""
    try:
        from decimal import Decimal
        
        usage_tracker = UsageTracker(db)
        
        filters = UsageFilters(
            operation_types=operation_types,
            ai_providers=ai_providers,
            date_from=date_from,
            date_to=date_to,
            min_cost=Decimal(str(min_cost)) if min_cost else None,
            max_cost=Decimal(str(max_cost)) if max_cost else None,
            min_tokens=min_tokens,
            max_tokens=max_tokens,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        return await usage_tracker.get_usage_records(current_user.id, filters)
        
    except Exception as e:
        logger.error(f"Error getting usage records: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve usage records"
        )


@router.get(
    "/statistics",
    response_model=UsageStatsResponse,
    summary="Get Usage Statistics",
    description="Get usage statistics for a time period",
)
async def get_usage_statistics(
    date_from: Optional[date] = Query(None, description="Start date (defaults to current month)"),
    date_to: Optional[date] = Query(None, description="End date (defaults to today)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get usage statistics for the specified time period."""
    try:
        usage_tracker = UsageTracker(db)
        
        return await usage_tracker.get_usage_statistics(
            user_id=current_user.id,
            date_from=date_from,
            date_to=date_to,
        )
        
    except Exception as e:
        logger.error(f"Error getting usage statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve usage statistics"
        )


@router.get(
    "/dashboard",
    response_model=Dict,
    summary="Get Usage Dashboard Data",
    description="Get comprehensive dashboard data including quota and usage stats",
)
async def get_usage_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get comprehensive usage dashboard data."""
    try:
        quota_manager = QuotaManager(db)
        usage_tracker = UsageTracker(db)
        
        # Get current quota
        quota = await quota_manager.get_or_create_quota(current_user.id)
        
        # Get current month usage statistics
        stats = await usage_tracker.get_usage_statistics(current_user.id)
        
        # Get billing period info
        period_info = await quota_manager.get_billing_period_info(current_user.id)
        
        # Calculate usage trends (last 7 days)
        from datetime import timedelta
        
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        week_stats = await usage_tracker.get_usage_statistics(
            user_id=current_user.id,
            date_from=week_ago,
            date_to=today,
        )
        
        return {
            "quota": QuotaResponse.from_orm(quota),
            "current_period_stats": stats,
            "weekly_stats": week_stats,
            "billing_period": period_info,
            "alerts": _generate_usage_alerts(quota),
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard data"
        )


# Admin endpoints (for future implementation)
@router.put(
    "/admin/quota/{user_id}",
    response_model=QuotaResponse,
    summary="Update User Quota (Admin)",
    description="Update quota limits for a specific user (admin only)",
    include_in_schema=False,  # Hide from public API docs
)
async def admin_update_quota(
    user_id: int,
    request: QuotaUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Update quota limits for a user (admin only)."""
    # TODO: Add admin permission check
    if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        from decimal import Decimal
        
        quota_manager = QuotaManager(db)
        
        quota = await quota_manager.update_quota_limits(
            user_id=user_id,
            token_limit=request.token_limit,
            cost_limit=request.cost_limit,
            summary_limit=request.summary_limit,
            quiz_limit=request.quiz_limit,
            is_premium=request.is_premium,
            changed_by=current_user.id,
            reason=request.reason,
        )
        
        return QuotaResponse.from_orm(quota)
        
    except Exception as e:
        logger.error(f"Error updating quota for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update quota"
        )


def _generate_usage_alerts(quota: UserQuota) -> List[Dict]:
    """Generate usage alerts based on quota status."""
    alerts = []
    
    # Token usage alerts
    if quota.token_usage_percentage >= 90:
        alerts.append({
            "type": "warning" if quota.token_usage_percentage < 100 else "error",
            "category": "tokens",
            "message": f"Token usage at {quota.token_usage_percentage:.1f}%",
            "details": f"Used {quota.tokens_used:,} of {quota.token_limit:,} tokens",
        })
    elif quota.token_usage_percentage >= 75:
        alerts.append({
            "type": "info",
            "category": "tokens",
            "message": f"Token usage at {quota.token_usage_percentage:.1f}%",
            "details": f"Used {quota.tokens_used:,} of {quota.token_limit:,} tokens",
        })
    
    # Cost usage alerts
    if quota.cost_usage_percentage >= 90:
        alerts.append({
            "type": "warning" if quota.cost_usage_percentage < 100 else "error",
            "category": "cost",
            "message": f"Cost usage at {quota.cost_usage_percentage:.1f}%",
            "details": f"Used ${quota.cost_used} of ${quota.cost_limit}",
        })
    elif quota.cost_usage_percentage >= 75:
        alerts.append({
            "type": "info",
            "category": "cost",
            "message": f"Cost usage at {quota.cost_usage_percentage:.1f}%",
            "details": f"Used ${quota.cost_used} of ${quota.cost_limit}",
        })
    
    # Operation limits alerts
    if quota.summaries_used >= quota.summary_limit * 0.9:
        alerts.append({
            "type": "warning" if quota.summaries_used < quota.summary_limit else "error",
            "category": "summaries",
            "message": f"Used {quota.summaries_used} of {quota.summary_limit} summaries",
            "details": f"Summary limit {'' if quota.summaries_used < quota.summary_limit else 'exceeded'}",
        })
    
    if quota.quizzes_used >= quota.quiz_limit * 0.9:
        alerts.append({
            "type": "warning" if quota.quizzes_used < quota.quiz_limit else "error",
            "category": "quizzes",
            "message": f"Used {quota.quizzes_used} of {quota.quiz_limit} quizzes",
            "details": f"Quiz limit {'' if quota.quizzes_used < quota.quiz_limit else 'exceeded'}",
        })
    
    return alerts
