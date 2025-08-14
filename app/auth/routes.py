"""Authentication routes."""

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.auth.utils import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.database import get_db_session
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
    UserCreate,
    UserResponse,
)
from app.services.email_service import get_email_service
from app.users.models import EmailVerificationToken, User

router = APIRouter()
settings = get_settings()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    Register a new user and send verification email.
    
    Args:
        user_data: User registration data
        request: HTTP request object for IP address
        db: Database session
        
    Returns:
        Created user information
        
    Raises:
        HTTPException: If email already exists or email service fails
    """
    # Check if user already exists
    stmt = select(User).where(User.email == user_data.email)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash the password
    hashed_password = hash_password(user_data.password)
    
    # Create new user
    new_user = User(
        email=user_data.email,
        hashed_password=hashed_password,
        is_active=True,
        is_verified=False,  # Will be verified via email
    )
    
    try:
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        # Send verification email if enabled
        if settings.enable_email_verification:
            await _send_verification_email(new_user, request, db)
        
        return UserResponse.model_validate(new_user)
    
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )


@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    
    Args:
        form_data: OAuth2 password request form
        db: Database session
        
    Returns:
        Access token and refresh token
        
    Raises:
        HTTPException: If credentials are incorrect
    """
    # Query user by email (username field in OAuth2 form)
    stmt = select(User).where(User.email == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    # Verify user exists and password is correct
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Create tokens
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,  # Convert to seconds
    )


@router.post("/login", response_model=Token)
async def login_json(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    JSON login endpoint (alternative to OAuth2 form-based login).
    
    Args:
        login_data: Login credentials
        db: Database session
        
    Returns:
        Access token and refresh token
        
    Raises:
        HTTPException: If credentials are incorrect
    """
    # Query user by email
    stmt = select(User).where(User.email == login_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    # Verify user exists and password is correct
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Create tokens
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,  # Convert to seconds
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Logout endpoint.
    
    Note: With JWT tokens, we can't truly invalidate tokens without a blacklist.
    This endpoint mainly exists for client-side token cleanup.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Success message
    """
    return MessageResponse(
        message="Successfully logged out",
        detail="Please remove the token from client storage"
    )


@router.post("/verify-email/{token}", response_model=MessageResponse)
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    Verify user email with token.
    
    Args:
        token: Email verification token
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If token is invalid, expired, or already used
    """
    # Find the token
    stmt = select(EmailVerificationToken).where(
        EmailVerificationToken.token_hash == EmailVerificationToken.hash_token(token),
        EmailVerificationToken.token_type == "verification"
    )
    result = await db.execute(stmt)
    token_record = result.scalar_one_or_none()
    
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid verification token"
        )
    
    if not token_record.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token has expired or been used"
        )
    
    # Get the user
    stmt = select(User).where(User.id == token_record.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    # Mark token as used and user as verified
    token_record.mark_as_used()
    user.is_verified = True
    
    await db.commit()
    
    # Send welcome email
    email_service = get_email_service()
    await email_service.send_welcome_email(
        to_email=user.email,
        user_name=user.email.split("@")[0]  # Use email prefix as name
    )
    
    return MessageResponse(
        message="Email successfully verified",
        detail="Welcome! Your account is now active."
    )


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification_email(
    email: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    Resend verification email.
    
    Args:
        email: User email address
        request: HTTP request object
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If user not found or already verified
    """
    # Find the user
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        # Don't reveal if user exists for security
        return MessageResponse(
            message="If the email exists, a verification link has been sent",
            detail="Check your inbox for the verification email"
        )
    
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified"
        )
    
    # Send verification email
    await _send_verification_email(user, request, db)
    
    return MessageResponse(
        message="Verification email sent",
        detail="Check your inbox for the verification link"
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    password_reset_data: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    Request password reset.
    
    Args:
        password_reset_data: Password reset request data
        request: HTTP request object
        db: Database session
        
    Returns:
        Success message
    """
    # Find the user
    stmt = select(User).where(User.email == password_reset_data.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    # Always return success for security (don't reveal if email exists)
    if not user:
        return MessageResponse(
            message="If the email exists, a password reset link has been sent",
            detail="Check your inbox for the password reset email"
        )
    
    if not user.is_active:
        return MessageResponse(
            message="If the email exists, a password reset link has been sent",
            detail="Check your inbox for the password reset email"
        )
    
    # Create password reset token
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent")
    
    token_record, raw_token = EmailVerificationToken.create_verification_token(
        user_id=user.id,
        token_type="reset",
        ip_address=ip_address,
        user_agent=user_agent,
        expires_hours=settings.password_reset_expire_hours
    )
    
    db.add(token_record)
    await db.commit()
    
    # Send password reset email
    reset_url = f"{request.base_url}auth/reset-password/{raw_token}"
    email_service = get_email_service()
    await email_service.send_password_reset_email(
        to_email=user.email,
        user_name=user.email.split("@")[0],
        reset_url=reset_url
    )
    
    return MessageResponse(
        message="Password reset link sent",
        detail="Check your inbox for the password reset email"
    )


@router.post("/reset-password/{token}", response_model=MessageResponse)
async def reset_password(
    token: str,
    password_reset_data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """
    Reset password with token.
    
    Args:
        token: Password reset token from URL
        password_reset_data: New password data
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If token is invalid, expired, or already used
    """
    # Verify token matches the one in request body
    if token != password_reset_data.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token mismatch"
        )
    
    # Find the token
    stmt = select(EmailVerificationToken).where(
        EmailVerificationToken.token_hash == EmailVerificationToken.hash_token(token),
        EmailVerificationToken.token_type == "reset"
    )
    result = await db.execute(stmt)
    token_record = result.scalar_one_or_none()
    
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid reset token"
        )
    
    if not token_record.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token has expired or been used"
        )
    
    # Get the user
    stmt = select(User).where(User.id == token_record.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password and mark token as used
    user.hashed_password = hash_password(password_reset_data.new_password)
    token_record.mark_as_used()
    
    await db.commit()
    
    # Send password changed notification
    email_service = get_email_service()
    await email_service.send_password_changed_notification(
        to_email=user.email,
        user_name=user.email.split("@")[0]
    )
    
    return MessageResponse(
        message="Password successfully reset",
        detail="You can now log in with your new password"
    )


async def _send_verification_email(
    user: User, 
    request: Request, 
    db: AsyncSession
) -> None:
    """
    Send verification email to user.
    
    Args:
        user: User to send verification email to
        request: HTTP request object
        db: Database session
        
    Raises:
        HTTPException: If email service fails
    """
    try:
        # Create verification token
        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent")
        
        token_record, raw_token = EmailVerificationToken.create_verification_token(
            user_id=user.id,
            token_type="verification",
            ip_address=ip_address,
            user_agent=user_agent,
            expires_hours=settings.email_verification_expire_hours
        )
        
        db.add(token_record)
        await db.commit()
        
        # Send verification email
        verification_url = f"{request.base_url}auth/verify-email/{raw_token}"
        email_service = get_email_service()
        
        success = await email_service.send_verification_email(
            to_email=user.email,
            user_name=user.email.split("@")[0],  # Use email prefix as name
            verification_url=verification_url
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email"
            )
            
    except Exception as e:
        await db.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email"
        )
