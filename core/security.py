"""
Security utilities for password hashing and JWT token handling.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from core.config import settings
from core.logging import get_logger, security_logger
from db_config import get_async_db
from models.models import User, UserRoleEnum, UserSession
from cryptography.fernet import Fernet
import base64

# Initialize logger
logger = security_logger

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token scheme
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against its hash.
    
    Args:
        plain_password: The plain text password
        hashed_password: The hashed password to verify against
        
    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        result = pwd_context.verify(plain_password, hashed_password)
        logger.debug("Password verification completed", success=result)
        return result
    except Exception as e:
        logger.error("Password verification error", error=str(e))
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a plain password.
    
    Args:
        password: The plain text password to hash
        
    Returns:
        str: The hashed password
    """
    try:
        hashed = pwd_context.hash(password)
        logger.debug("Password hash generated successfully")
        return hashed
    except Exception as e:
        logger.error("Password hashing error", error=str(e))
        raise


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: The data to encode in the token
        expires_delta: Optional custom expiration time
        
    Returns:
        str: The encoded JWT token
    """
    try:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        
        logger.info("Access token created", 
                   username=data.get("sub"), 
                   expires_at=expire.isoformat())
        return encoded_jwt
    except Exception as e:
        logger.error("Token creation error", error=str(e), username=data.get("sub"))
        raise


def create_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a general purpose JWT token (for password reset, account activation, etc.).
    
    Args:
        data: The data to encode in the token
        expires_delta: Optional custom expiration time
        
    Returns:
        str: The encoded JWT token
    """
    try:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(hours=24)  # Default 24 hours
        
        to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
        encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        
        logger.info("Token created", 
                   username=data.get("sub"),
                   type=data.get("type", "unknown"),
                   expires_at=expire.isoformat())
        return encoded_jwt
    except Exception as e:
        logger.error("Token creation error", 
                    error=str(e), 
                    username=data.get("sub"),
                    type=data.get("type", "unknown"))
        raise


def verify_token(token: str) -> Optional[dict]:
    """
    Verify and decode a JWT token.
    
    Args:
        token: The JWT token to verify
        
    Returns:
        dict: The decoded token payload if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        logger.debug("Token verified successfully", username=payload.get("sub"))
        return payload
    except JWTError as e:
        logger.warning("Token verification failed", error=str(e))
        return None
    except Exception as e:
        logger.error("Token verification error", error=str(e))
        return None


async def get_current_user(token: HTTPAuthorizationCredentials = Depends(security), db: AsyncSession = Depends(get_async_db)) -> User:
    """
    Get the current user from the JWT token.
    
    Args:
        token: The JWT token from the Authorization header
        db: Database session
        
    Returns:
        User: The current user if authentication is successful
        
    Raises:
        HTTPException: If authentication fails
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Verify the token
        payload = jwt.decode(token.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        username = payload.get("sub")
        if username is None:
            logger.warning("Token missing username claim")
            raise credentials_exception
        
        # Find the user
        user_stmt = select(User).where(User.username == username)
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        if user is None:
            logger.warning("User not found for token", username=username)
            raise credentials_exception
        
        # Get the token from the Authorization header
        token_value = token.credentials

        # Check if session is still valid
        session_stmt = select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.session_token == token_value,  # Check the specific token
            or_(
                UserSession.expires_at > datetime.now(timezone.utc),
                UserSession.expires_at.is_(None)
            )  # Check if not expired
        )
        session_result = await db.execute(session_stmt)
        session = session_result.scalar_one_or_none()

        if not session:
            logger.warning("No valid session found", username=username, user_id=user.id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalidated. Please log in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user
        
    except JWTError as e:
        logger.warning("JWT verification failed", error=str(e))
        raise credentials_exception
    except Exception as e:
        logger.error("Authentication error", error=str(e))
        raise credentials_exception


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Check if the current user is active.
    
    Args:
        current_user: The current authenticated user
        
    Returns:
        User: The current user if active
        
    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        logger.warning("Inactive user attempted access", 
                      username=current_user.username, 
                      user_id=current_user.id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user


async def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Check if the current user is an admin.
    
    Args:
        current_user: The current authenticated user
        
    Returns:
        User: The current user if admin
        
    Raises:
        HTTPException: If user is not an admin
    """
    if current_user.role != UserRoleEnum.admin:
        logger.warning("Non-admin user attempted admin action", 
                      username=current_user.username, 
                      user_id=current_user.id,
                      role=current_user.role.value)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user


# API Key Encryption/Decryption Functions
def _get_encryption_key() -> bytes:
    """Get or generate encryption key for API keys."""
    # Use JWT secret as base for encryption key
    key_material = settings.jwt_secret_key.encode()
    # Ensure the key is 32 bytes for Fernet
    if len(key_material) < 32:
        key_material = key_material.ljust(32, b'0')
    else:
        key_material = key_material[:32]
    
    # Encode as base64 for Fernet
    return base64.urlsafe_b64encode(key_material)


def encrypt_api_key(plain_api_key: str) -> str:
    """
    Encrypt an API key for secure storage.
    
    Args:
        plain_api_key: The plain text API key
        
    Returns:
        str: The encrypted API key (base64 encoded)
    """
    if not plain_api_key:
        return ""
    
    f = Fernet(_get_encryption_key())
    encrypted_bytes = f.encrypt(plain_api_key.encode())
    return base64.urlsafe_b64encode(encrypted_bytes).decode()


def decrypt_api_key(encrypted_api_key: str) -> str:
    """
    Decrypt an API key for use.
    
    Args:
        encrypted_api_key: The encrypted API key (base64 encoded)
        
    Returns:
        str: The decrypted API key
    """
    if not encrypted_api_key:
        return ""
    
    try:
        f = Fernet(_get_encryption_key())
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_api_key.encode())
        decrypted_bytes = f.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()
    except Exception as e:
        # If decryption fails, it might be a plain text key (for backward compatibility)
        # In production, you might want to handle this differently
        return encrypted_api_key
