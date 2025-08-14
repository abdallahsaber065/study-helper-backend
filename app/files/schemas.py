"""File-related Pydantic schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class FileUploadResponse(BaseModel):
    """Response schema for file upload."""

    id: str = Field(..., description="Unique file identifier")
    original_filename: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type of the file")
    created_at: datetime = Field(..., description="Upload timestamp")
    message: str = Field(..., description="Success message")

    class Config:
        """Pydantic config."""
        from_attributes = True


class FileMetadataResponse(BaseModel):
    """Response schema for file metadata."""

    id: str = Field(..., description="Unique file identifier")
    original_filename: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type of the file")
    description: Optional[str] = Field(None, description="File description")
    is_processed: bool = Field(..., description="Whether file has been processed")
    created_at: datetime = Field(..., description="Upload timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        """Pydantic config."""
        from_attributes = True


class FileListResponse(BaseModel):
    """Response schema for file listing."""

    files: List[FileMetadataResponse] = Field(..., description="List of files")
    total_count: int = Field(..., description="Total number of files")
    total_size: int = Field(..., description="Total size of all files in bytes")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Number of items per page")
    has_next: bool = Field(..., description="Whether there are more pages")


class FileUpdateRequest(BaseModel):
    """Request schema for file update."""

    description: Optional[str] = Field(None, max_length=1000, description="File description")

    @validator("description")
    def validate_description(cls, v):
        """Validate description."""
        if v is not None and len(v.strip()) == 0:
            return None
        return v


class FileDeleteResponse(BaseModel):
    """Response schema for file deletion."""

    message: str = Field(..., description="Deletion confirmation message")
    deleted_file_id: str = Field(..., description="ID of deleted file")


class FileError(BaseModel):
    """Error response schema for file operations."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[dict] = Field(None, description="Additional error details")


class FileValidationError(FileError):
    """Validation error response for file operations."""

    validation_errors: List[str] = Field(..., description="List of validation errors")
