"""
Summary database models for AI-powered document summarization.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..files.models import FileMetadata
from ..users.models import User


class Summary(Base):
    """
    Database model for document summaries with comprehensive AI processing tracking.
    
    This model tracks all aspects of AI-powered summary generation including:
    - Processing status and progress
    - AI provider and model information
    - Cost and token usage tracking
    - Quality metrics and user feedback
    - Audit trail and metadata
    """
    
    __tablename__ = "summaries"

    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Foreign key relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    file_id: Mapped[str] = mapped_column(ForeignKey("file_metadata.id"), nullable=False)
    
    # Summary content and metadata
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary_type: Mapped[str] = mapped_column(
        String(50), 
        nullable=False, 
        default="general"
    )  # general, academic, technical, executive, etc.
    
    # AI processing information
    ai_provider: Mapped[str] = mapped_column(String(50), nullable=False)  # openai, gemini, anthropic
    ai_model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_template: Mapped[Optional[str]] = mapped_column(String(100))  # template identifier
    
    # Usage and cost tracking
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    generation_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))  # USD cost
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Task processing tracking
    task_id: Mapped[Optional[str]] = mapped_column(String(36))  # Celery task ID
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36))  # Request correlation ID
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="pending"
    )  # pending, processing, completed, failed, cancelled
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Quality and feedback tracking
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))  # 0.00-5.00
    user_rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5 stars
    user_feedback: Mapped[Optional[str]] = mapped_column(Text)
    
    # Content analysis metrics
    original_word_count: Mapped[Optional[int]] = mapped_column(Integer)
    summary_word_count: Mapped[Optional[int]] = mapped_column(Integer)
    compression_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))  # e.g., 0.25 = 25%
    readability_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    
    # Configuration and parameters
    max_length: Mapped[Optional[int]] = mapped_column(Integer)
    temperature: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    custom_instructions: Mapped[Optional[str]] = mapped_column(Text)
    
    # Audit and timestamps
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
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Soft delete support
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    user: Mapped[User] = relationship("User", back_populates="summaries")
    file_metadata: Mapped[FileMetadata] = relationship("FileMetadata", back_populates="summaries")
    
    def __repr__(self) -> str:
        return f"<Summary(id={self.id}, title='{self.title}', status='{self.status}')>"
    
    @property
    def is_completed(self) -> bool:
        """Check if summary generation is completed."""
        return self.status == "completed"
    
    @property
    def is_failed(self) -> bool:
        """Check if summary generation failed."""
        return self.status == "failed"
    
    @property
    def is_processing(self) -> bool:
        """Check if summary is currently being processed."""
        return self.status in ["pending", "processing"]
    
    def calculate_compression_ratio(self) -> Optional[Decimal]:
        """Calculate and update compression ratio if word counts are available."""
        if self.original_word_count and self.summary_word_count:
            ratio = Decimal(self.summary_word_count) / Decimal(self.original_word_count)
            self.compression_ratio = ratio
            return ratio
        return None
    
    def mark_as_processing(self, task_id: str, correlation_id: str) -> None:
        """Mark summary as processing with task identifiers."""
        self.status = "processing"
        self.task_id = task_id
        self.correlation_id = correlation_id
        self.progress_percentage = 0
    
    def mark_as_completed(self, processing_time_ms: int) -> None:
        """Mark summary as completed with processing time."""
        self.status = "completed"
        self.progress_percentage = 100
        self.processing_time_ms = processing_time_ms
        self.completed_at = func.now()
        self.error_message = None
    
    def mark_as_failed(self, error_message: str) -> None:
        """Mark summary as failed with error message."""
        self.status = "failed"
        self.error_message = error_message[:1000]  # Truncate long error messages
        self.completed_at = func.now()
    
    def update_progress(self, percentage: int) -> None:
        """Update processing progress percentage."""
        if 0 <= percentage <= 100:
            self.progress_percentage = percentage
    
    def soft_delete(self) -> None:
        """Soft delete the summary."""
        self.deleted_at = func.now()


class SummaryVersion(Base):
    """
    Model for tracking summary versions and revisions.
    
    Allows users to regenerate summaries with different parameters
    while maintaining history of previous versions.
    """
    
    __tablename__ = "summary_versions"
    
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    summary_id: Mapped[str] = mapped_column(ForeignKey("summaries.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Generation parameters for this version
    ai_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_template: Mapped[Optional[str]] = mapped_column(String(100))
    custom_instructions: Mapped[Optional[str]] = mapped_column(Text)
    
    # Metrics for this version
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    generation_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    user_rating: Mapped[Optional[int]] = mapped_column(Integer)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    
    # Relationships
    summary: Mapped[Summary] = relationship("Summary")
    
    def __repr__(self) -> str:
        return f"<SummaryVersion(id={self.id}, summary_id={self.summary_id}, version={self.version_number})>"
