"""
Authentication-related Pydantic schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """Schema for token data."""
    username: Optional[str] = None


class LoginRequest(BaseModel):
    """Schema for login request."""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="User password")


class LoginResponse(BaseModel):
    """Schema for login response."""
    access_token: str
    token_type: str = "bearer"
    user: dict  # Will contain user info without sensitive data
    expires_in: int


class RegisterResponse(BaseModel):
    """Schema for registration response."""
    message: str
    user: dict  # Will contain user info without sensitive data
