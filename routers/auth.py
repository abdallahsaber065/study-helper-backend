"""
Authentication routes for user registration, login, and user management.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.security import (
    get_password_hash, 
    verify_password, 
    create_access_token,
    get_current_user,
    get_current_active_user
)
from core.config import settings
from db_config import get_db
from models.models import User, UserSession, UserRoleEnum
from schemas.user import UserCreate, UserRead, UserUpdate
from schemas.auth import LoginRequest, LoginResponse, RegisterResponse, Token

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user.
    
    - **username**: Must be unique, 3-50 characters
    - **email**: Must be unique and valid email format
    - **password**: Minimum 8 characters
    - **first_name**: User's first name
    - **last_name**: User's last name
    """
    # Check if username already exists
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    if db.query(User).filter(User.email == user_data.email).first():
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
            message="User registered successfully",
            user=user_dict
        )
    
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username or email already exists"
        )


@router.post("/login", response_model=LoginResponse)
async def login_user(login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login user and return JWT token.
    
    - **username**: Username or email address
    - **password**: User's password
    """
    # Find user by username or email
    user = db.query(User).filter(
        (User.username == login_data.username) | (User.email == login_data.username)
    ).first()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
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
    user.last_login = datetime.utcnow()
    
    # Create or update user session
    session = db.query(UserSession).filter(UserSession.user_id == user.id).first()
    if session:
        session.session_token = access_token
        session.updated_at = datetime.utcnow()
        session.expires_at = datetime.utcnow() + access_token_expires
    else:
        session = UserSession(
            user_id=user.id,
            session_token=access_token,
            expires_at=datetime.utcnow() + access_token_expires
        )
        db.add(session)
    
    db.commit()
    
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
    # Find and delete the user's session
    session = db.query(UserSession).filter(UserSession.user_id == current_user.id).first()
    if session:
        db.delete(session)
        db.commit()
    
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserRead)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """
    Get current authenticated user's information.
    """
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
    
    current_user.updated_at = datetime.utcnow()
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
        session.updated_at = datetime.utcnow()
        session.expires_at = datetime.utcnow() + access_token_expires
        db.commit()
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60
    )
