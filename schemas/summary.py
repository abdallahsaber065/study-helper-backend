"""
Summary-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class SummaryBase(BaseModel):
    """Base summary schema with common fields."""
    title: str = Field(..., min_length=1, max_length=255)
    full_markdown: str = Field(..., description="Full markdown content of the summary")


class SummaryCreate(SummaryBase):
    """Schema for creating a new summary."""
    physical_file_id: Optional[int] = Field(None, description="ID of the source file (if applicable)")
    user_id: int = Field(..., description="ID of the user creating the summary")
    community_id: Optional[int] = Field(None, description="ID of the community if shared")


class SummaryRead(SummaryBase):
    """Schema for reading summary data."""
    id: int
    user_id: int
    physical_file_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    community_id: Optional[int] = None

    class Config:
        from_attributes = True


class SummaryUpdate(BaseModel):
    """Schema for updating a summary."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    full_markdown: Optional[str] = None
    community_id: Optional[int] = None


class SummaryGenerateRequest(BaseModel):
    """Schema for requesting a summary generation from files."""
    physical_file_ids: List[int] = Field(..., description="List of file IDs to summarize", min_items=1)
    custom_instructions: Optional[str] = Field(None, description="Custom instructions for the AI")


class SummaryGenerateTextRequest(BaseModel):
    """Schema for requesting a summary generation from raw text."""
    text_content: str = Field(..., description="Raw text to summarize")
    custom_instructions: Optional[str] = Field(None, description="Custom instructions for the AI")


class SummaryGenerateResponse(BaseModel):
    """Response schema for summary generation."""
    message: str
    summary: SummaryRead 