"""
Pydantic schemas for Notifications.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from models.models import NotificationTypeEnum, ContentTypeEnum


# Base schemas
class NotificationBase(BaseModel):
    notification_type: NotificationTypeEnum
    message: str = Field(..., min_length=1, max_length=500)
    related_content_type: Optional[ContentTypeEnum] = None
    related_content_id: Optional[int] = None
    related_community_id: Optional[int] = None


class NotificationCreate(NotificationBase):
    user_id: int  # Recipient
    actor_id: Optional[int] = None  # User who triggered the notification


class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None


class NotificationRead(NotificationBase):
    id: int
    user_id: int
    actor_id: Optional[int]
    is_read: bool
    created_at: datetime
    updated_at: datetime
    
    # Actor details (populated by router)
    actor_username: Optional[str] = None
    actor_first_name: Optional[str] = None
    actor_last_name: Optional[str] = None
    
    # Community details (if applicable)
    community_name: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Response model for notification listing."""
    notifications: List[NotificationRead]
    total_count: int
    unread_count: int
    has_more: bool


class NotificationMarkReadResponse(BaseModel):
    """Response model for marking notifications as read."""
    message: str
    updated_count: int 