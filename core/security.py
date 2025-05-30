"""
Security utilities for password hashing and JWT token handling.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from core.config import settings
from core.logging import get_logger, security_logger
from db_config import get_db
from models.models import User, UserRoleEnum
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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    
    Args:
        credentials: The HTTP authorization credentials
        db: Database session
        
    Returns:
        User: The authenticated user
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = verify_token(token)
        
        if payload is None:
            logger.warning("Invalid token provided")
            raise credentials_exception
        
        username: str = payload.get("sub")
        if username is None:
            logger.warning("Token missing username")
            raise credentials_exception
        
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            logger.warning("User not found", username=username)
            raise credentials_exception
        
        if not user.is_active:
            logger.warning("Inactive user attempted access", username=username, user_id=user.id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Inactive user"
            )
        
        logger.debug("User authenticated successfully", username=username, user_id=user.id)
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error", error=str(e))
        raise credentials_exception


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to ensure the current user is active.
    
    Args:
        current_user: The current authenticated user
        
    Returns:
        User: The active user
        
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        logger.warning("Inactive user access denied", username=current_user.username, user_id=current_user.id)
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Get the current user, but verify they have admin privileges.
    
    Args:
        current_user: The current authenticated user
        
    Returns:
        The current user if they have admin privileges
        
    Raises:
        HTTPException: If the user is not an admin
    """
    if current_user.role != UserRoleEnum.admin:
        logger.warning("Non-admin user attempted admin access", 
                      username=current_user.username, 
                      user_id=current_user.id, 
                      role=current_user.role.value)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have admin privileges"
        )
    
    logger.info("Admin user access granted", 
               username=current_user.username, 
               user_id=current_user.id)
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
