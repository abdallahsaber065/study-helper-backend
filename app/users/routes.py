"""User management routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user, get_current_verified_user
from app.database import get_db_session
from app.schemas.auth import UserResponse, UserUpdate, MessageResponse
from app.users.models import User

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get current user information.
    
    This is a protected route that requires authentication.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Current user information
    """
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_users_me(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    Update current user information.
    
    Args:
        user_update: User update data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Updated user information
        
    Raises:
        HTTPException: If email already exists
    """
    # Check if email is being updated and if it already exists
    if user_update.email and user_update.email != current_user.email:
        stmt = select(User).where(User.email == user_update.email)
        result = await db.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Update email and set verification status to False
        current_user.email = user_update.email
        current_user.is_verified = False
    
    # Update other fields if provided
    if user_update.is_active is not None:
        current_user.is_active = user_update.is_active
    
    # Note: is_verified should typically only be updated through verification process
    # but we'll allow it for admin purposes
    if user_update.is_verified is not None:
        current_user.is_verified = user_update.is_verified
    
    try:
        await db.commit()
        await db.refresh(current_user)
        
        return UserResponse.model_validate(current_user)
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        ) from e


@router.delete("/me", response_model=MessageResponse)
async def delete_users_me(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    Deactivate current user account.
    
    This doesn't permanently delete the user, just deactivates them.
    Requires email verification for security.
    
    Args:
        current_user: Current verified user
        db: Database session
        
    Returns:
        Success message
    """
    # Deactivate user instead of deleting
    current_user.is_active = False
    
    try:
        await db.commit()
        
        return MessageResponse(
            message="Account deactivated successfully",
            detail="Your account has been deactivated. Contact support to reactivate."
        )
    
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate account"
        ) from e


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get detailed user profile information.
    
    This is an alias for /me with the same functionality.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User profile information
    """
    return UserResponse.model_validate(current_user)
