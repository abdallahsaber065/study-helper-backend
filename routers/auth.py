"""
Authentication routes for user registration, login, and user management.
"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.security import (
    get_password_hash, 
    verify_password, 
    create_access_token,
    get_current_user,
    get_current_active_user,
    create_token,
    verify_token
)
from core.config import settings
from core.logging import get_logger
from db_config import get_db
from models.models import User, UserSession, UserRoleEnum
from schemas.user import UserCreate, UserRead, UserUpdate
from schemas.auth import (
    LoginRequest, 
    LoginResponse, 
    RegisterResponse, 
    Token,
    PasswordResetRequest,
    PasswordResetConfirm,
    PasswordResetResponse,
    ActivationRequest,
    ActivationResponse
)
from services.email_service import EmailService

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()

# Initialize logger for auth operations
logger = get_logger("auth")


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Register a new user.
    
    - **username**: Must be unique, 3-50 characters
    - **email**: Must be unique and valid email format
    - **password**: Minimum 8 characters
    - **first_name**: User's first name
    - **last_name**: User's last name
    """
    logger.info("User registration attempt", username=user_data.username, email=user_data.email)
    
    # Check if username already exists
    if db.query(User).filter(User.username == user_data.username).first():
        logger.warning("Registration failed - username already exists", username=user_data.username)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    if db.query(User).filter(User.email == user_data.email).first():
        logger.warning("Registration failed - email already exists", email=user_data.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash the password
    hashed_password = get_password_hash(user_data.password)
    
    # Create new user
    db_user = User(
        username=user_data.username,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        email=user_data.email,
        password_hash=hashed_password,
        role=UserRoleEnum.user,  # Default role
        is_active=True,
        is_verified=False  # Will need email verification in the future
    )
    
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        logger.info("User registered successfully", 
                   username=db_user.username, 
                   user_id=db_user.id, 
                   email=db_user.email)
        
        # Generate activation token
        activation_token = create_token(
            data={"sub": db_user.username, "type": "activation"},
            expires_delta=timedelta(hours=settings.activation_token_expire_hours)
        )
        
        # Send activation email in background
        email_service = EmailService()
        background_tasks.add_task(
            email_service.send_activation_email,
            to_email=db_user.email,
            username=db_user.username,
            token=activation_token
        )
        
        # Return user data without sensitive information
        user_dict = {
            "id": db_user.id,
            "username": db_user.username,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "email": db_user.email,
            "role": db_user.role.value,
            "is_active": db_user.is_active,
            "is_verified": db_user.is_verified,
            "created_at": db_user.created_at
        }
        
        return RegisterResponse(
            message="User registered successfully. Please check your email to activate your account.",
            user=user_dict
        )
    
    except IntegrityError as e:
        db.rollback()
        logger.error("Registration failed - database integrity error", 
                    username=user_data.username, 
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username or email already exists"
        )
    except Exception as e:
        db.rollback()
        logger.error("Registration failed - unexpected error", 
                    username=user_data.username, 
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to server error"
        )


@router.post("/login", response_model=LoginResponse)
async def login_user(login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login user and return JWT token.
    
    - **username**: Username or email address
    - **password**: User's password
    """
    logger.info("Login attempt", username_or_email=login_data.username)
    
    # Find user by username or email
    user = db.query(User).filter(
        (User.username == login_data.username) | (User.email == login_data.username)
    ).first()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        logger.warning("Login failed - invalid credentials", username_or_email=login_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        logger.warning("Login failed - account deactivated", 
                      username=user.username, 
                      user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
    
    # Create or update user session
    session = db.query(UserSession).filter(UserSession.user_id == user.id).first()
    if session:
        session.session_token = access_token
        session.updated_at = datetime.now(timezone.utc)
        session.expires_at = datetime.now(timezone.utc) + access_token_expires
        logger.debug("Updated existing user session", username=user.username, user_id=user.id)
    else:
        session = UserSession(
            user_id=user.id,
            session_token=access_token,
            expires_at=datetime.now(timezone.utc) + access_token_expires
        )
        db.add(session)
        logger.debug("Created new user session", username=user.username, user_id=user.id)
    
    db.commit()
    
    logger.info("Login successful", 
               username=user.username, 
               user_id=user.id, 
               role=user.role.value)
    
    # Return user data without sensitive information
    user_dict = {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "last_login": user.last_login
    }
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_dict,
        expires_in=settings.jwt_access_token_expire_minutes * 60  # Convert to seconds
    )


@router.post("/logout")
async def logout_user(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """
    Logout user by invalidating their session.
    """
    logger.info("Logout request", username=current_user.username, user_id=current_user.id)
    
    # Find and delete the user's session
    session = db.query(UserSession).filter(UserSession.user_id == current_user.id).first()
    if session:
        db.delete(session)
        db.commit()
        logger.info("User session deleted", username=current_user.username, user_id=current_user.id)
    else:
        logger.warning("No session found for logout", username=current_user.username, user_id=current_user.id)
    
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserRead)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current authenticated user's information.
    """
    logger.debug("User info requested", username=current_user.username, user_id=current_user.id)
    return current_user


@router.put("/me", response_model=UserRead)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update current authenticated user's information.
    """
    logger.info("User profile update request", username=current_user.username, user_id=current_user.id)
    
    # Update only provided fields
    update_data = user_update.dict(exclude_unset=True)
    
    # Check if email is being updated and if it's already taken
    if "email" in update_data:
        existing_user = db.query(User).filter(
            User.email == update_data["email"],
            User.id != current_user.id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Apply updates
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    current_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(current_user)
    
    return current_user


@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Refresh JWT token for current user.
    """
    # Create new access token
    access_token_expires = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": current_user.username}, expires_delta=access_token_expires
    )
    
    # Update session with new token
    session = db.query(UserSession).filter(UserSession.user_id == current_user.id).first()
    if session:
        session.session_token = access_token
        session.updated_at = datetime.now(timezone.utc)
        session.expires_at = datetime.now(timezone.utc) + access_token_expires
        db.commit()
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60
    )


@router.post("/password-reset", response_model=PasswordResetResponse)
async def request_password_reset(
    reset_request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Request a password reset email.
    
    - **email**: Email address associated with the account
    """
    logger.info("Password reset requested", email=reset_request.email)
    
    # Find user by email
    user = db.query(User).filter(User.email == reset_request.email).first()
    
    # Always return success even if email not found (to prevent email enumeration)
    if not user:
        logger.warning("Password reset requested for nonexistent email", email=reset_request.email)
        return PasswordResetResponse(
            message="If your email is registered, a password reset link has been sent."
        )
    
    # Generate password reset token
    reset_token = create_token(
        data={"sub": user.username, "type": "password_reset"},
        expires_delta=timedelta(hours=settings.password_reset_token_expire_hours)
    )
    
    # Send password reset email in background
    email_service = EmailService()
    background_tasks.add_task(
        email_service.send_password_reset_email,
        to_email=user.email,
        username=user.username,
        token=reset_token
    )
    
    logger.info("Password reset email sent", username=user.username, user_id=user.id)
    
    return PasswordResetResponse(
        message="If your email is registered, a password reset link has been sent."
    )


@router.post("/password-reset/confirm", response_model=PasswordResetResponse)
async def confirm_password_reset(
    reset_confirm: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """
    Reset password using a token from the reset email.
    
    - **token**: Password reset token
    - **new_password**: New password (minimum 8 characters)
    """
    # Verify the token
    token_data = verify_token(reset_confirm.token)
    
    if not token_data or token_data.get("type") != "password_reset":
        logger.warning("Invalid password reset token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token"
        )
    
    # Get the username from the token
    username = token_data.get("sub")
    if not username:
        logger.error("Token missing username claim")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token format"
        )
    
    # Find the user
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.error("User not found for password reset", username=username)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Hash the new password
    new_password_hash = get_password_hash(reset_confirm.new_password)
    
    # Update the password
    user.password_hash = new_password_hash
    user.updated_at = datetime.now(timezone.utc)
    
    # Invalidate all sessions (force logout on all devices)
    sessions = db.query(UserSession).filter(UserSession.user_id == user.id).all()
    for session in sessions:
        db.delete(session)
    
    db.commit()
    
    logger.info("Password reset successful", username=user.username, user_id=user.id)
    
    return PasswordResetResponse(
        message="Password has been reset successfully. Please log in with your new password."
    )


@router.post("/activate", response_model=ActivationResponse)
async def activate_account(
    activation_request: ActivationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Activate a user account using the token sent via email.
    
    - **token**: Account activation token
    """
    # Verify the token
    token_data = verify_token(activation_request.token)
    
    if not token_data or token_data.get("type") != "activation":
        logger.warning("Invalid activation token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token"
        )
    
    # Get the username from the token
    username = token_data.get("sub")
    if not username:
        logger.error("Token missing username claim")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token format"
        )
    
    # Find the user
    user = db.query(User).filter(User.username == username).first()
    if not user:
        logger.error("User not found for activation", username=username)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if already verified
    if user.is_verified:
        logger.info("Account already verified", username=user.username, user_id=user.id)
        return ActivationResponse(
            message="Your account is already activated.",
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_verified": user.is_verified
            }
        )
    
    # Activate the account
    user.is_verified = True
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    
    logger.info("Account activated successfully", username=user.username, user_id=user.id)
    
    # Send welcome email in background
    email_service = EmailService()
    background_tasks.add_task(
        email_service.send_welcome_email,
        to_email=user.email,
        username=user.username
    )
    
    return ActivationResponse(
        message="Your account has been activated successfully. You can now log in.",
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_verified": user.is_verified
        }
    )
