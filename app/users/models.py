"""User model definitions."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.files.models import FileMetadata
    from app.summaries.models import Summary
    from app.usage.models import UserQuota, UsageRecord
    from app.quizzes.models import Quiz, QuizAttempt
    from app.notifications.models import Notification, NotificationPreference, PushSubscription
    from app.dashboards.models import (
        UserActivity, CollaborationSession, CollaborationParticipant, CollaborationActivity
    )


class User(Base):
    """User model for authentication and user management."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    files: Mapped[List["FileMetadata"]] = relationship(
        "FileMetadata", back_populates="user", cascade="all, delete-orphan"
    )
    summaries: Mapped[List["Summary"]] = relationship(
        "Summary", back_populates="user", cascade="all, delete-orphan"
    )
    quotas: Mapped[List["UserQuota"]] = relationship(
        "UserQuota", back_populates="user", cascade="all, delete-orphan"
    )
    usage_records: Mapped[List["UsageRecord"]] = relationship(
        "UsageRecord", back_populates="user", cascade="all, delete-orphan"
    )
    quizzes: Mapped[List["Quiz"]] = relationship(
        "Quiz", back_populates="user", cascade="all, delete-orphan"
    )
    quiz_attempts: Mapped[List["QuizAttempt"]] = relationship(
        "QuizAttempt", back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    notification_preferences: Mapped[List["NotificationPreference"]] = relationship(
        "NotificationPreference", back_populates="user", cascade="all, delete-orphan"
    )
    push_subscriptions: Mapped[List["PushSubscription"]] = relationship(
        "PushSubscription", back_populates="user", cascade="all, delete-orphan"
    )
    activities: Mapped[List["UserActivity"]] = relationship(
        "UserActivity", back_populates="user", cascade="all, delete-orphan"
    )
    owned_collaboration_sessions: Mapped[List["CollaborationSession"]] = relationship(
        "CollaborationSession", back_populates="owner", cascade="all, delete-orphan"
    )
    collaboration_participations: Mapped[List["CollaborationParticipant"]] = relationship(
        "CollaborationParticipant", back_populates="user", cascade="all, delete-orphan"
    )
    collaboration_activities: Mapped[List["CollaborationActivity"]] = relationship(
        "CollaborationActivity", back_populates="user", cascade="all, delete-orphan"
    )
    verification_tokens: Mapped[List["EmailVerificationToken"]] = relationship(
        "EmailVerificationToken", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, email='{self.email}', is_active={self.is_active})>"


class EmailVerificationToken(Base):
    """Model for secure email verification tokens."""

    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # SHA-256 hash
    token_type: Mapped[str] = mapped_column(String(20), nullable=False)  # verification, reset
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="verification_tokens")

    @classmethod
    def generate_token(cls) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(32)

    @classmethod
    def hash_token(cls, token: str) -> str:
        """Hash a token using SHA-256."""
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def create_verification_token(
        cls,
        user_id: int,
        token_type: str,
        ip_address: str,
        user_agent: Optional[str] = None,
        expires_hours: int = 24,
    ) -> tuple["EmailVerificationToken", str]:
        """
        Create a new verification token.
        
        Args:
            user_id: ID of the user
            token_type: Type of token (verification, reset)
            ip_address: IP address of the request
            user_agent: User agent string
            expires_hours: Hours until token expires
            
        Returns:
            Tuple of (token_instance, raw_token)
        """
        raw_token = cls.generate_token()
        token_hash = cls.hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

        token_instance = cls(
            id=secrets.token_urlsafe(16),
            user_id=user_id,
            token_hash=token_hash,
            token_type=token_type,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return token_instance, raw_token

    def is_expired(self) -> bool:
        """Check if the token is expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def is_used(self) -> bool:
        """Check if the token has been used."""
        return self.used_at is not None

    def is_valid(self) -> bool:
        """Check if the token is valid (not expired and not used)."""
        return not self.is_expired() and not self.is_used()

    def mark_as_used(self) -> None:
        """Mark the token as used."""
        self.used_at = datetime.now(timezone.utc)

    def verify_token(self, raw_token: str) -> bool:
        """Verify if the provided raw token matches the stored hash."""
        return self.hash_token(raw_token) == self.token_hash

    def __repr__(self) -> str:
        """String representation of EmailVerificationToken."""
        return (
            f"<EmailVerificationToken(id='{self.id}', user_id={self.user_id}, "
            f"type='{self.token_type}', expires_at='{self.expires_at}')>"
        )
