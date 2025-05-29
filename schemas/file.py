"""
File-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PhysicalFileBase(BaseModel):
    """Base physical file schema with common fields."""
    file_name: str = Field(..., min_length=1, max_length=255, description="Original filename")
    file_type: str = Field(..., description="File extension/type")
    mime_type: str = Field(..., description="MIME type of the file")


class PhysicalFileRead(PhysicalFileBase):
    """Schema for reading physical file data."""
    id: int
    file_hash: str
    file_path: str
    file_size_bytes: int
    uploaded_at: datetime
    user_id: int

    class Config:
        from_attributes = True


class UserFileAccessBase(BaseModel):
    """Base user file access schema."""
    access_level: str = Field(default="read", description="Access level (read, write, admin)")


class UserFileAccessRead(UserFileAccessBase):
    """Schema for reading user file access data."""
    user_id: int
    physical_file_id: int
    granted_at: datetime
    granted_by_user_id: Optional[int] = None

    class Config:
        from_attributes = True


class UserFileAccessCreate(UserFileAccessBase):
    """Schema for creating user file access."""
    physical_file_id: int
    user_id: int
    granted_by_user_id: Optional[int] = None
