"""
Notification system models for comprehensive user communication.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING
from enum import Enum

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, JSON,
    Index, UniqueConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from ..users.models import User


class NotificationType(str, Enum):
    """Types of notifications that can be sent."""
    
    # Task-related notifications
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    
    # Summary notifications
    SUMMARY_GENERATED = "summary_generated"
    SUMMARY_FAILED = "summary_failed"
    SUMMARY_UPDATED = "summary_updated"
    
    # Quiz notifications
    QUIZ_GENERATED = "quiz_generated"
    QUIZ_FAILED = "quiz_failed"
    QUIZ_COMPLETED = "quiz_completed"
    QUIZ_ATTEMPT_STARTED = "quiz_attempt_started"
    QUIZ_ATTEMPT_COMPLETED = "quiz_attempt_completed"
    
    # System notifications
    SYSTEM_MAINTENANCE = "system_maintenance"
    SYSTEM_UPDATE = "system_update"
    SYSTEM_ALERT = "system_alert"
    
    # Account notifications
    ACCOUNT_VERIFICATION = "account_verification"
    PASSWORD_RESET = "password_reset"
    ACCOUNT_SECURITY = "account_security"
    
    # Usage notifications
    QUOTA_WARNING = "quota_warning"
    QUOTA_EXCEEDED = "quota_exceeded"
    USAGE_REPORT = "usage_report"
    
    # Collaboration notifications
    FILE_SHARED = "file_shared"
    COMMENT_ADDED = "comment_added"
    MENTION = "mention"


class NotificationPriority(str, Enum):
    """Priority levels for notifications."""
    
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class DeliveryChannel(str, Enum):
    """Channels through which notifications can be delivered."""
    
    IN_APP = "in_app"           # WebSocket/real-time in application
    EMAIL = "email"             # Email notification
    PUSH = "push"               # Browser push notification
    SMS = "sms"                 # SMS (future feature)
    WEBHOOK = "webhook"         # Webhook delivery (future feature)


class NotificationStatus(str, Enum):
    """Status of notification delivery."""
    
    PENDING = "pending"         # Not yet sent
    SENT = "sent"              # Successfully sent
    DELIVERED = "delivered"     # Confirmed delivery
    READ = "read"              # User has read the notification
    FAILED = "failed"          # Failed to send
    DISMISSED = "dismissed"     # User dismissed notification
    EXPIRED = "expired"        # Notification expired


class Notification(Base):
    """
    Comprehensive notification model for all user communications.
    
    Handles in-app notifications, email notifications, push notifications,
    and tracks delivery status, user interactions, and analytics.
    """
    
    __tablename__ = "notifications"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # User relationship
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Notification metadata
    type: Mapped[NotificationType] = mapped_column(String(50), nullable=False, index=True)
    priority: Mapped[NotificationPriority] = mapped_column(
        String(20), 
        nullable=False, 
        default=NotificationPriority.NORMAL,
        index=True
    )
    
    # Content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Rich content and actions
    data: Mapped[Optional[Dict]] = mapped_column(JSON)  # Additional structured data
    action_url: Mapped[Optional[str]] = mapped_column(String(500))  # URL for notification action
    action_text: Mapped[Optional[str]] = mapped_column(String(100))  # Text for action button
    image_url: Mapped[Optional[str]] = mapped_column(String(500))  # Image for rich notifications
    
    # Delivery configuration
    channels: Mapped[List[str]] = mapped_column(JSON, default=lambda: ["in_app"])  # Delivery channels
    schedule_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # Scheduled delivery
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # Expiration time
    
    # Status tracking
    status: Mapped[NotificationStatus] = mapped_column(
        String(20), 
        nullable=False, 
        default=NotificationStatus.PENDING,
        index=True
    )
    
    # Interaction tracking
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    
    # Context tracking
    source_id: Mapped[Optional[str]] = mapped_column(String(100))  # ID of related entity (task, summary, etc.)
    source_type: Mapped[Optional[str]] = mapped_column(String(50))  # Type of related entity
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36))  # For tracking related notifications
    
    # Analytics
    device_type: Mapped[Optional[str]] = mapped_column(String(50))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        onupdate=func.now()
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notifications")
    
    # Database constraints and indexes
    __table_args__ = (
        Index("idx_notifications_user_status", "user_id", "status"),
        Index("idx_notifications_user_type", "user_id", "type"),
        Index("idx_notifications_created_at", "created_at"),
        Index("idx_notifications_schedule", "schedule_for"),
        Index("idx_notifications_expires", "expires_at"),
    )
    
    def is_read(self) -> bool:
        """Check if notification has been read."""
        return self.status == NotificationStatus.READ or self.read_at is not None
    
    def is_expired(self) -> bool:
        """Check if notification has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at.replace(tzinfo=None)
    
    def can_retry(self) -> bool:
        """Check if notification can be retried."""
        return (
            self.status == NotificationStatus.FAILED and 
            self.retry_count < self.max_retries
        )
    
    def mark_as_read(self) -> None:
        """Mark notification as read."""
        if not self.is_read():
            self.status = NotificationStatus.READ
            self.read_at = datetime.utcnow()
    
    def mark_as_dismissed(self) -> None:
        """Mark notification as dismissed."""
        self.status = NotificationStatus.DISMISSED
        self.dismissed_at = datetime.utcnow()
    
    def mark_as_clicked(self) -> None:
        """Mark notification as clicked (also marks as read)."""
        self.clicked_at = datetime.utcnow()
        if not self.is_read():
            self.mark_as_read()


class NotificationPreference(Base):
    """
    User preferences for notification delivery and types.
    
    Allows users to configure which notifications they want to receive
    and through which channels.
    """
    
    __tablename__ = "notification_preferences"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # User relationship
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Notification type preference
    notification_type: Mapped[NotificationType] = mapped_column(String(50), nullable=False)
    
    # Channel preferences
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timing preferences
    quiet_hours_start: Mapped[Optional[str]] = mapped_column(String(5))  # HH:MM format
    quiet_hours_end: Mapped[Optional[str]] = mapped_column(String(5))    # HH:MM format
    timezone: Mapped[Optional[str]] = mapped_column(String(50))          # e.g., "America/New_York"
    
    # Frequency preferences
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False)  # Bundle notifications
    digest_frequency: Mapped[Optional[str]] = mapped_column(String(20))   # hourly, daily, weekly
    
    # Priority thresholds
    min_priority: Mapped[NotificationPriority] = mapped_column(
        String(20), 
        default=NotificationPriority.LOW
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        onupdate=func.now()
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notification_preferences")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_user_notification_type"),
        Index("idx_notification_preferences_user", "user_id"),
    )


class PushSubscription(Base):
    """
    Web Push API subscriptions for browser push notifications.
    
    Stores the subscription data needed to send push notifications
    to user devices via the Web Push Protocol.
    """
    
    __tablename__ = "push_subscriptions"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # User relationship
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Push subscription data (from browser's PushManager.subscribe())
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    p256dh_key: Mapped[str] = mapped_column(String(200), nullable=False)  # Public key
    auth_key: Mapped[str] = mapped_column(String(50), nullable=False)     # Auth secret
    
    # Device/browser information
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    device_type: Mapped[Optional[str]] = mapped_column(String(50))  # desktop, mobile, tablet
    browser_name: Mapped[Optional[str]] = mapped_column(String(50))
    browser_version: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Status and settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        onupdate=func.now()
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="push_subscriptions")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
        Index("idx_push_subscriptions_user", "user_id"),
        Index("idx_push_subscriptions_active", "is_active"),
    )


class NotificationTemplate(Base):
    """
    Templates for generating consistent notification content.
    
    Provides reusable templates with placeholders for dynamic content,
    supporting multiple languages and customization.
    """
    
    __tablename__ = "notification_templates"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Template identification
    template_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Template content
    title_template: Mapped[str] = mapped_column(String(255), nullable=False)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Email-specific templates
    email_subject_template: Mapped[Optional[str]] = mapped_column(String(255))
    email_html_template: Mapped[Optional[str]] = mapped_column(Text)
    email_text_template: Mapped[Optional[str]] = mapped_column(Text)
    
    # Configuration
    notification_type: Mapped[NotificationType] = mapped_column(String(50), nullable=False)
    default_priority: Mapped[NotificationPriority] = mapped_column(
        String(20), 
        default=NotificationPriority.NORMAL
    )
    default_channels: Mapped[List[str]] = mapped_column(JSON, default=lambda: ["in_app"])
    
    # Localization
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    
    # Template variables documentation
    required_variables: Mapped[Optional[List[str]]] = mapped_column(JSON)  # List of required variables
    optional_variables: Mapped[Optional[List[str]]] = mapped_column(JSON)  # List of optional variables
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        onupdate=func.now()
    )
    
    # Constraints
    __table_args__ = (
        Index("idx_notification_templates_type", "notification_type"),
        Index("idx_notification_templates_active", "is_active"),
        Index("idx_notification_templates_language", "language"),
    )
    
    def render_title(self, variables: Dict[str, any]) -> str:
        """Render title template with provided variables."""
        return self.title_template.format(**variables)
    
    def render_message(self, variables: Dict[str, any]) -> str:
        """Render message template with provided variables."""
        return self.message_template.format(**variables)
    
    def render_email_subject(self, variables: Dict[str, any]) -> Optional[str]:
        """Render email subject template with provided variables."""
        if self.email_subject_template:
            return self.email_subject_template.format(**variables)
        return None
