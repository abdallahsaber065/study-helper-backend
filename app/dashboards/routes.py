"""
Dashboard and collaboration API routes for real-time features.

This module provides:
- Real-time activity tracking endpoints
- System metrics and monitoring
- Collaboration session management
- Live status dashboards
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    status, 
    Query, 
    Path,
    BackgroundTasks
)
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

import structlog

from ..auth.dependencies import get_current_user
from ..database import get_db_session
from ..users.models import User
from .models import ActivityType, CollaborationAction
from .services import (
    activity_tracker,
    metrics_collector,
    collaboration_manager,
    status_manager
)

logger = structlog.get_logger(__name__)

router = APIRouter()


# Pydantic schemas for dashboard endpoints
class ActivityLogRequest(BaseModel):
    activity_type: ActivityType
    description: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MetricRequest(BaseModel):
    metric_name: str
    value: float
    metric_type: str = "gauge"
    unit: Optional[str] = None
    category: str = "general"
    tags: Optional[Dict[str, Any]] = None


class CollaborationSessionCreate(BaseModel):
    resource_type: str
    resource_id: str
    session_name: Optional[str] = None
    is_public: bool = False
    max_participants: Optional[int] = Field(None, ge=2, le=100)
    settings: Optional[Dict[str, Any]] = None


class StatusUpdateRequest(BaseModel):
    status_type: str
    scope: str
    status: str
    scope_id: Optional[str] = None
    value: Optional[float] = None
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    expires_in_seconds: Optional[int] = Field(None, ge=1, le=86400)


# Activity Tracking Endpoints

@router.post("/activities/log")
async def log_activity(
    activity_request: ActivityLogRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, str]:
    """
    Log a user activity for tracking and analytics.
    
    This endpoint allows manual activity logging for custom events
    that aren't automatically tracked by the system.
    """
    
    try:
        activity_id = await activity_tracker.log_activity(
            user_id=current_user.id,
            activity_type=activity_request.activity_type,
            description=activity_request.description,
            resource_type=activity_request.resource_type,
            resource_id=activity_request.resource_id,
            metadata=activity_request.metadata,
            session=session
        )
        
        return {
            "message": "Activity logged successfully",
            "activity_id": activity_id
        }
        
    except Exception as e:
        logger.error(
            "Failed to log activity",
            user_id=current_user.id,
            activity_type=activity_request.activity_type,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to log activity"
        )


@router.get("/activities/recent")
async def get_recent_activities(
    activity_types: Optional[str] = Query(None, description="Comma-separated activity types"),
    resource_type: Optional[str] = Query(None, description="Resource type filter"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of activities"),
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get recent activities for the current user.
    
    Returns a list of recent activities with filtering options.
    """
    
    try:
        # Parse activity types if provided
        parsed_activity_types = None
        if activity_types:
            try:
                parsed_activity_types = [
                    ActivityType(t.strip()) 
                    for t in activity_types.split(",")
                ]
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid activity type: {str(e)}"
                )
        
        activities = await activity_tracker.get_recent_activities(
            user_id=current_user.id,
            activity_types=parsed_activity_types,
            resource_type=resource_type,
            limit=limit,
            hours=hours,
            session=session
        )
        
        # Format activities for response
        activity_data = []
        for activity in activities:
            activity_data.append({
                "id": activity.id,
                "activity_type": activity.activity_type,
                "description": activity.description,
                "resource_type": activity.resource_type,
                "resource_id": activity.resource_id,
                "metadata": activity.metadata,
                "started_at": activity.started_at.isoformat(),
                "completed_at": activity.completed_at.isoformat() if activity.completed_at else None,
                "duration_ms": activity.duration_ms,
                "success": activity.success
            })
        
        return {
            "activities": activity_data,
            "total": len(activity_data),
            "filters": {
                "activity_types": parsed_activity_types,
                "resource_type": resource_type,
                "hours": hours
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get recent activities",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve activities"
        )


# System Metrics Endpoints

@router.post("/metrics/record")
async def record_metric(
    metric_request: MetricRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, str]:
    """
    Record a system metric.
    
    This endpoint allows recording custom metrics for monitoring
    and performance tracking.
    """
    
    try:
        metric_id = await metrics_collector.record_metric(
            metric_name=metric_request.metric_name,
            value=metric_request.value,
            metric_type=metric_request.metric_type,
            unit=metric_request.unit,
            category=metric_request.category,
            tags=metric_request.tags,
            session=session
        )
        
        return {
            "message": "Metric recorded successfully",
            "metric_id": metric_id
        }
        
    except Exception as e:
        logger.error(
            "Failed to record metric",
            user_id=current_user.id,
            metric_name=metric_request.metric_name,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record metric"
        )


@router.get("/metrics")
async def get_metrics(
    metric_names: Optional[str] = Query(None, description="Comma-separated metric names"),
    category: Optional[str] = Query(None, description="Metric category filter"),
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    limit: int = Query(1000, ge=1, le=5000, description="Maximum number of metrics"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get system metrics with filtering.
    
    Returns system metrics for monitoring and analytics.
    """
    
    try:
        # Parse metric names if provided
        parsed_metric_names = None
        if metric_names:
            parsed_metric_names = [name.strip() for name in metric_names.split(",")]
        
        metrics = await metrics_collector.get_metrics(
            metric_names=parsed_metric_names,
            category=category,
            hours=hours,
            limit=limit,
            session=session
        )
        
        # Format metrics for response
        metric_data = []
        for metric in metrics:
            metric_data.append({
                "id": metric.id,
                "metric_name": metric.metric_name,
                "metric_type": metric.metric_type,
                "value": metric.value,
                "unit": metric.unit,
                "category": metric.category,
                "tags": metric.tags,
                "aggregation_period": metric.aggregation_period,
                "sample_count": metric.sample_count,
                "timestamp": metric.timestamp.isoformat()
            })
        
        return {
            "metrics": metric_data,
            "total": len(metric_data),
            "filters": {
                "metric_names": parsed_metric_names,
                "category": category,
                "hours": hours
            }
        }
        
    except Exception as e:
        logger.error(
            "Failed to get metrics",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metrics"
        )


# Collaboration Session Endpoints

@router.post("/collaboration/sessions", status_code=status.HTTP_201_CREATED)
async def create_collaboration_session(
    session_request: CollaborationSessionCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Create a new collaboration session.
    
    Creates a session for real-time collaboration on a resource
    like a file, summary, or quiz.
    """
    
    try:
        collab_session = await collaboration_manager.create_session(
            owner_id=current_user.id,
            resource_type=session_request.resource_type,
            resource_id=session_request.resource_id,
            session_name=session_request.session_name,
            is_public=session_request.is_public,
            max_participants=session_request.max_participants,
            settings=session_request.settings,
            session=session
        )
        
        return {
            "message": "Collaboration session created successfully",
            "session_id": collab_session.id,
            "session_data": {
                "id": collab_session.id,
                "resource_type": collab_session.resource_type,
                "resource_id": collab_session.resource_id,
                "session_name": collab_session.session_name,
                "is_public": collab_session.is_public,
                "max_participants": collab_session.max_participants,
                "owner_id": collab_session.owner_id,
                "created_at": collab_session.created_at.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(
            "Failed to create collaboration session",
            user_id=current_user.id,
            resource_type=session_request.resource_type,
            resource_id=session_request.resource_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create collaboration session"
        )


@router.post("/collaboration/sessions/{session_id}/join")
async def join_collaboration_session(
    session_id: str = Path(..., description="Collaboration session ID"),
    connection_id: Optional[str] = Query(None, description="WebSocket connection ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, str]:
    """
    Join an existing collaboration session.
    
    Allows a user to join a collaboration session for real-time
    collaboration features.
    """
    
    try:
        success = await collaboration_manager.join_session(
            session_id=session_id,
            user_id=current_user.id,
            connection_id=connection_id,
            session=session
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collaboration session not found or inactive"
            )
        
        return {
            "message": "Successfully joined collaboration session",
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to join collaboration session",
            user_id=current_user.id,
            session_id=session_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join collaboration session"
        )


# Live Status Endpoints

@router.post("/status/update")
async def update_live_status(
    status_request: StatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, str]:
    """
    Update live status information.
    
    Updates real-time status information for dashboards
    and monitoring.
    """
    
    try:
        status_id = await status_manager.update_status(
            status_type=status_request.status_type,
            scope=status_request.scope,
            status=status_request.status,
            scope_id=status_request.scope_id,
            value=status_request.value,
            message=status_request.message,
            data=status_request.data,
            expires_in_seconds=status_request.expires_in_seconds,
            session=session
        )
        
        return {
            "message": "Status updated successfully",
            "status_id": status_id
        }
        
    except Exception as e:
        logger.error(
            "Failed to update live status",
            user_id=current_user.id,
            status_type=status_request.status_type,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update status"
        )


# Dashboard Summary Endpoints

@router.get("/summary/user-activity")
async def get_user_activity_summary(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get user activity summary for dashboard.
    
    Provides aggregated activity data for user dashboard display.
    """
    
    try:
        hours = days * 24
        activities = await activity_tracker.get_recent_activities(
            user_id=current_user.id,
            limit=1000,
            hours=hours,
            session=session
        )
        
        # Aggregate activity data
        activity_counts = {}
        daily_counts = {}
        total_duration = 0
        successful_activities = 0
        
        for activity in activities:
            # Count by type
            activity_type = activity.activity_type
            activity_counts[activity_type] = activity_counts.get(activity_type, 0) + 1
            
            # Count by day
            day = activity.started_at.date().isoformat()
            daily_counts[day] = daily_counts.get(day, 0) + 1
            
            # Sum duration and success
            if activity.duration_ms:
                total_duration += activity.duration_ms
            if activity.success:
                successful_activities += 1
        
        return {
            "summary": {
                "total_activities": len(activities),
                "successful_activities": successful_activities,
                "success_rate": successful_activities / len(activities) if activities else 0,
                "average_duration_ms": total_duration / len(activities) if activities else 0,
                "days_analyzed": days
            },
            "activity_counts": activity_counts,
            "daily_activity": daily_counts
        }
        
    except Exception as e:
        logger.error(
            "Failed to get user activity summary",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve activity summary"
        )


@router.get("/summary/system-health")
async def get_system_health_summary(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get system health summary for dashboard.
    
    Provides current system health status and key metrics.
    """
    
    try:
        # Get recent system metrics
        metrics = await metrics_collector.get_metrics(
            category="health",
            hours=1,
            limit=100,
            session=session
        )
        
        # Aggregate health data
        health_status = "healthy"
        key_metrics = {}
        
        for metric in metrics:
            key_metrics[metric.metric_name] = {
                "value": metric.value,
                "unit": metric.unit,
                "timestamp": metric.timestamp.isoformat()
            }
            
            # Simple health determination (can be made more sophisticated)
            if metric.metric_name == "error_rate" and metric.value > 0.05:
                health_status = "warning"
            elif metric.metric_name == "response_time_ms" and metric.value > 1000:
                health_status = "warning"
        
        return {
            "health_status": health_status,
            "key_metrics": key_metrics,
            "last_updated": datetime.utcnow().isoformat(),
            "metrics_count": len(metrics)
        }
        
    except Exception as e:
        logger.error(
            "Failed to get system health summary",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system health summary"
        )


# Health check endpoint
@router.get("/health")
async def dashboard_health_check() -> Dict[str, str]:
    """
    Health check for the dashboard system.
    """
    
    return {
        "status": "healthy",
        "service": "dashboard_system",
        "timestamp": datetime.utcnow().isoformat()
    }
