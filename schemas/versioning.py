"""
Pydantic schemas for Content Versioning.
"""
from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from models.models import ContentTypeEnum


# Base schemas
class ContentVersionBase(BaseModel):
    content_type: ContentTypeEnum
    content_id: int
    version_number: int
    version_data: Dict[str, Any] = Field(..., description="Snapshot of content at this version")


class ContentVersionCreate(ContentVersionBase):
    user_id: int


class ContentVersionRead(ContentVersionBase):
    id: int
    user_id: int
    created_at: datetime
    
    # User details (populated by router)
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    class Config:
        from_attributes = True


class ContentVersionListResponse(BaseModel):
    """Response model for version listing."""
    versions: List[ContentVersionRead]
    total_count: int
    current_version: int
    has_more: bool


class ContentVersionCompareResponse(BaseModel):
    """Response model for version comparison."""
    content_type: ContentTypeEnum
    content_id: int
    version_a: ContentVersionRead
    version_b: ContentVersionRead
    differences: Dict[str, Any] = Field(
        ..., description="Differences between versions"
    )


class ContentRestoreResponse(BaseModel):
    """Response model for content restoration."""
    message: str
    content_type: ContentTypeEnum
    content_id: int
    restored_from_version: int
    new_version_number: int 