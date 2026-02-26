"""
Pydantic schemas for Content Analytics.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from models.models import ContentTypeEnum


# Base schemas
class ContentAnalyticsBase(BaseModel):
    content_type: ContentTypeEnum
    content_id: int
    view_count: int = 0
    like_count: int = 0
    share_count: int = 0
    comment_count: int = 0


class ContentAnalyticsRead(ContentAnalyticsBase):
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContentAnalyticsUpdate(BaseModel):
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    share_count: Optional[int] = None
    comment_count: Optional[int] = None


class AnalyticsIncrement(BaseModel):
    """Request to increment analytics counters."""
    metric: str = Field(..., pattern="^(view|like|share|comment)$")
    increment: int = Field(default=1, ge=0, le=100)


class ContentAnalyticsSummary(BaseModel):
    """Summary analytics for content."""
    content_type: ContentTypeEnum
    content_id: int
    analytics: ContentAnalyticsRead
    engagement_score: float = Field(
        ..., description="Calculated engagement score based on all metrics"
    )
    popularity_rank: Optional[int] = Field(
        None, description="Rank among similar content"
    )


class AnalyticsDashboard(BaseModel):
    """Dashboard response with aggregated analytics."""
    total_content: int
    total_views: int
    total_likes: int
    total_comments: int
    total_shares: int
    
    top_content: List[ContentAnalyticsSummary] = Field(
        ..., description="Top performing content"
    )
    
    recent_activity: List[Dict[str, Any]] = Field(
        ..., description="Recent analytics activity"
    )
    
    period_comparison: Dict[str, Any] = Field(
        default_factory=dict, description="Comparison with previous period"
    )


class ContentEngagementMetrics(BaseModel):
    """Detailed engagement metrics for specific content."""
    content_type: ContentTypeEnum
    content_id: int
    
    # Basic metrics
    views: int
    likes: int
    comments: int
    shares: int
    
    # Derived metrics
    engagement_rate: float = Field(..., description="Engagement rate percentage")
    view_to_comment_ratio: float
    average_rating: Optional[float] = None
    
    # Time-based metrics
    views_last_24h: int = 0
    views_last_7d: int = 0
    views_last_30d: int = 0
    
    # Trend indicators
    trend_direction: str = Field(..., pattern="^(up|down|stable)$")
    trend_percentage: float = Field(..., description="Percentage change from previous period") 