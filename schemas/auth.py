"""
Authentication-related Pydantic schemas.
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    """Access token schema."""
    access_token: str
    token_type: str
    expires_in: int = Field(..., description="Token expiration time in seconds")


class TokenData(BaseModel):
    """Token payload schema."""
    username: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request schema."""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., min_length=8, description="Password")


class LoginResponse(BaseModel):
    """Login response schema."""
    access_token: str
    token_type: str
    user: Dict[str, Any]
    expires_in: int = Field(..., description="Token expiration time in seconds")


class RegisterResponse(BaseModel):
    """Registration response schema."""
    message: str
    user: Dict[str, Any]


class PasswordResetRequest(BaseModel):
    """Password reset request schema."""
    email: EmailStr = Field(..., description="Email address to send reset link to")


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema."""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, description="New password")


class PasswordResetResponse(BaseModel):
    """Password reset response schema."""
    message: str


class ActivationRequest(BaseModel):
    """Account activation request schema."""
    token: str = Field(..., description="Account activation token")


class ActivationResponse(BaseModel):
    """Account activation response schema."""
    message: str
    user: Dict[str, Any]
