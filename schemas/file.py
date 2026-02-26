"""
File-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class FileBase(BaseModel):
    """Base file schema with common fields."""
    file_name: str = Field(..., description="Original file name")
    file_type: str = Field(..., description="File extension (e.g., pdf, txt)")
    mime_type: str = Field(..., description="MIME type of the file")


class FileCreate(FileBase):
    """Schema for file creation metadata."""
    file_hash: str = Field(..., description="SHA-256 hash of the file")
    file_size_bytes: int = Field(..., description="File size in bytes")
    file_path: str = Field(..., description="Path where the file is stored")


class FileRead(FileBase):
    """Schema for reading file data."""
    id: int
    file_hash: str
    file_size_bytes: int
    uploaded_at: datetime
    user_id: int

    class Config:
        from_attributes = True


class FileUploadResponse(BaseModel):
    """Response schema for file upload."""
    message: str
    file: FileRead


class UserFileAccessCreate(BaseModel):
    """Schema for creating user file access."""
    user_id: int
    physical_file_id: int
    access_level: str = Field(default="read", description="Access level (read, write, admin)")
    granted_by_user_id: Optional[int] = None


class UserFileAccessRead(BaseModel):
    """Schema for reading user file access."""
    user_id: int
    physical_file_id: int
    access_level: str
    granted_at: datetime
    granted_by_user_id: Optional[int] = None

    class Config:
        from_attributes = True


class FileAccessList(BaseModel):
    """Schema for listing file access entries."""
    file: FileRead
    access_entries: List[UserFileAccessRead]
