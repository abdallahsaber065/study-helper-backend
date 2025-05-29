"""
Subject-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SubjectBase(BaseModel):
    """Base subject schema with common fields."""
    name: str = Field(..., min_length=1, max_length=100, description="Subject name")
    description: Optional[str] = Field(None, description="Subject description")


class SubjectCreate(SubjectBase):
    """Schema for creating a new subject."""
    pass


class SubjectRead(SubjectBase):
    """Schema for reading subject data."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubjectUpdate(BaseModel):
    """Schema for updating subject data."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
