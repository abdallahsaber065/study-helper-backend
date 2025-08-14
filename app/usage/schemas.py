"""
Pydantic schemas for usage tracking and quota management.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator


class QuotaPlan(str, Enum):
    """Available quota plans."""
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class OperationType(str, Enum):
    """Types of AI operations."""
    SUMMARY = "summary"
    QUIZ = "quiz"
    ANALYSIS = "analysis"
    CHAT = "chat"


class UsageStatus(str, Enum):
    """Status of usage records."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


# Request schemas
class QuotaUpdateRequest(BaseModel):
    """Request to update user quota limits."""
    
    token_limit: Optional[int] = Field(None, ge=0, le=10000000)
    cost_limit: Optional[Decimal] = Field(None, ge=0, le=10000)
    summary_limit: Optional[int] = Field(None, ge=0, le=10000)
    quiz_limit: Optional[int] = Field(None, ge=0, le=10000)
    is_premium: Optional[bool] = None
    reason: Optional[str] = Field(None, max_length=500)


class UsageRecordCreate(BaseModel):
    """Schema for creating usage records."""
    
    operation_type: OperationType
    resource_id: Optional[str] = None
    ai_provider: str = Field(..., max_length=50)
    ai_model: str = Field(..., max_length=100)
    
    input_tokens: Optional[int] = Field(None, ge=0)
    output_tokens: Optional[int] = Field(None, ge=0)
    total_tokens: int = Field(..., ge=0)
    
    cost: Decimal = Field(..., ge=0)
    cost_currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    
    processing_time_ms: Optional[int] = Field(None, ge=0)
    request_timestamp: datetime
    response_timestamp: Optional[datetime] = None
    
    correlation_id: Optional[str] = None
    task_id: Optional[str] = None
    
    status: UsageStatus = Field(default=UsageStatus.SUCCESS)
    error_message: Optional[str] = Field(None, max_length=2000)
    
    quality_score: Optional[Decimal] = Field(None, ge=0, le=5)
    user_rating: Optional[int] = Field(None, ge=1, le=5)


# Response schemas
class QuotaResponse(BaseModel):
    """Response schema for user quota information."""
    
    id: str
    user_id: int
    quota_month: date
    
    # Limits
    token_limit: int
    cost_limit: Decimal
    summary_limit: int
    quiz_limit: int
    
    # Usage
    tokens_used: int
    cost_used: Decimal
    summaries_used: int
    quizzes_used: int
    
    # Calculated fields
    tokens_remaining: int
    cost_remaining: Decimal
    summaries_remaining: int
    quizzes_remaining: int
    
    # Usage percentages
    token_usage_percentage: float
    cost_usage_percentage: float
    
    # Limit status
    is_token_limit_exceeded: bool
    is_cost_limit_exceeded: bool
    is_summary_limit_exceeded: bool
    is_quiz_limit_exceeded: bool
    
    # Premium status
    is_premium: bool
    premium_expires_at: Optional[datetime]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class UsageResponse(BaseModel):
    """Response schema for usage records."""
    
    id: str
    user_id: int
    operation_type: OperationType
    resource_id: Optional[str]
    
    ai_provider: str
    ai_model: str
    
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: int
    
    cost: Decimal
    cost_currency: str
    
    processing_time_ms: Optional[int]
    request_timestamp: datetime
    response_timestamp: Optional[datetime]
    
    correlation_id: Optional[str]
    task_id: Optional[str]
    
    status: UsageStatus
    error_message: Optional[str]
    
    quality_score: Optional[Decimal]
    user_rating: Optional[int]
    
    created_at: datetime
    
    # Calculated fields
    cost_per_token: Optional[Decimal]
    duration_seconds: Optional[float]
    is_successful: bool
    
    class Config:
        from_attributes = True


class UsageStatsResponse(BaseModel):
    """Response schema for usage statistics."""
    
    # Time period
    period_start: date
    period_end: date
    
    # Totals
    total_operations: int
    total_tokens: int
    total_cost: Decimal
    
    # By operation type
    operations_by_type: Dict[str, int]
    tokens_by_type: Dict[str, int]
    cost_by_type: Dict[str, Decimal]
    
    # By AI provider
    operations_by_provider: Dict[str, int]
    tokens_by_provider: Dict[str, int]
    cost_by_provider: Dict[str, Decimal]
    
    # Performance metrics
    average_processing_time_ms: Optional[float]
    success_rate: float
    
    # Quality metrics
    average_quality_score: Optional[float]
    average_user_rating: Optional[float]


class QuotaHistoryResponse(BaseModel):
    """Response schema for quota change history."""
    
    id: str
    user_id: int
    quota_id: str
    
    change_type: str
    field_changed: str
    old_value: Optional[str]
    new_value: str
    
    reason: Optional[str]
    changed_by: Optional[int]
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class QuotaCheckResponse(BaseModel):
    """Response schema for quota availability checks."""
    
    can_proceed: bool
    reason: Optional[str] = None
    
    # Quota status
    tokens_available: bool
    cost_available: bool
    operation_available: bool
    
    # Remaining quotas
    tokens_remaining: int
    cost_remaining: Decimal
    operations_remaining: int
    
    # Required vs available
    tokens_required: Optional[int] = None
    cost_required: Optional[Decimal] = None
    tokens_shortfall: Optional[int] = None
    cost_shortfall: Optional[Decimal] = None


class BillingPeriodResponse(BaseModel):
    """Response schema for billing period information."""
    
    current_period: date
    period_start: date
    period_end: date
    days_remaining: int
    
    # Reset information
    next_reset_date: date
    auto_reset: bool


class PremiumUpgradeRequest(BaseModel):
    """Request schema for premium upgrades."""
    
    plan: QuotaPlan = Field(..., description="Target plan")
    duration_months: int = Field(1, ge=1, le=12, description="Subscription duration")
    payment_method_id: Optional[str] = Field(None, description="Payment method ID")


class UsageFilters(BaseModel):
    """Filters for usage record queries."""
    
    operation_types: Optional[List[OperationType]] = None
    ai_providers: Optional[List[str]] = None
    statuses: Optional[List[UsageStatus]] = None
    
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    
    min_cost: Optional[Decimal] = Field(None, ge=0)
    max_cost: Optional[Decimal] = Field(None, ge=0)
    
    min_tokens: Optional[int] = Field(None, ge=0)
    max_tokens: Optional[int] = Field(None, ge=0)
    
    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=1000)
    
    # Sorting
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")

    @validator("date_to")
    def validate_date_range(cls, v, values):
        if v and "date_from" in values and values["date_from"]:
            if v < values["date_from"]:
                raise ValueError("date_to must be after date_from")
        return v

    @validator("max_cost")
    def validate_cost_range(cls, v, values):
        if v and "min_cost" in values and values["min_cost"]:
            if v < values["min_cost"]:
                raise ValueError("max_cost must be greater than min_cost")
        return v

    @validator("max_tokens")
    def validate_token_range(cls, v, values):
        if v and "min_tokens" in values and values["min_tokens"]:
            if v < values["min_tokens"]:
                raise ValueError("max_tokens must be greater than min_tokens")
        return v


class UsageListResponse(BaseModel):
    """Response schema for paginated usage lists."""
    
    usage_records: List[UsageResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    
    # Summary statistics for the filtered results
    summary_stats: Optional[UsageStatsResponse] = None
