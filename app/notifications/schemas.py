"""
Pydantic schemas for notification system API endpoints.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from pydantic import BaseModel, Field, validator

from .models import (
    NotificationType,
    NotificationPriority,
    DeliveryChannel,
    NotificationStatus
)


# Base schemas
class NotificationBase(BaseModel):
    """Base notification schema with common fields."""
    
    type: NotificationType
    priority: NotificationPriority = NotificationPriority.NORMAL
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    data: Optional[Dict[str, Any]] = None
    action_url: Optional[str] = Field(None, max_length=500)
    action_text: Optional[str] = Field(None, max_length=100)
    image_url: Optional[str] = Field(None, max_length=500)
    channels: List[DeliveryChannel] = Field(default=[DeliveryChannel.IN_APP])
    schedule_for: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    source_id: Optional[str] = Field(None, max_length=100)
    source_type: Optional[str] = Field(None, max_length=50)
    correlation_id: Optional[str] = Field(None, max_length=36)


class NotificationCreate(NotificationBase):
    """Schema for creating notifications."""
    
    @validator("expires_at")
    def expires_at_must_be_future(cls, v, values):
        if v and v <= datetime.utcnow():
            raise ValueError("Expiration time must be in the future")
        return v
    
    @validator("schedule_for")
    def schedule_for_validation(cls, v, values):
        if v and v <= datetime.utcnow():
            raise ValueError("Scheduled time must be in the future")
        return v


class NotificationUpdate(BaseModel):
    """Schema for updating notification status and metadata."""
    
    status: Optional[NotificationStatus] = None
    expires_at: Optional[datetime] = None
    data: Optional[Dict[str, Any]] = None


class NotificationResponse(NotificationBase):
    """Schema for notification API responses."""
    
    id: str
    user_id: int
    status: NotificationStatus
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Computed properties
    is_read: bool = False
    is_expired: bool = False
    can_retry: bool = False
    
    class Config:
        from_attributes = True
    
    def __init__(self, **data):
        super().__init__(**data)
        # Set computed properties
        self.is_read = self.status == NotificationStatus.READ or self.read_at is not None
        self.is_expired = (
            self.expires_at is not None and 
            datetime.utcnow() > self.expires_at.replace(tzinfo=None)
        ) if self.expires_at else False
        self.can_retry = (
            self.status == NotificationStatus.FAILED and 
            self.retry_count < 3  # max_retries default
        )


class NotificationList(BaseModel):
    """Schema for paginated notification lists."""
    
    notifications: List[NotificationResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class NotificationMarkRead(BaseModel):
    """Schema for marking notifications as read."""
    
    notification_ids: List[str] = Field(..., min_items=1)


class NotificationMarkDismissed(BaseModel):
    """Schema for dismissing notifications."""
    
    notification_ids: List[str] = Field(..., min_items=1)


# Notification Preferences Schemas
class NotificationPreferenceBase(BaseModel):
    """Base schema for notification preferences."""
    
    notification_type: NotificationType
    in_app_enabled: bool = True
    email_enabled: bool = True
    push_enabled: bool = True
    sms_enabled: bool = False
    quiet_hours_start: Optional[str] = Field(None, pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    quiet_hours_end: Optional[str] = Field(None, pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    timezone: Optional[str] = Field(None, max_length=50)
    digest_enabled: bool = False
    digest_frequency: Optional[str] = Field(None, pattern=r"^(hourly|daily|weekly)$")
    min_priority: NotificationPriority = NotificationPriority.LOW


class NotificationPreferenceCreate(NotificationPreferenceBase):
    """Schema for creating notification preferences."""
    pass


class NotificationPreferenceUpdate(BaseModel):
    """Schema for updating notification preferences."""
    
    in_app_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = Field(None, pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    quiet_hours_end: Optional[str] = Field(None, pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    timezone: Optional[str] = Field(None, max_length=50)
    digest_enabled: Optional[bool] = None
    digest_frequency: Optional[str] = Field(None, pattern=r"^(hourly|daily|weekly)$")
    min_priority: Optional[NotificationPriority] = None


class NotificationPreferenceResponse(NotificationPreferenceBase):
    """Schema for notification preference responses."""
    
    id: str
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class NotificationPreferencesBulkUpdate(BaseModel):
    """Schema for updating multiple notification preferences at once."""
    
    preferences: Dict[NotificationType, NotificationPreferenceUpdate]
    
    @validator("preferences")
    def validate_preferences(cls, v):
        if not v:
            raise ValueError("At least one preference must be specified")
        return v


# Push Subscription Schemas
class PushSubscriptionCreate(BaseModel):
    """Schema for creating push subscriptions."""
    
    endpoint: str = Field(..., max_length=500)
    p256dh_key: str = Field(..., max_length=200)
    auth_key: str = Field(..., max_length=50)
    user_agent: Optional[str] = Field(None, max_length=500)
    device_type: Optional[str] = Field(None, max_length=50)
    browser_name: Optional[str] = Field(None, max_length=50)
    browser_version: Optional[str] = Field(None, max_length=20)


class PushSubscriptionResponse(BaseModel):
    """Schema for push subscription responses."""
    
    id: str
    user_id: int
    endpoint: str
    device_type: Optional[str]
    browser_name: Optional[str]
    browser_version: Optional[str]
    is_active: bool
    last_used_at: Optional[datetime]
    failure_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Server-Sent Events Schemas
class SSEMessage(BaseModel):
    """Schema for Server-Sent Events messages."""
    
    event: str = "message"
    data: Dict[str, Any]
    id: Optional[str] = None
    retry: Optional[int] = None


class NotificationSSEMessage(SSEMessage):
    """Server-Sent Events message for notifications."""
    
    event: str = "notification"


class TaskProgressSSEMessage(SSEMessage):
    """Server-Sent Events message for task progress."""
    
    event: str = "task_progress"


class SystemMessageSSE(SSEMessage):
    """Server-Sent Events message for system messages."""
    
    event: str = "system_message"


# WebSocket Message Schemas
class WebSocketMessage(BaseModel):
    """Base schema for WebSocket messages."""
    
    type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class NotificationWebSocketMessage(WebSocketMessage):
    """WebSocket message for notifications."""
    
    type: str = "notification"
    notification_type: NotificationType
    message: str
    data: Optional[Dict[str, Any]] = None


class TaskProgressWebSocketMessage(WebSocketMessage):
    """WebSocket message for task progress updates."""
    
    type: str = "task_progress"
    task_id: str
    progress: int = Field(..., ge=0, le=100)
    status: str
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class SystemWebSocketMessage(WebSocketMessage):
    """WebSocket message for system messages."""
    
    type: str = "system_message"
    message: str
    data: Optional[Dict[str, Any]] = None


# Analytics and Statistics Schemas
class NotificationStats(BaseModel):
    """Schema for notification statistics."""
    
    total_notifications: int
    unread_count: int
    pending_count: int
    failed_count: int
    notifications_by_type: Dict[NotificationType, int]
    notifications_by_status: Dict[NotificationStatus, int]
    delivery_rate: float = Field(..., ge=0, le=1)
    average_read_time_minutes: Optional[float] = None


class UserActivityStats(BaseModel):
    """Schema for user activity and notification engagement."""
    
    total_received: int
    total_read: int
    total_clicked: int
    total_dismissed: int
    read_rate: float = Field(..., ge=0, le=1)
    click_through_rate: float = Field(..., ge=0, le=1)
    average_response_time_hours: Optional[float] = None
    preferred_channels: List[DeliveryChannel]


# Template Schemas
class NotificationTemplateBase(BaseModel):
    """Base schema for notification templates."""
    
    template_key: str = Field(..., max_length=100)
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    title_template: str = Field(..., max_length=255)
    message_template: str
    email_subject_template: Optional[str] = Field(None, max_length=255)
    email_html_template: Optional[str] = None
    email_text_template: Optional[str] = None
    notification_type: NotificationType
    default_priority: NotificationPriority = NotificationPriority.NORMAL
    default_channels: List[DeliveryChannel] = Field(default=[DeliveryChannel.IN_APP])
    language: str = Field(default="en", max_length=10)
    required_variables: Optional[List[str]] = None
    optional_variables: Optional[List[str]] = None
    is_active: bool = True


class NotificationTemplateCreate(NotificationTemplateBase):
    """Schema for creating notification templates."""
    pass


class NotificationTemplateUpdate(BaseModel):
    """Schema for updating notification templates."""
    
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    title_template: Optional[str] = Field(None, max_length=255)
    message_template: Optional[str] = None
    email_subject_template: Optional[str] = Field(None, max_length=255)
    email_html_template: Optional[str] = None
    email_text_template: Optional[str] = None
    default_priority: Optional[NotificationPriority] = None
    default_channels: Optional[List[DeliveryChannel]] = None
    required_variables: Optional[List[str]] = None
    optional_variables: Optional[List[str]] = None
    is_active: Optional[bool] = None


class NotificationTemplateResponse(NotificationTemplateBase):
    """Schema for notification template responses."""
    
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Bulk Operations Schemas
class BulkNotificationCreate(BaseModel):
    """Schema for creating multiple notifications at once."""
    
    notifications: List[NotificationCreate] = Field(..., min_items=1, max_items=100)
    
    @validator("notifications")
    def validate_notifications(cls, v):
        if len(v) > 100:
            raise ValueError("Cannot create more than 100 notifications at once")
        return v


class BulkOperationResult(BaseModel):
    """Schema for bulk operation results."""
    
    total_requested: int
    successful: int
    failed: int
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        if self.total_requested == 0:
            return 0.0
        return self.successful / self.total_requested
