"""
Models for live dashboards and real-time collaboration.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING
from enum import Enum

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, JSON,
    Index, UniqueConstraint, func, Float
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from ..users.models import User
    from ..files.models import FileMetadata


class ActivityType(str, Enum):
    """Types of user activities to track."""
    
    LOGIN = "login"
    LOGOUT = "logout"
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_DELETE = "file_delete"
    SUMMARY_GENERATE = "summary_generate"
    SUMMARY_VIEW = "summary_view"
    QUIZ_GENERATE = "quiz_generate"
    QUIZ_ATTEMPT = "quiz_attempt"
    QUIZ_COMPLETE = "quiz_complete"
    WEBSOCKET_CONNECT = "websocket_connect"
    WEBSOCKET_DISCONNECT = "websocket_disconnect"
    API_REQUEST = "api_request"


class CollaborationAction(str, Enum):
    """Types of collaboration actions."""
    
    FILE_SHARE = "file_share"
    FILE_UNSHARE = "file_unshare"
    COMMENT_ADD = "comment_add"
    COMMENT_EDIT = "comment_edit"
    COMMENT_DELETE = "comment_delete"
    MENTION = "mention"
    VIEW_JOIN = "view_join"
    VIEW_LEAVE = "view_leave"


class UserActivity(Base):
    """
    Track user activities for real-time dashboards and analytics.
    
    Records all user actions for system monitoring, analytics,
    and security auditing.
    """
    
    __tablename__ = "user_activities"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # User relationship
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Activity details
    activity_type: Mapped[ActivityType] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Context and metadata
    resource_type: Mapped[Optional[str]] = mapped_column(String(50))  # file, summary, quiz, etc.
    resource_id: Mapped[Optional[str]] = mapped_column(String(100))   # ID of the resource
    activity_metadata: Mapped[Optional[Dict]] = mapped_column(JSON)  # Additional context data
    
    # Request/session information
    session_id: Mapped[Optional[str]] = mapped_column(String(100))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Performance metrics
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)       # Duration for completed activities
    success: Mapped[bool] = mapped_column(Boolean, default=True)     # Whether the activity succeeded
    error_message: Mapped[Optional[str]] = mapped_column(Text)       # Error details if failed
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False,
        index=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="activities")
    
    # Database constraints and indexes
    __table_args__ = (
        Index("idx_user_activities_user_type", "user_id", "activity_type"),
        Index("idx_user_activities_started_at", "started_at"),
        Index("idx_user_activities_resource", "resource_type", "resource_id"),
        Index("idx_user_activities_session", "session_id"),
    )
    
    def mark_completed(self, success: bool = True, error_message: Optional[str] = None) -> None:
        """Mark the activity as completed."""
        self.completed_at = datetime.utcnow()
        self.success = success
        if error_message:
            self.error_message = error_message
        
        if self.completed_at and self.started_at:
            self.duration_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)


class SystemMetric(Base):
    """
    Store system-wide metrics for real-time monitoring.
    
    Tracks performance, usage, and health metrics across
    the entire platform.
    """
    
    __tablename__ = "system_metrics"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Metric identification
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)  # counter, gauge, histogram
    
    # Metric values
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(20))  # requests/sec, bytes, percent, etc.
    
    # Categorization and tags
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # performance, usage, health
    tags: Mapped[Optional[Dict]] = mapped_column(JSON)  # Additional categorization
    
    # Aggregation info
    aggregation_period: Mapped[Optional[str]] = mapped_column(String(20))  # 1m, 5m, 1h, 1d
    sample_count: Mapped[Optional[int]] = mapped_column(Integer)  # For averaged metrics
    
    # Timestamps
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False,
        index=True
    )
    
    # Database constraints and indexes
    __table_args__ = (
        Index("idx_system_metrics_name_timestamp", "metric_name", "timestamp"),
        Index("idx_system_metrics_category_timestamp", "category", "timestamp"),
        Index("idx_system_metrics_type", "metric_type"),
    )


class CollaborationSession(Base):
    """
    Track collaborative sessions for shared files and resources.
    
    Enables real-time collaboration features like shared viewing,
    comments, and live cursor tracking.
    """
    
    __tablename__ = "collaboration_sessions"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Resource being collaborated on
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)  # file, summary, quiz
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Session details
    session_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    # Access control
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_permission: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Owner and participants
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    max_participants: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Session metadata
    settings: Mapped[Optional[Dict]] = mapped_column(JSON)  # Session-specific settings
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="owned_collaboration_sessions")
    participants: Mapped[List["CollaborationParticipant"]] = relationship(
        "CollaborationParticipant", back_populates="session", cascade="all, delete-orphan"
    )
    activities: Mapped[List["CollaborationActivity"]] = relationship(
        "CollaborationActivity", back_populates="session", cascade="all, delete-orphan"
    )
    
    # Database constraints and indexes
    __table_args__ = (
        Index("idx_collaboration_sessions_resource", "resource_type", "resource_id"),
        Index("idx_collaboration_sessions_owner", "owner_id"),
        Index("idx_collaboration_sessions_active", "is_active"),
    )


class CollaborationParticipant(Base):
    """
    Track participants in collaboration sessions.
    """
    
    __tablename__ = "collaboration_participants"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Session and user relationships
    session_id: Mapped[str] = mapped_column(ForeignKey("collaboration_sessions.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    # Participation details
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # owner, editor, viewer
    permissions: Mapped[List[str]] = mapped_column(JSON, default=lambda: ["read"])  # read, write, comment
    
    # Session state
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_activity: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Cursor and viewport tracking for real-time collaboration
    cursor_position: Mapped[Optional[Dict]] = mapped_column(JSON)  # Current cursor position
    viewport: Mapped[Optional[Dict]] = mapped_column(JSON)         # Current viewport/scroll position
    
    # Connection info
    connection_id: Mapped[Optional[str]] = mapped_column(String(100))  # WebSocket connection ID
    
    # Timestamps
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    session: Mapped["CollaborationSession"] = relationship(
        "CollaborationSession", back_populates="participants"
    )
    user: Mapped["User"] = relationship("User", back_populates="collaboration_participations")
    
    # Database constraints and indexes
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_session_user"),
        Index("idx_collaboration_participants_session", "session_id"),
        Index("idx_collaboration_participants_user", "user_id"),
        Index("idx_collaboration_participants_online", "is_online"),
    )


class CollaborationActivity(Base):
    """
    Track activities within collaboration sessions.
    """
    
    __tablename__ = "collaboration_activities"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Session and user relationships
    session_id: Mapped[str] = mapped_column(ForeignKey("collaboration_sessions.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    # Activity details
    action: Mapped[CollaborationAction] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Activity data
    data: Mapped[Optional[Dict]] = mapped_column(JSON)  # Action-specific data
    
    # Timestamps
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False,
        index=True
    )
    
    # Relationships
    session: Mapped["CollaborationSession"] = relationship(
        "CollaborationSession", back_populates="activities"
    )
    user: Mapped["User"] = relationship("User", back_populates="collaboration_activities")
    
    # Database constraints and indexes
    __table_args__ = (
        Index("idx_collaboration_activities_session", "session_id"),
        Index("idx_collaboration_activities_user", "user_id"),
        Index("idx_collaboration_activities_timestamp", "timestamp"),
    )


class LiveStatus(Base):
    """
    Store live status information for real-time dashboards.
    
    Provides current system state, active users, and
    real-time statistics for monitoring dashboards.
    """
    
    __tablename__ = "live_status"
    
    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Status type and scope
    status_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)  # system, user, resource
    scope_id: Mapped[Optional[str]] = mapped_column(String(100))    # ID within scope
    
    # Status data
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # healthy, warning, error, etc.
    value: Mapped[Optional[float]] = mapped_column(Float)            # Numeric status value
    message: Mapped[Optional[str]] = mapped_column(String(500))      # Status message
    data: Mapped[Optional[Dict]] = mapped_column(JSON)              # Additional status data
    
    # Timestamps and expiry
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False,
        index=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Database constraints and indexes
    __table_args__ = (
        Index("idx_live_status_type_scope", "status_type", "scope"),
        Index("idx_live_status_scope_id", "scope", "scope_id"),
        Index("idx_live_status_expires", "expires_at"),
    )
    
    def is_expired(self) -> bool:
        """Check if the status has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at.replace(tzinfo=None)
    
    def update_status(
        self, 
        status: str, 
        value: Optional[float] = None, 
        message: Optional[str] = None,
        data: Optional[Dict] = None
    ) -> None:
        """Update the status information."""
        self.status = status
        if value is not None:
            self.value = value
        if message is not None:
            self.message = message
        if data is not None:
            self.data = data
        self.last_updated = datetime.utcnow()
