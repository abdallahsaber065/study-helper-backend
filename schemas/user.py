"""
User-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from models.models import UserRoleEnum


class UserBase(BaseModel):
    """Base user schema with common fields."""
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    first_name: str = Field(..., min_length=1, max_length=50, description="User's first name")
    last_name: str = Field(..., min_length=1, max_length=50, description="User's last name")
    email: EmailStr = Field(..., description="User's email address")


class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(..., min_length=8, description="User's password (min 8 characters)")


class UserRead(UserBase):
    """Schema for reading user data (excludes sensitive information)."""
    id: int
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    profile_picture_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    role: UserRoleEnum

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Schema for updating user data."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    email: Optional[EmailStr] = None
    profile_picture_url: Optional[str] = None


class UserSession(BaseModel):
    """Schema for user session data."""
    id: int
    user_id: int
    session_token: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True
