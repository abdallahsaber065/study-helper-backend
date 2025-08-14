"""File management routes."""

import math
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db_session
from app.files.models import FileMetadata
from app.files.schemas import (
    FileDeleteResponse,
    FileListResponse,
    FileMetadataResponse,
    FileUpdateRequest,
    FileUploadResponse,
    FileValidationError
)
from app.files.utils import (
    FileValidationError as FileValidationException,
    calculate_file_hash,
    create_file_response,
    delete_file_from_disk,
    generate_unique_filename,
    get_mime_type,
    save_file,
    validate_file
)
from app.users.models import User

router = APIRouter()


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    description: Optional[str] = Form(None, description="Optional file description"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> FileUploadResponse:
    """
    Upload a file for the authenticated user.
    
    Supported file types:
    - PDF files (application/pdf)
    - Plain text files (text/plain)
    - Markdown files (text/markdown)
    
    File size limit: 10MB
    """
    try:
        # Validate the file
        validate_file(file)
        
        # Generate unique filename
        stored_filename = generate_unique_filename(file.filename)
        
        # Save file to disk
        file_path, content, file_size = await save_file(file, stored_filename)
        
        # Calculate file hash for deduplication and integrity
        file_hash = calculate_file_hash(content)
        
        # Get MIME type
        mime_type = get_mime_type(file.filename)
        
        # Check if user already has a file with the same hash
        existing_file_stmt = select(FileMetadata).where(
            FileMetadata.user_id == current_user.id,
            FileMetadata.file_hash == file_hash
        )
        existing_file = await db.scalar(existing_file_stmt)
        
        if existing_file:
            # Delete the newly uploaded file since it's a duplicate
            delete_file_from_disk(file_path)
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_file",
                    "message": "You have already uploaded this file",
                    "existing_file_id": existing_file.id,
                    "existing_filename": existing_file.original_filename
                }
            )
        
        # Create file metadata record
        file_metadata = FileMetadata(
            user_id=current_user.id,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            file_hash=file_hash,
            description=description.strip() if description else None,
            is_processed=False
        )
        
        db.add(file_metadata)
        await db.commit()
        await db.refresh(file_metadata)
        
        return FileUploadResponse(
            id=file_metadata.id,
            original_filename=file_metadata.original_filename,
            file_size=file_metadata.file_size,
            mime_type=file_metadata.mime_type,
            created_at=file_metadata.created_at,
            message="File uploaded successfully"
        )
        
    except FileValidationException as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_error",
                "message": e.message,
                "details": e.details
            }
        )
    except Exception as e:
        # Clean up file if database operation failed
        if 'file_path' in locals():
            delete_file_from_disk(file_path)
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": "upload_failed",
                "message": "File upload failed due to server error"
            }
        )


@router.get("/", response_model=FileListResponse)
async def list_files(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search in filenames"),
    mime_type: Optional[str] = Query(None, description="Filter by MIME type"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> FileListResponse:
    """
    List files for the authenticated user with pagination and filtering.
    """
    # Build base query
    query = select(FileMetadata).where(FileMetadata.user_id == current_user.id)
    
    # Apply search filter
    if search:
        search_term = f"%{search.strip()}%"
        query = query.where(FileMetadata.original_filename.ilike(search_term))
    
    # Apply MIME type filter
    if mime_type:
        query = query.where(FileMetadata.mime_type == mime_type)
    
    # Order by creation date (newest first)
    query = query.order_by(FileMetadata.created_at.desc())
    
    # Get total count for pagination
    count_query = select(func.count()).select_from(
        query.subquery()
    )
    total_count = await db.scalar(count_query)
    
    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    
    # Execute query
    result = await db.execute(query)
    files = result.scalars().all()
    
    # Calculate total size
    size_query = select(func.sum(FileMetadata.file_size)).where(
        FileMetadata.user_id == current_user.id
    )
    if search:
        search_term = f"%{search.strip()}%"
        size_query = size_query.where(FileMetadata.original_filename.ilike(search_term))
    if mime_type:
        size_query = size_query.where(FileMetadata.mime_type == mime_type)
    
    total_size = await db.scalar(size_query) or 0
    
    # Calculate pagination info
    has_next = offset + per_page < total_count
    
    return FileListResponse(
        files=[FileMetadataResponse.model_validate(file) for file in files],
        total_count=total_count,
        total_size=total_size,
        page=page,
        per_page=per_page,
        has_next=has_next
    )


@router.get("/{file_id}", response_model=FileMetadataResponse)
async def get_file_metadata(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> FileMetadataResponse:
    """Get metadata for a specific file."""
    # Get file metadata
    query = select(FileMetadata).where(
        FileMetadata.id == file_id,
        FileMetadata.user_id == current_user.id
    )
    file_metadata = await db.scalar(query)
    
    if not file_metadata:
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )
    
    return FileMetadataResponse.model_validate(file_metadata)


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Download a file."""
    # Get file metadata
    query = select(FileMetadata).where(
        FileMetadata.id == file_id,
        FileMetadata.user_id == current_user.id
    )
    file_metadata = await db.scalar(query)
    
    if not file_metadata:
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )
    
    # Return file response
    return create_file_response(
        file_metadata.file_path,
        file_metadata.original_filename
    )


@router.put("/{file_id}", response_model=FileMetadataResponse)
async def update_file_metadata(
    file_id: str,
    update_data: FileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> FileMetadataResponse:
    """Update file metadata (description only)."""
    # Get file metadata
    query = select(FileMetadata).where(
        FileMetadata.id == file_id,
        FileMetadata.user_id == current_user.id
    )
    file_metadata = await db.scalar(query)
    
    if not file_metadata:
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )
    
    # Update description
    file_metadata.description = update_data.description
    
    await db.commit()
    await db.refresh(file_metadata)
    
    return FileMetadataResponse.model_validate(file_metadata)


@router.delete("/{file_id}", response_model=FileDeleteResponse)
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> FileDeleteResponse:
    """Delete a file and its metadata."""
    # Get file metadata
    query = select(FileMetadata).where(
        FileMetadata.id == file_id,
        FileMetadata.user_id == current_user.id
    )
    file_metadata = await db.scalar(query)
    
    if not file_metadata:
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )
    
    # Delete file from disk
    delete_file_from_disk(file_metadata.file_path)
    
    # Delete metadata from database
    await db.delete(file_metadata)
    await db.commit()
    
    return FileDeleteResponse(
        message="File deleted successfully",
        deleted_file_id=file_id
    )


@router.delete("/", response_model=dict)
async def delete_all_files(
    confirm: bool = Query(False, description="Confirmation to delete all files"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Delete all files for the authenticated user."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "confirmation_required",
                "message": "Set confirm=true to delete all files"
            }
        )
    
    # Get all files for user
    query = select(FileMetadata).where(FileMetadata.user_id == current_user.id)
    result = await db.execute(query)
    files = result.scalars().all()
    
    if not files:
        return {"message": "No files to delete"}
    
    deleted_count = 0
    # Delete files from disk and database
    for file_metadata in files:
        delete_file_from_disk(file_metadata.file_path)
        await db.delete(file_metadata)
        deleted_count += 1
    
    await db.commit()
    
    return {
        "message": f"Successfully deleted {deleted_count} files",
        "deleted_count": deleted_count
    }
