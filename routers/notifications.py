"""
Router for User Notifications.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from db_config import get_db
from core.security import get_current_user
from models.models import User
from schemas.notification import (
    NotificationRead, NotificationUpdate, NotificationListResponse, 
    NotificationMarkReadResponse
)
from services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False, description="Show only unread notifications"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's notifications with pagination."""
    notification_service = NotificationService(db)
    
    notifications, total_count, unread_count = notification_service.get_user_notifications(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        unread_only=unread_only
    )
    
    return NotificationListResponse(
        notifications=notifications,
        total_count=total_count,
        unread_count=unread_count,
        has_more=(skip + limit) < total_count
    )


@router.get("/unread-count", response_model=dict)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get count of unread notifications."""
    notification_service = NotificationService(db)
    
    _, _, unread_count = notification_service.get_user_notifications(
        user_id=current_user.id,
        skip=0,
        limit=1,
        unread_only=True
    )
    
    return {"unread_count": unread_count}


@router.put("/mark-read", response_model=NotificationMarkReadResponse)
async def mark_notifications_read(
    notification_ids: Optional[List[int]] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark notifications as read. If no IDs provided, marks all as read."""
    notification_service = NotificationService(db)
    
    updated_count = notification_service.mark_notifications_read(
        user_id=current_user.id,
        notification_ids=notification_ids
    )
    
    message = f"Marked {updated_count} notification(s) as read"
    if notification_ids is None:
        message = f"Marked all {updated_count} unread notification(s) as read"
    
    return NotificationMarkReadResponse(
        message=message,
        updated_count=updated_count
    )


@router.put("/{notification_id}", response_model=NotificationRead)
async def update_notification(
    notification_id: int,
    update_data: NotificationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a specific notification (mark as read/unread)."""
    from models.models import Notification
    from sqlalchemy.orm import joinedload
    from datetime import datetime, timezone
    
    notification = db.query(Notification).options(
        joinedload(Notification.actor_user),
        joinedload(Notification.related_community)
    ).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    # Update notification
    if update_data.is_read is not None:
        notification.is_read = update_data.is_read
        notification.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(notification)
    
    # Convert to read schema
    notification_read = NotificationRead.from_orm(notification)
    
    # Add actor details
    if notification.actor_user:
        notification_read.actor_username = notification.actor_user.username
        notification_read.actor_first_name = notification.actor_user.first_name
        notification_read.actor_last_name = notification.actor_user.last_name
    
    # Add community details
    if notification.related_community:
        notification_read.community_name = notification.related_community.name
    
    return notification_read


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a notification."""
    notification_service = NotificationService(db)
    notification_service.delete_notification(notification_id, current_user.id) 