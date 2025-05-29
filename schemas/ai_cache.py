"""
AI cache-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class GeminiFileCacheBase(BaseModel):
    """Base schema for Gemini file cache entries."""
    physical_file_id: int = Field(..., description="ID of the cached physical file")
    api_key_id: int = Field(..., description="ID of the AI API key used")
    gemini_file_uri: str = Field(..., description="URI of the file in Gemini API")
    gemini_display_name: str = Field(..., description="Display name of the file in Gemini API")
    gemini_file_unique_name: str = Field(..., description="Unique name of the file in Gemini API")
    expiration_time: Optional[datetime] = Field(None, description="Expiration time of the cache")


class GeminiFileCacheCreate(GeminiFileCacheBase):
    """Schema for creating a Gemini file cache entry."""
    pass


class GeminiFileCacheRead(GeminiFileCacheBase):
    """Schema for reading Gemini file cache data."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AiApiKeyBase(BaseModel):
    """Base schema for AI API keys."""
    user_id: int = Field(..., description="ID of the user who owns the API key")
    provider_name: str = Field(..., description="Name of the AI provider (e.g., OpenAI, Google)")
    is_active: bool = Field(default=True, description="Whether the API key is active")


class AiApiKeyCreate(AiApiKeyBase):
    """Schema for creating an AI API key."""
    api_key: str = Field(..., description="The actual API key (will be encrypted)")


class AiApiKeyRead(AiApiKeyBase):
    """Schema for reading AI API key data."""
    id: int
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True 