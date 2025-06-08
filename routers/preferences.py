"""
Router for User Preferences.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db_config import get_async_db
from core.security import get_current_user
from models.models import User, UserPreference
from schemas.preference import (
    UserPreferenceRead, UserPreferenceUpdate, PreferenceUpdateResponse
)

router = APIRouter(prefix="/preferences", tags=["User Preferences"])


@router.get("", response_model=UserPreferenceRead)
async def get_user_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get current user's preferences."""
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    preferences = result.scalar_one_or_none()
    
    if not preferences:
        # Create default preferences if they don't exist
        preferences = UserPreference(
            user_id=current_user.id,
            email_notifications_enabled=True,
            default_theme="light",
            default_content_filter_difficulty=None,
            preferences_json={}
        )
        db.add(preferences)
        await db.commit()
        await db.refresh(preferences)
    
    return UserPreferenceRead.from_orm(preferences)


@router.put("", response_model=PreferenceUpdateResponse)
async def update_user_preferences(
    update_data: UserPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update current user's preferences."""
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    preferences = result.scalar_one_or_none()
    
    if not preferences:
        # Create preferences if they don't exist
        preferences = UserPreference(
            user_id=current_user.id,
            email_notifications_enabled=True,
            default_theme="light",
            default_content_filter_difficulty=None,
            preferences_json={}
        )
        db.add(preferences)
        await db.commit()
        await db.refresh(preferences)
    
    # Update provided fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(preferences, field, value)
    
    await db.commit()
    await db.refresh(preferences)
    
    return PreferenceUpdateResponse(
        message="Preferences updated successfully",
        preferences=UserPreferenceRead.from_orm(preferences)
    )


@router.post("/reset", response_model=PreferenceUpdateResponse)
async def reset_user_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Reset user preferences to default values."""
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    preferences = result.scalar_one_or_none()
    
    if not preferences:
        # Create default preferences
        preferences = UserPreference(
            user_id=current_user.id,
            email_notifications_enabled=True,
            default_theme="light",
            default_content_filter_difficulty=None,
            preferences_json={}
        )
        db.add(preferences)
    else:
        # Reset to defaults
        preferences.email_notifications_enabled = True
        preferences.default_theme = "light"
        preferences.default_content_filter_difficulty = None
        preferences.preferences_json = {}
    
    await db.commit()
    await db.refresh(preferences)
    
    return PreferenceUpdateResponse(
        message="Preferences reset to default values",
        preferences=UserPreferenceRead.from_orm(preferences)
    ) 