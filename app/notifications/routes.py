"""
Notification system API routes for comprehensive user communication.

This module provides:
- Notification management endpoints
- Server-sent events (SSE) for real-time updates
- Push notification subscription management
- Notification preferences configuration
- Analytics and reporting endpoints
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, AsyncGenerator
from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    status, 
    Query, 
    Body,
    BackgroundTasks,
    Request
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from ..auth.dependencies import get_current_user
from ..database import get_db_session
from ..users.models import User
from .models import NotificationType, NotificationStatus, NotificationPriority
from .schemas import (
    NotificationCreate,
    NotificationUpdate,
    NotificationResponse,
    NotificationList,
    NotificationMarkRead,
    NotificationMarkDismissed,
    NotificationStats,
    NotificationPreferenceCreate,
    NotificationPreferenceUpdate,
    NotificationPreferenceResponse,
    NotificationPreferencesBulkUpdate,
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    BulkNotificationCreate,
    BulkOperationResult,
    SSEMessage
)
from .services import notification_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# Notification Management Endpoints

@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def create_notification(
    notification_data: NotificationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> NotificationResponse:
    """
    Create a new notification.
    
    This endpoint allows creating notifications for the current user.
    Notifications will be delivered through the specified channels.
    """
    
    try:
        notification = await notification_service.create_notification(
            user_id=current_user.id,
            notification_data=notification_data,
            session=session
        )
        
        logger.info(
            "Notification created via API",
            notification_id=notification.id,
            user_id=current_user.id,
            type=notification_data.type
        )
        
        return notification
        
    except Exception as e:
        logger.error(
            "Failed to create notification",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create notification"
        )


@router.post("/bulk", response_model=BulkOperationResult)
async def create_bulk_notifications(
    bulk_data: BulkNotificationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> BulkOperationResult:
    """
    Create multiple notifications in bulk.
    
    Useful for batch operations like sending notifications to multiple users
    or creating multiple related notifications.
    """
    
    successful = 0
    failed = 0
    errors = []
    
    for i, notification_data in enumerate(bulk_data.notifications):
        try:
            await notification_service.create_notification(
                user_id=current_user.id,
                notification_data=notification_data,
                session=session
            )
            successful += 1
            
        except Exception as e:
            failed += 1
            errors.append({
                "index": i,
                "notification": notification_data.dict(),
                "error": str(e)
            })
    
    logger.info(
        "Bulk notification creation completed",
        user_id=current_user.id,
        total=len(bulk_data.notifications),
        successful=successful,
        failed=failed
    )
    
    return BulkOperationResult(
        total_requested=len(bulk_data.notifications),
        successful=successful,
        failed=failed,
        errors=errors
    )


@router.get("", response_model=NotificationList)
async def get_notifications(
    status_filter: Optional[NotificationStatus] = Query(None, description="Filter by notification status"),
    type_filter: Optional[NotificationType] = Query(None, description="Filter by notification type"),
    include_read: bool = Query(True, description="Include read notifications"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> NotificationList:
    """
    Get user's notifications with filtering and pagination.
    
    Returns a paginated list of notifications for the current user.
    Supports filtering by status, type, and read status.
    """
    
    try:
        offset = (page - 1) * per_page
        
        notifications, total = await notification_service.get_user_notifications(
            user_id=current_user.id,
            status_filter=status_filter,
            type_filter=type_filter,
            limit=per_page,
            offset=offset,
            include_read=include_read,
            session=session
        )
        
        has_next = offset + per_page < total
        has_prev = page > 1
        
        return NotificationList(
            notifications=notifications,
            total=total,
            page=page,
            per_page=per_page,
            has_next=has_next,
            has_prev=has_prev
        )
        
    except Exception as e:
        logger.error(
            "Failed to get notifications",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve notifications"
        )


@router.get("/unread/count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, int]:
    """
    Get count of unread notifications for the current user.
    
    Useful for displaying notification badges in the UI.
    """
    
    try:
        notifications, total = await notification_service.get_user_notifications(
            user_id=current_user.id,
            include_read=False,
            limit=1,  # We only need the count
            offset=0,
            session=session
        )
        
        return {"unread_count": total}
        
    except Exception as e:
        logger.error(
            "Failed to get unread count",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unread count"
        )


@router.put("/read", status_code=status.HTTP_200_OK)
async def mark_notifications_read(
    data: NotificationMarkRead,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Mark notifications as read.
    
    Accepts a list of notification IDs to mark as read.
    """
    
    try:
        updated_count = await notification_service.mark_notifications_read(
            user_id=current_user.id,
            notification_ids=data.notification_ids,
            session=session
        )
        
        return {
            "message": f"Marked {updated_count} notifications as read",
            "updated_count": updated_count,
            "requested_count": len(data.notification_ids)
        }
        
    except Exception as e:
        logger.error(
            "Failed to mark notifications as read",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notifications as read"
        )


@router.put("/dismiss", status_code=status.HTTP_200_OK)
async def dismiss_notifications(
    data: NotificationMarkDismissed,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Dismiss notifications.
    
    Dismissed notifications are hidden from the user's notification list.
    """
    
    try:
        updated_count = await notification_service.dismiss_notifications(
            user_id=current_user.id,
            notification_ids=data.notification_ids,
            session=session
        )
        
        return {
            "message": f"Dismissed {updated_count} notifications",
            "updated_count": updated_count,
            "requested_count": len(data.notification_ids)
        }
        
    except Exception as e:
        logger.error(
            "Failed to dismiss notifications",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dismiss notifications"
        )


@router.put("/read/all", status_code=status.HTTP_200_OK)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Mark all unread notifications as read for the current user.
    """
    
    try:
        # Get all unread notification IDs
        notifications, _ = await notification_service.get_user_notifications(
            user_id=current_user.id,
            include_read=False,
            limit=1000,  # Large limit to get all unread
            offset=0,
            session=session
        )
        
        if not notifications:
            return {"message": "No unread notifications to mark as read", "updated_count": 0}
        
        notification_ids = [n.id for n in notifications]
        
        updated_count = await notification_service.mark_notifications_read(
            user_id=current_user.id,
            notification_ids=notification_ids,
            session=session
        )
        
        return {
            "message": f"Marked all {updated_count} notifications as read",
            "updated_count": updated_count
        }
        
    except Exception as e:
        logger.error(
            "Failed to mark all notifications as read",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark all notifications as read"
        )


# Server-Sent Events (SSE) Endpoints

@router.get("/stream")
async def notification_stream(
    current_user: User = Depends(get_current_user),
    request: Request = None
) -> StreamingResponse:
    """
    Server-Sent Events (SSE) endpoint for real-time notifications.
    
    Provides a continuous stream of notifications and updates
    for the authenticated user.
    """
    
    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events for the user."""
        
        logger.info(
            "SSE connection established",
            user_id=current_user.id
        )
        
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
        
        try:
            while True:
                # Check if client disconnected
                if request and await request.is_disconnected():
                    logger.info(
                        "SSE client disconnected",
                        user_id=current_user.id
                    )
                    break
                
                # Send heartbeat every 30 seconds
                heartbeat_data = {
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat(),
                    "user_id": current_user.id
                }
                
                yield f"data: {json.dumps(heartbeat_data)}\n\n"
                
                # Wait before next heartbeat
                await asyncio.sleep(30)
                
        except Exception as e:
            logger.error(
                "SSE stream error",
                user_id=current_user.id,
                error=str(e)
            )
        finally:
            logger.info(
                "SSE connection closed",
                user_id=current_user.id
            )
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*"
        }
    )


# Push Notification Subscription Endpoints

@router.post("/push/subscribe", response_model=PushSubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def subscribe_push_notifications(
    subscription_data: PushSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> PushSubscriptionResponse:
    """
    Subscribe to web push notifications.
    
    Creates a push subscription for the current user's device/browser.
    """
    
    try:
        from .push_service import push_notification_service
        
        subscription = await push_notification_service.create_subscription(
            user_id=current_user.id,
            subscription_data=subscription_data,
            session=session
        )
        
        logger.info(
            "Push subscription created",
            user_id=current_user.id,
            subscription_id=subscription.id
        )
        
        return subscription
        
    except Exception as e:
        logger.error(
            "Failed to create push subscription",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create push subscription"
        )


@router.get("/push/subscriptions", response_model=List[PushSubscriptionResponse])
async def get_push_subscriptions(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> List[PushSubscriptionResponse]:
    """
    Get user's push notification subscriptions.
    """
    
    try:
        from .push_service import push_notification_service
        
        subscriptions = await push_notification_service.get_user_subscriptions(
            user_id=current_user.id,
            active_only=True,
            session=session
        )
        
        return subscriptions
        
    except Exception as e:
        logger.error(
            "Failed to get push subscriptions",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve push subscriptions"
        )


@router.delete("/push/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_push_notifications(
    subscription_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Unsubscribe from push notifications.
    
    Removes a specific push subscription.
    """
    
    try:
        from .push_service import push_notification_service
        
        success = await push_notification_service.delete_subscription(
            subscription_id=subscription_id,
            user_id=current_user.id,
            session=session
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Push subscription not found"
            )
        
        logger.info(
            "Push subscription deleted",
            user_id=current_user.id,
            subscription_id=subscription_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete push subscription",
            user_id=current_user.id,
            subscription_id=subscription_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete push subscription"
        )


@router.post("/push/test/{subscription_id}")
async def test_push_subscription(
    subscription_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Send a test push notification to verify the subscription works.
    """
    
    try:
        from .push_service import push_notification_service
        
        success = await push_notification_service.test_subscription(
            subscription_id=subscription_id,
            user_id=current_user.id,
            session=session
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Push subscription not found or inactive"
            )
        
        return {"message": "Test notification sent successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to send test push notification",
            user_id=current_user.id,
            subscription_id=subscription_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send test notification"
        )


@router.get("/push/vapid-public-key")
async def get_vapid_public_key() -> Dict[str, Optional[str]]:
    """
    Get the VAPID public key for client-side push subscription.
    """
    
    try:
        from .push_service import push_notification_service
        
        public_key = push_notification_service.get_vapid_public_key()
        
        return {"public_key": public_key}
        
    except Exception as e:
        logger.error(
            "Failed to get VAPID public key",
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get VAPID public key"
        )


# Analytics and Statistics Endpoints

@router.get("/stats", response_model=NotificationStats)
async def get_notification_statistics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> NotificationStats:
    """
    Get notification statistics and analytics.
    
    Provides insights into notification delivery, read rates, and user engagement.
    """
    
    try:
        stats = await notification_service.get_notification_stats(
            user_id=current_user.id,
            days=days,
            session=session
        )
        
        return stats
        
    except Exception as e:
        logger.error(
            "Failed to get notification statistics",
            user_id=current_user.id,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve notification statistics"
        )


# Admin and System Endpoints

@router.post("/system/process-scheduled")
async def process_scheduled_notifications(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Process scheduled notifications (admin endpoint).
    
    Manually trigger processing of notifications scheduled for delivery.
    """
    
    # TODO: Add admin role check
    # For now, any authenticated user can trigger this
    
    async def process_task():
        try:
            processed_count = await notification_service.process_scheduled_notifications(session)
            logger.info(
                "Scheduled notifications processed",
                processed_count=processed_count,
                triggered_by=current_user.id
            )
        except Exception as e:
            logger.error(
                "Failed to process scheduled notifications",
                error=str(e)
            )
    
    background_tasks.add_task(process_task)
    
    return {"message": "Scheduled notification processing started"}


@router.post("/system/cleanup-expired")
async def cleanup_expired_notifications(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Clean up expired notifications (admin endpoint).
    
    Manually trigger cleanup of expired notifications.
    """
    
    # TODO: Add admin role check
    
    async def cleanup_task():
        try:
            cleaned_count = await notification_service.cleanup_expired_notifications(session)
            logger.info(
                "Expired notifications cleaned up",
                cleaned_count=cleaned_count,
                triggered_by=current_user.id
            )
        except Exception as e:
            logger.error(
                "Failed to clean up expired notifications",
                error=str(e)
            )
    
    background_tasks.add_task(cleanup_task)
    
    return {"message": "Expired notification cleanup started"}


# Preference Management Endpoints (to be implemented in preferences.py if needed)
# These would handle user notification preferences, but for now they're part of this module

@router.get("/preferences", response_model=List[NotificationPreferenceResponse])
async def get_notification_preferences(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> List[NotificationPreferenceResponse]:
    """
    Get user's notification preferences.
    """
    
    from .services import get_user_notification_preferences
    
    preferences = await get_user_notification_preferences(current_user.id, session)
    return [NotificationPreferenceResponse.model_validate(pref) for pref in preferences]


@router.put("/preferences", response_model=List[NotificationPreferenceResponse])
async def update_notification_preferences(
    preferences_data: NotificationPreferencesBulkUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> List[NotificationPreferenceResponse]:
    """
    Update user's notification preferences.
    
    Allows bulk updating of notification preferences for different types.
    """
    
    from .services import update_user_notification_preferences
    
    preferences = await update_user_notification_preferences(
        current_user.id, 
        preferences_data.preferences, 
        session
    )
    return [NotificationPreferenceResponse.model_validate(pref) for pref in preferences]


# Health check endpoint
@router.get("/health")
async def notification_health_check() -> Dict[str, str]:
    """
    Health check for the notification system.
    """
    
    return {
        "status": "healthy",
        "service": "notification_system",
        "timestamp": datetime.utcnow().isoformat()
    }
