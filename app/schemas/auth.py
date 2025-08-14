"""Authentication and user schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user schema with common fields."""
    
    email: EmailStr = Field(..., description="User email address")


class UserCreate(UserBase):
    """Schema for user registration."""
    
    password: str = Field(
        ..., 
        min_length=8, 
        max_length=100,
        description="User password (minimum 8 characters)"
    )


class UserUpdate(BaseModel):
    """Schema for user updates."""
    
    email: Optional[EmailStr] = Field(None, description="Updated email address")
    is_active: Optional[bool] = Field(None, description="User active status")
    is_verified: Optional[bool] = Field(None, description="User verification status")


class UserResponse(UserBase):
    """Schema for user response data."""
    
    id: int = Field(..., description="User ID")
    is_active: bool = Field(..., description="User active status")
    is_verified: bool = Field(..., description="User verification status") 
    created_at: datetime = Field(..., description="User creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        """Pydantic configuration."""
        from_attributes = True


class Token(BaseModel):
    """Schema for authentication token response."""
    
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")


class TokenData(BaseModel):
    """Schema for token payload data."""
    
    user_id: Optional[int] = Field(None, description="User ID from token")


class LoginRequest(BaseModel):
    """Schema for login request."""
    
    username: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""
    
    refresh_token: str = Field(..., description="Refresh token")


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""
    
    email: EmailStr = Field(..., description="User email address")


class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation."""
    
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(
        ..., 
        min_length=8, 
        max_length=100,
        description="New password (minimum 8 characters)"
    )


class MessageResponse(BaseModel):
    """Generic message response schema."""
    
    message: str = Field(..., description="Response message")
    detail: Optional[str] = Field(None, description="Additional details")
