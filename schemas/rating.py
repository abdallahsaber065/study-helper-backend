"""
Pydantic schemas for Content Ratings.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from models.models import ContentTypeEnum, RatingValueEnum


# Base schemas
class ContentRatingBase(BaseModel):
    content_type: ContentTypeEnum
    content_id: int
    rating: RatingValueEnum
    review_text: Optional[str] = Field(None, max_length=1000)


class ContentRatingCreate(ContentRatingBase):
    pass


class ContentRatingUpdate(BaseModel):
    rating: Optional[RatingValueEnum] = None
    review_text: Optional[str] = Field(None, max_length=1000)


class ContentRatingRead(ContentRatingBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    
    # User details (populated by router)
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    class Config:
        from_attributes = True


class ContentRatingStats(BaseModel):
    """Aggregated rating statistics for content."""
    content_type: ContentTypeEnum
    content_id: int
    average_rating: Optional[float] = None
    total_ratings: int = 0
    rating_breakdown: dict = {}  # {"1": count, "2": count, ...}


class RatingCreateResponse(BaseModel):
    """Response model for rating creation/update."""
    message: str
    rating: ContentRatingRead
    stats: ContentRatingStats 