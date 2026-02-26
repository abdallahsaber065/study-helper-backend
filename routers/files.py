"""
File upload and management routes.
"""
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, select, and_, delete

from core.security import get_current_active_user
from core.file_utils import save_upload_file, validate_file_type, validate_file_size
from db_config import get_async_db
from models.models import User, PhysicalFile, UserFileAccess
from schemas.file import FileRead, FileUploadResponse, UserFileAccessCreate, UserFileAccessRead, FileAccessList

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Upload a file.
    
    - Supports PDF, TXT, DOCX, DOC
    - Maximum file size: 50MB (configurable)
    - Files are deduplicated based on content hash
    """
    # Validate file type
    if not validate_file_type(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed types: PDF, TXT, DOCX, DOC"
        )
    
    # Get file content for validation and hashing
    file_content = await file.read()
    file_size = len(file_content)
    
    # Reset file position for later use
    await file.seek(0)
    
    # Validate file size
    if not validate_file_size(file_size):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: 50MB"
        )
    
    # Save file and get metadata
    file_path, file_hash, file_size, mime_type = await save_upload_file(file)
    
    # Check if file already exists (by hash)
    existing_file_stmt = select(PhysicalFile).where(PhysicalFile.file_hash == file_hash)
    existing_file_result = await db.execute(existing_file_stmt)
    existing_file = existing_file_result.scalar_one_or_none()
    
    if existing_file:
        # Check if current user already has access to this file
        access_stmt = select(UserFileAccess).where(
            UserFileAccess.user_id == current_user.id,
            UserFileAccess.physical_file_id == existing_file.id
        )
        access_result = await db.execute(access_stmt)
        existing_access = access_result.scalar_one_or_none()
        
        if not existing_access:
            # Grant access to existing file
            new_access = UserFileAccess(
                user_id=current_user.id,
                physical_file_id=existing_file.id,
                access_level="read",  # Default to read access
                granted_by_user_id=existing_file.user_id  # Original uploader grants access
            )
            db.add(new_access)
            await db.commit()
        
        return FileUploadResponse(
            message="File already exists. Access granted.",
            file=existing_file
        )
    
    # Create new file record
    new_file = PhysicalFile(
        file_hash=file_hash,
        file_name=file.filename,
        file_path=file_path,
        file_type=os.path.splitext(file.filename)[1].lower().replace(".", ""),
        file_size_bytes=file_size,
        mime_type=mime_type,
        user_id=current_user.id  # Set current user as uploader
    )
    
    db.add(new_file)
    await db.commit()
    await db.refresh(new_file)
    
    # Create access record for the uploader
    user_access = UserFileAccess(
        user_id=current_user.id,
        physical_file_id=new_file.id,
        access_level="admin",  # Uploader gets admin access
        granted_by_user_id=current_user.id  # Self-granted
    )
    
    db.add(user_access)
    await db.commit()
    
    return FileUploadResponse(
        message="File uploaded successfully",
        file=new_file
    )


@router.get("/", response_model=List[FileRead])
async def get_user_files(
    skip: int = Query(0, ge=0, description="Number of files to skip"),
    limit: int = Query(100, ge=1, le=100, description="Number of files to return"),
    search: Optional[str] = Query(None, description="Search by filename"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get list of files accessible to the current user.
    """
    # Query files the user has access to
    stmt = select(PhysicalFile).join(
        UserFileAccess,
        PhysicalFile.id == UserFileAccess.physical_file_id
    ).where(
        UserFileAccess.user_id == current_user.id
    )
    
    # Apply search filter
    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(PhysicalFile.file_name.ilike(search_term))
    
    stmt = stmt.order_by(PhysicalFile.uploaded_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    files = result.scalars().all()
    
    return files


@router.get("/{file_id}", response_model=FileRead)
async def get_file_by_id(
    file_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific file by ID.
    """
    # Query the file and check access
    stmt = select(PhysicalFile).join(
        UserFileAccess,
        PhysicalFile.id == UserFileAccess.physical_file_id
    ).where(
        PhysicalFile.id == file_id,
        UserFileAccess.user_id == current_user.id
    )
    
    result = await db.execute(stmt)
    file = result.scalar_one_or_none()
    
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or you don't have access"
        )
    
    return file


@router.post("/{file_id}/share", response_model=UserFileAccessRead)
async def share_file(
    file_id: int,
    user_id: int = Form(..., description="ID of the user to share with"),
    access_level: str = Form("read", description="Access level (read, write, admin)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Share a file with another user.
    """
    # Check if file exists and current user has admin access
    access_stmt = select(UserFileAccess).where(
        UserFileAccess.physical_file_id == file_id,
        UserFileAccess.user_id == current_user.id,
        UserFileAccess.access_level == "admin"
    )
    access_result = await db.execute(access_stmt)
    file_access = access_result.scalar_one_or_none()
    
    if not file_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have admin access to this file"
        )
    
    # Check if target user exists
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    target_user = user_result.scalar_one_or_none()
    
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user not found"
        )
    
    # Validate access level
    if access_level not in ["read", "write", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid access level. Must be one of: read, write, admin"
        )
    
    # Check if user already has access
    existing_access_stmt = select(UserFileAccess).where(
        UserFileAccess.physical_file_id == file_id,
        UserFileAccess.user_id == user_id
    )
    existing_access_result = await db.execute(existing_access_stmt)
    existing_access = existing_access_result.scalar_one_or_none()
    
    if existing_access:
        # Update existing access
        existing_access.access_level = access_level
        existing_access.granted_by_user_id = current_user.id
        await db.commit()
        await db.refresh(existing_access)
        return existing_access
    
    # Create new access
    new_access = UserFileAccess(
        user_id=user_id,
        physical_file_id=file_id,
        access_level=access_level,
        granted_by_user_id=current_user.id
    )
    
    db.add(new_access)
    await db.commit()
    await db.refresh(new_access)
    
    return new_access


@router.delete("/{file_id}/share/{user_id}")
async def revoke_file_access(
    file_id: int,
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Revoke access to a file from a user.
    """
    # Check if current user has admin access to the file
    admin_access_stmt = select(UserFileAccess).where(
        UserFileAccess.physical_file_id == file_id,
        UserFileAccess.user_id == current_user.id,
        UserFileAccess.access_level == "admin"
    )
    admin_access_result = await db.execute(admin_access_stmt)
    admin_access = admin_access_result.scalar_one_or_none()
    
    if not admin_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have admin access to this file"
        )
    
    # Don't allow revoking own access
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke your own access"
        )
    
    # Find the access to revoke
    access_to_revoke_stmt = select(UserFileAccess).where(
        UserFileAccess.physical_file_id == file_id,
        UserFileAccess.user_id == user_id
    )
    access_to_revoke_result = await db.execute(access_to_revoke_stmt)
    access_to_revoke = access_to_revoke_result.scalar_one_or_none()
    
    if not access_to_revoke:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User doesn't have access to this file"
        )
    
    await db.delete(access_to_revoke)
    await db.commit()
    
    return {"message": "File access revoked successfully"}


@router.get("/{file_id}/access", response_model=List[UserFileAccessRead])
async def get_file_access_list(
    file_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get list of users who have access to a file.
    """
    # Check if current user has access to the file
    user_access_stmt = select(UserFileAccess).where(
        UserFileAccess.physical_file_id == file_id,
        UserFileAccess.user_id == current_user.id
    )
    user_access_result = await db.execute(user_access_stmt)
    user_access = user_access_result.scalar_one_or_none()
    
    if not user_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this file"
        )
    
    # Get all users with access to this file
    access_list_stmt = select(UserFileAccess).options(
        selectinload(UserFileAccess.user),
        selectinload(UserFileAccess.granted_by)
    ).where(UserFileAccess.physical_file_id == file_id)
    
    access_list_result = await db.execute(access_list_stmt)
    access_list = access_list_result.scalars().all()
    
    return access_list 