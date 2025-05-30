"""
Pydantic schemas for Content Comments.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from models.models import ContentTypeEnum


# Base schemas
class ContentCommentBase(BaseModel):
    content_type: ContentTypeEnum
    content_id: int
    comment_text: str = Field(..., min_length=1, max_length=2000)
    parent_comment_id: Optional[int] = None


class ContentCommentCreate(ContentCommentBase):
    pass


class ContentCommentUpdate(BaseModel):
    comment_text: Optional[str] = Field(None, min_length=1, max_length=2000)


class ContentCommentRead(ContentCommentBase):
    id: int
    author_id: int
    is_deleted: bool
    is_edited: bool
    created_at: datetime
    updated_at: datetime
    
    # Author details (populated by router)
    author_username: Optional[str] = None
    author_first_name: Optional[str] = None
    author_last_name: Optional[str] = None
    
    # Reply count (populated by router)
    reply_count: int = 0
    replies: List["ContentCommentRead"] = []

    class Config:
        from_attributes = True


# Fix forward reference
ContentCommentRead.model_rebuild()


class CommentThreadResponse(BaseModel):
    """Response model for threaded comments."""
    comments: List[ContentCommentRead]
    total_count: int
    has_more: bool


class CommentCreateResponse(BaseModel):
    """Response model for comment creation."""
    message: str
    comment: ContentCommentRead 