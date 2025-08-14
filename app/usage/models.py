"""
Usage tracking and quota management models.
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, Numeric, String, Text, 
    UniqueConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from ..users.models import User


class UserQuota(Base):
    """
    User quotas for AI usage and cost management.
    
    Tracks monthly limits for tokens, costs, and operations.
    """
    
    __tablename__ = "user_quotas"
    
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    # Quota period
    quota_month: Mapped[date] = mapped_column(Date, nullable=False)  # YYYY-MM-01 format
    
    # Token limits
    token_limit: Mapped[int] = mapped_column(Integer, default=100000)  # Monthly token limit
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    
    # Cost limits (USD)
    cost_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("50.00"))
    cost_used: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    
    # Operation limits
    summary_limit: Mapped[int] = mapped_column(Integer, default=100)  # Monthly summaries
    summaries_used: Mapped[int] = mapped_column(Integer, default=0)
    
    quiz_limit: Mapped[int] = mapped_column(Integer, default=50)  # Monthly quizzes
    quizzes_used: Mapped[int] = mapped_column(Integer, default=0)
    
    # Premium features
    is_premium: Mapped[bool] = mapped_column(default=False)
    premium_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="quotas")
    
    # Unique constraint for user-month combination
    __table_args__ = (
        UniqueConstraint('user_id', 'quota_month', name='unique_user_quota_month'),
        Index('idx_user_quota_month', 'user_id', 'quota_month'),
    )
    
    def __repr__(self) -> str:
        return f"<UserQuota(id={self.id}, user_id={self.user_id}, month={self.quota_month})>"
    
    @property
    def tokens_remaining(self) -> int:
        """Calculate remaining token quota."""
        return max(0, self.token_limit - self.tokens_used)
    
    @property
    def cost_remaining(self) -> Decimal:
        """Calculate remaining cost quota."""
        return max(Decimal("0.00"), self.cost_limit - self.cost_used)
    
    @property
    def summaries_remaining(self) -> int:
        """Calculate remaining summary quota."""
        return max(0, self.summary_limit - self.summaries_used)
    
    @property
    def quizzes_remaining(self) -> int:
        """Calculate remaining quiz quota."""
        return max(0, self.quiz_limit - self.quizzes_used)
    
    @property
    def token_usage_percentage(self) -> float:
        """Calculate token usage as percentage."""
        if self.token_limit == 0:
            return 0.0
        return min(100.0, (self.tokens_used / self.token_limit) * 100)
    
    @property
    def cost_usage_percentage(self) -> float:
        """Calculate cost usage as percentage."""
        if self.cost_limit == 0:
            return 0.0
        return min(100.0, float((self.cost_used / self.cost_limit) * 100))
    
    @property
    def is_token_limit_exceeded(self) -> bool:
        """Check if token limit is exceeded."""
        return self.tokens_used >= self.token_limit
    
    @property
    def is_cost_limit_exceeded(self) -> bool:
        """Check if cost limit is exceeded."""
        return self.cost_used >= self.cost_limit
    
    @property
    def is_summary_limit_exceeded(self) -> bool:
        """Check if summary limit is exceeded."""
        return self.summaries_used >= self.summary_limit
    
    @property
    def is_quiz_limit_exceeded(self) -> bool:
        """Check if quiz limit is exceeded."""
        return self.quizzes_used >= self.quiz_limit
    
    def can_use_tokens(self, token_count: int) -> bool:
        """Check if user can use specified number of tokens."""
        return (self.tokens_used + token_count) <= self.token_limit
    
    def can_afford_cost(self, cost: Decimal) -> bool:
        """Check if user can afford specified cost."""
        return (self.cost_used + cost) <= self.cost_limit
    
    def can_create_summary(self) -> bool:
        """Check if user can create another summary."""
        return self.summaries_used < self.summary_limit
    
    def can_create_quiz(self) -> bool:
        """Check if user can create another quiz."""
        return self.quizzes_used < self.quiz_limit
    
    def add_usage(
        self, 
        tokens: int = 0, 
        cost: Decimal = Decimal("0.00"), 
        summaries: int = 0, 
        quizzes: int = 0
    ) -> None:
        """Add usage to the quota."""
        self.tokens_used += tokens
        self.cost_used += cost
        self.summaries_used += summaries
        self.quizzes_used += quizzes


class UsageRecord(Base):
    """
    Detailed usage tracking for AI operations.
    
    Records individual AI API calls with detailed metrics.
    """
    
    __tablename__ = "usage_records"
    
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    # Operation details
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # summary, quiz, etc.
    resource_id: Mapped[Optional[str]] = mapped_column(String(36))  # summary_id, quiz_id, etc.
    
    # AI provider details
    ai_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_model: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Usage metrics
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    
    # Cost tracking
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0.0000"))
    cost_currency: Mapped[str] = mapped_column(String(3), default="USD")
    
    # Performance metrics
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    request_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False
    )
    response_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Request metadata
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36))
    task_id: Mapped[Optional[str]] = mapped_column(String(36))
    
    # Success/failure tracking
    status: Mapped[str] = mapped_column(String(20), default="success")  # success, error, timeout
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Quality metrics
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    user_rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5 stars
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="usage_records")
    
    # Indexes for efficient queries
    __table_args__ = (
        Index('idx_user_created_at', 'user_id', 'created_at'),
        Index('idx_operation_type', 'operation_type'),
        Index('idx_ai_provider_model', 'ai_provider', 'ai_model'),
        Index('idx_status', 'status'),
        Index('idx_correlation_id', 'correlation_id'),
    )
    
    def __repr__(self) -> str:
        return f"<UsageRecord(id={self.id}, user_id={self.user_id}, operation={self.operation_type})>"
    
    @property
    def cost_per_token(self) -> Optional[Decimal]:
        """Calculate cost per token."""
        if self.total_tokens > 0:
            return self.cost / self.total_tokens
        return None
    
    @property
    def is_successful(self) -> bool:
        """Check if the operation was successful."""
        return self.status == "success"
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate duration in seconds."""
        if self.response_timestamp and self.request_timestamp:
            delta = self.response_timestamp - self.request_timestamp
            return delta.total_seconds()
        return None


class QuotaHistory(Base):
    """
    Historical quota changes for audit and analytics.
    """
    
    __tablename__ = "quota_history"
    
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    quota_id: Mapped[str] = mapped_column(ForeignKey("user_quotas.id"), nullable=False)
    
    # Change details
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)  # upgrade, downgrade, reset, adjustment
    field_changed: Mapped[str] = mapped_column(String(50), nullable=False)  # token_limit, cost_limit, etc.
    
    # Values
    old_value: Mapped[Optional[str]] = mapped_column(String(100))
    new_value: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Context
    reason: Mapped[Optional[str]] = mapped_column(Text)
    changed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))  # Admin user ID
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    quota: Mapped["UserQuota"] = relationship("UserQuota")
    changed_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[changed_by])
    
    def __repr__(self) -> str:
        return f"<QuotaHistory(id={self.id}, user_id={self.user_id}, change_type={self.change_type})>"
