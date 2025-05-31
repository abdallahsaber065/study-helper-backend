"""
AI cache-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List
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
    provider_name: str = Field(..., description="Name of the AI provider (e.g., OpenAI, Google)")
    is_active: bool = Field(default=True, description="Whether the API key is active")


class AiApiKeyCreate(AiApiKeyBase):
    """Schema for creating an AI API key."""
    api_key: str = Field(..., description="The actual API key (will be encrypted)")


class AiApiKeyUpdate(BaseModel):
    """Schema for updating an AI API key."""
    api_key: Optional[str] = Field(None, description="The actual API key (will be encrypted)")
    provider_name: Optional[str] = Field(None, description="Name of the AI provider (e.g., OpenAI, Google)")
    is_active: Optional[bool] = Field(None, description="Whether the API key is active")


class AiApiKeyRead(AiApiKeyBase):
    """Schema for reading AI API key data."""
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserFreeApiUsageRead(BaseModel):
    """Schema for reading user's free tier API usage."""
    user_id: int = Field(..., description="ID of the user")
    api_provider: str = Field(..., description="Name of the AI provider")
    usage_count: int = Field(..., description="Number of times the free tier API has been used")
    last_used_at: Optional[datetime] = Field(None, description="When the API was last used")
    limit: int = Field(..., description="Maximum allowed usage for this provider")
    remaining: int = Field(..., description="Remaining usage for this provider")

    class Config:
        from_attributes = True


class UserApiUsageSummary(BaseModel):
    """Summary of user's API usage for all providers."""
    gemini: Optional[UserFreeApiUsageRead] = Field(None, description="Gemini API usage")
    openai: Optional[UserFreeApiUsageRead] = Field(None, description="OpenAI API usage")
    has_own_keys: bool = Field(False, description="Whether the user has their own API keys")


class AiApiKeyList(BaseModel):
    """List of AI API keys."""
    items: List[AiApiKeyRead]
    total: int = Field(..., description="Total number of API keys")


class AiApiKeyTestRequest(BaseModel):
    """Schema for testing an AI API key."""
    api_key: str = Field(..., description="The API key to test")
    provider_name: str = Field(..., description="Name of the AI provider to test with")


class AiApiKeyTestResponse(BaseModel):
    """Schema for API key test response."""
    is_valid: bool = Field(..., description="Whether the API key is valid")
    message: str = Field(..., description="Status message") 