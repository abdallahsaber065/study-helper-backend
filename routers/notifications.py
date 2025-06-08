"""
Router for Notifications.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from db_config import get_async_db
from core.security import get_current_user
from models.models import User, Notification, NotificationTypeEnum
from schemas.notification import (
    NotificationRead, NotificationUpdate, NotificationListResponse
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    notification_type: Optional[NotificationTypeEnum] = Query(None, description="Filter by notification type"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get user's notifications with optional filtering."""
    stmt = select(Notification).options(
        selectinload(Notification.actor_user),
        selectinload(Notification.related_community)
    ).where(Notification.user_id == current_user.id)
    
    # Apply filters
    if is_read is not None:
        stmt = stmt.where(Notification.is_read == is_read)
    
    if notification_type:
        stmt = stmt.where(Notification.notification_type == notification_type)
    
    # Get total count
    count_stmt = select(func.count(Notification.id)).where(Notification.user_id == current_user.id)
    if is_read is not None:
        count_stmt = count_stmt.where(Notification.is_read == is_read)
    if notification_type:
        count_stmt = count_stmt.where(Notification.notification_type == notification_type)
    
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar()
    
    # Apply pagination and ordering
    stmt = stmt.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    
    return NotificationListResponse(
        notifications=[NotificationRead.from_orm(notif) for notif in notifications],
        total_count=total_count,
        unread_count=0,  # Will be calculated separately if needed
        has_more=(skip + limit) < total_count
    )


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get count of unread notifications."""
    stmt = select(func.count(Notification.id)).where(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    )
    result = await db.execute(stmt)
    unread_count = result.scalar()
    
    return {"unread_count": unread_count}


@router.put("/{notification_id}/mark-read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Mark a specific notification as read."""
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    )
    result = await db.execute(stmt)
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    
    return NotificationRead.from_orm(notification)


@router.put("/mark-all-read")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Mark all user notifications as read."""
    stmt = update(Notification).where(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).values(is_read=True)
    
    result = await db.execute(stmt)
    await db.commit()
    
    return {
        "message": f"Marked {result.rowcount} notifications as read",
        "updated_count": result.rowcount
    }


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a specific notification."""
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    )
    result = await db.execute(stmt)
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    await db.delete(notification)
    await db.commit()
    
    return {"message": "Notification deleted successfully"} 