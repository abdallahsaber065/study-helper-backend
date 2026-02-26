"""
Pydantic schemas for User Preferences.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from models.models import DifficultyLevelEnum


# Base schemas
class UserPreferenceBase(BaseModel):
    email_notifications_enabled: bool = True
    default_theme: str = Field(default="light", pattern="^(light|dark|auto)$")
    default_content_filter_difficulty: Optional[DifficultyLevelEnum] = None
    preferences_json: Optional[Dict[str, Any]] = None


class UserPreferenceCreate(UserPreferenceBase):
    pass


class UserPreferenceUpdate(BaseModel):
    email_notifications_enabled: Optional[bool] = None
    default_theme: Optional[str] = Field(None, pattern="^(light|dark|auto)$")
    default_content_filter_difficulty: Optional[DifficultyLevelEnum] = None
    preferences_json: Optional[Dict[str, Any]] = None


class UserPreferenceRead(UserPreferenceBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PreferenceUpdateResponse(BaseModel):
    """Response model for preference updates."""
    message: str
    preferences: UserPreferenceRead 