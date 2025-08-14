"""
Pydantic schemas for summary API requests and responses.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class SummaryStatus(str, Enum):
    """Summary processing status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SummaryType(str, Enum):
    """Types of summaries that can be generated."""
    GENERAL = "general"
    ACADEMIC = "academic"
    TECHNICAL = "technical"
    EXECUTIVE = "executive"
    BULLET_POINTS = "bullet_points"
    DETAILED = "detailed"


class AIProvider(str, Enum):
    """Supported AI providers for summary generation."""
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"


# Request schemas
class SummaryGenerateRequest(BaseModel):
    """Request schema for generating a new summary."""
    
    file_id: str = Field(..., description="ID of the file to summarize")
    title: str = Field(..., min_length=1, max_length=255, description="Title for the summary")
    summary_type: SummaryType = Field(
        default=SummaryType.GENERAL,
        description="Type of summary to generate"
    )
    ai_provider: Optional[AIProvider] = Field(
        default=None,
        description="AI provider to use (defaults to system default)"
    )
    ai_model: Optional[str] = Field(
        default=None,
        pattern=r"^[a-zA-Z0-9\-_.]+$",
        description="Specific AI model to use"
    )
    max_length: Optional[int] = Field(
        default=None,
        ge=100,
        le=5000,
        description="Maximum length of summary in words"
    )
    temperature: Optional[float] = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="AI temperature setting for creativity"
    )
    custom_instructions: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Custom instructions for summary generation"
    )

    @validator("file_id")
    def validate_file_id(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("File ID is required")
        return v.strip()

    @validator("title")
    def validate_title(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Title is required")
        return v.strip()


class SummaryUpdateRequest(BaseModel):
    """Request schema for updating summary metadata."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    user_rating: Optional[int] = Field(None, ge=1, le=5)
    user_feedback: Optional[str] = Field(None, max_length=2000)


class SummaryRegenerateRequest(BaseModel):
    """Request schema for regenerating an existing summary."""
    
    ai_provider: Optional[AIProvider] = Field(default=None)
    ai_model: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9\-_.]+$")
    summary_type: Optional[SummaryType] = Field(default=None)
    max_length: Optional[int] = Field(default=None, ge=100, le=5000)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    custom_instructions: Optional[str] = Field(default=None, max_length=1000)


# Response schemas
class SummaryProgressResponse(BaseModel):
    """Response schema for summary generation progress."""
    
    task_id: str
    summary_id: str
    status: SummaryStatus
    progress_percentage: int = Field(ge=0, le=100)
    estimated_time_remaining: Optional[int] = Field(
        default=None,
        description="Estimated time remaining in seconds"
    )
    current_step: Optional[str] = Field(
        default=None,
        description="Current processing step description"
    )


class SummaryMetrics(BaseModel):
    """Summary generation metrics and analytics."""
    
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    generation_cost: Optional[Decimal] = None
    processing_time_ms: Optional[int] = None
    original_word_count: Optional[int] = None
    summary_word_count: Optional[int] = None
    compression_ratio: Optional[Decimal] = None
    readability_score: Optional[Decimal] = None
    quality_score: Optional[Decimal] = None


class SummaryResponse(BaseModel):
    """Response schema for summary data."""
    
    id: str
    user_id: int
    file_id: str
    title: str
    content: str
    summary_type: str
    
    # AI processing info
    ai_provider: str
    ai_model_used: str
    prompt_template: Optional[str] = None
    
    # Status and progress
    status: SummaryStatus
    progress_percentage: int
    error_message: Optional[str] = None
    
    # User interaction
    user_rating: Optional[int] = None
    user_feedback: Optional[str] = None
    
    # Metrics
    metrics: Optional[SummaryMetrics] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SummaryListResponse(BaseModel):
    """Response schema for paginated summary lists."""
    
    summaries: List[SummaryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SummaryAnalytics(BaseModel):
    """Analytics data for summaries."""
    
    total_summaries: int
    completed_summaries: int
    failed_summaries: int
    processing_summaries: int
    
    total_cost: Decimal
    total_tokens: int
    average_processing_time_ms: float
    average_compression_ratio: Optional[float] = None
    average_quality_score: Optional[float] = None
    
    # Provider usage statistics
    provider_usage: dict[str, int]
    model_usage: dict[str, int]
    summary_type_usage: dict[str, int]


class TaskProgressUpdate(BaseModel):
    """WebSocket message for task progress updates."""
    
    task_id: str
    summary_id: str
    status: SummaryStatus
    progress_percentage: int
    current_step: Optional[str] = None
    estimated_time_remaining: Optional[int] = None
    error_message: Optional[str] = None
    
    class Config:
        use_enum_values = True


# Validation schemas for internal use
class SummaryFilters(BaseModel):
    """Filters for summary queries."""
    
    status: Optional[List[SummaryStatus]] = None
    summary_type: Optional[List[SummaryType]] = None
    ai_provider: Optional[List[AIProvider]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    min_quality_score: Optional[float] = Field(None, ge=0.0, le=5.0)
    has_user_rating: Optional[bool] = None
    
    # Search
    search_query: Optional[str] = Field(None, max_length=200)
    
    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    
    # Sorting
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


class BulkSummaryOperation(BaseModel):
    """Schema for bulk operations on summaries."""
    
    summary_ids: List[str] = Field(..., min_items=1, max_items=50)
    operation: str = Field(..., pattern="^(delete|regenerate|export)$")
    parameters: Optional[dict] = None
