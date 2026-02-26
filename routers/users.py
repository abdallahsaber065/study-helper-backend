"""
Router for User Management (excluding auth operations).
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, func
from sqlalchemy.orm import selectinload

from core.security import get_current_active_user, get_current_admin_user
from db_config import get_async_db
from models.models import User, UserRoleEnum, AiApiKey, UserFreeApiUsage, AiProviderEnum
from schemas.user import UserRead
from schemas.ai_cache import UserApiUsageSummary, UserFreeApiUsageRead
from core.config import settings

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserRead)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get current user's profile information."""
    # Refresh user data to get latest information
    stmt = select(User).where(User.id == current_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one()
    
    return UserRead.model_validate(user)


@router.put("/me", response_model=UserRead)
async def update_current_user_profile(
    update_data: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update current user's profile information."""
    # Get current user from database
    stmt = select(User).where(User.id == current_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one()
    
    # Update allowed fields
    allowed_fields = ['first_name', 'last_name', 'profile_picture_url']
    
    for field, value in update_data.items():
        if field in allowed_fields and hasattr(user, field):
            setattr(user, field, value)
    
    await db.commit()
    await db.refresh(user)
    
    return UserRead.model_validate(user)


@router.get("/", response_model=List[UserRead])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by username, first name, or last name"),
    role: Optional[UserRoleEnum] = Query(None, description="Filter by user role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_db)
):
    """List all users (admin only)."""
    stmt = select(User)
    
    # Apply search filter
    if search:
        search_filter = or_(
            User.username.ilike(f"%{search}%"),
            User.first_name.ilike(f"%{search}%"),
            User.last_name.ilike(f"%{search}%"),
            User.email.ilike(f"%{search}%")
        )
        stmt = stmt.where(search_filter)
    
    # Apply role filter
    if role:
        stmt = stmt.where(User.role == role)
    
    # Apply active status filter
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    
    # Apply pagination
    stmt = stmt.offset(skip).limit(limit).order_by(User.created_at.desc())
    
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    return [UserRead.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserRead)
async def get_user_by_id(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get user by ID (admin only)."""
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserRead.model_validate(user)


@router.put("/{user_id}/role")
async def update_user_role(
    user_id: int,
    new_role: UserRoleEnum,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update user role (admin only)."""
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent self-demotion from admin
    if current_user.id == user_id and new_role != UserRoleEnum.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own admin role"
        )
    
    user.role = new_role
    await db.commit()
    
    return {
        "message": f"User role updated to {new_role.value}",
        "user_id": user_id,
        "new_role": new_role.value
    }


@router.put("/{user_id}/status")
async def update_user_status(
    user_id: int,
    is_active: bool,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update user active status (admin only)."""
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent self-deactivation
    if current_user.id == user_id and not is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    user.is_active = is_active
    await db.commit()
    
    status_text = "activated" if is_active else "deactivated"
    return {
        "message": f"User {status_text} successfully",
        "user_id": user_id,
        "is_active": is_active
    }


@router.get("/{user_id}/api-usage")
async def get_user_api_usage(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get user API usage statistics (admin only)."""
    # Check if user exists
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get user's API keys
    api_keys_stmt = select(AiApiKey).where(
        AiApiKey.user_id == user_id,
        AiApiKey.is_active == True
    )
    api_keys_result = await db.execute(api_keys_stmt)
    api_keys = api_keys_result.scalars().all()
    
    # Get free API usage
    usage_stmt = select(UserFreeApiUsage).where(UserFreeApiUsage.user_id == user_id)
    usage_result = await db.execute(usage_stmt)
    free_usage = usage_result.scalars().all()
    
    return {
        "user_id": user_id,
        "username": user.username,
        "api_keys": [
            {
                "id": key.id,
                "provider": key.provider_name.value,
                "created_at": key.created_at,
                "last_used_at": key.last_used_at,
                "is_active": key.is_active
            }
            for key in api_keys
        ],
        "free_usage": [
            {
                "provider": usage.api_provider.value,
                "usage_count": usage.usage_count,
                "last_used_at": usage.last_used_at
            }
            for usage in free_usage
        ]
    }


@router.get("/username/{username}", response_model=UserRead)
async def get_user_by_username(
    username: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific user by username.
    """
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Users can only view their own profile unless they're admin
    if current_user.id != user.id and current_user.role != UserRoleEnum.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this user's profile"
        )
    
    return UserRead.model_validate(user)


@router.get("/me/api-usage")
async def get_my_api_usage(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get the current user's API usage summary."""
    # Check if user has their own API keys
    api_keys_stmt = select(AiApiKey).where(
        AiApiKey.user_id == current_user.id,
        AiApiKey.is_active == True
    )
    api_keys_result = await db.execute(api_keys_stmt)
    has_own_keys = api_keys_result.scalar_one_or_none() is not None
    
    # Get free tier usage for Gemini
    gemini_usage_stmt = select(UserFreeApiUsage).where(
        UserFreeApiUsage.user_id == current_user.id,
        UserFreeApiUsage.api_provider == AiProviderEnum.Google
    )
    gemini_usage_result = await db.execute(gemini_usage_stmt)
    gemini_usage = gemini_usage_result.scalar_one_or_none()
    
    # Get free tier usage for OpenAI
    openai_usage_stmt = select(UserFreeApiUsage).where(
        UserFreeApiUsage.user_id == current_user.id,
        UserFreeApiUsage.api_provider == AiProviderEnum.OpenAI
    )
    openai_usage_result = await db.execute(openai_usage_stmt)
    openai_usage = openai_usage_result.scalar_one_or_none()
    
    # Create response
    response = {
        "user_id": current_user.id,
        "has_own_keys": has_own_keys,
        "free_usage": []
    }
    
    # Add Gemini usage if available
    if gemini_usage:
        response["free_usage"].append({
            "provider": "Google",
            "usage_count": gemini_usage.usage_count,
            "last_used_at": gemini_usage.last_used_at
        })
    
    # Add OpenAI usage if available
    if openai_usage:
        response["free_usage"].append({
            "provider": "OpenAI",
            "usage_count": openai_usage.usage_count,
            "last_used_at": openai_usage.last_used_at
        })
    
    return response
