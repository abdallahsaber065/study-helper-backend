"""
Router for Content Versioning.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from db_config import get_db
from core.security import get_current_user
from models.models import User, ContentTypeEnum
from schemas.versioning import (
    ContentVersionRead, ContentVersionListResponse, ContentVersionCompareResponse,
    ContentRestoreResponse
)
from services.versioning_service import ContentVersioningService

router = APIRouter(prefix="/versioning", tags=["Content Versioning"])


@router.post("/content/{content_type}/{content_id}/create-version", response_model=ContentVersionRead)
async def create_content_version(
    content_type: ContentTypeEnum,
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new version of content."""
    versioning_service = ContentVersioningService(db)
    
    # TODO: Add permission check - user should own the content or have edit rights
    
    version = versioning_service.create_version(
        content_type=content_type,
        content_id=content_id,
        user_id=current_user.id
    )
    
    # Convert to read schema with user details
    version_read = ContentVersionRead.from_orm(version)
    version_read.username = current_user.username
    version_read.first_name = current_user.first_name
    version_read.last_name = current_user.last_name
    
    return version_read


@router.get("/content/{content_type}/{content_id}/versions", response_model=ContentVersionListResponse)
async def get_content_versions(
    content_type: ContentTypeEnum,
    content_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get all versions for specific content."""
    versioning_service = ContentVersioningService(db)
    
    versions, total_count, current_version = versioning_service.get_content_versions(
        content_type=content_type,
        content_id=content_id,
        skip=skip,
        limit=limit
    )
    
    return ContentVersionListResponse(
        versions=versions,
        total_count=total_count,
        current_version=current_version,
        has_more=(skip + limit) < total_count
    )


@router.get("/content/{content_type}/{content_id}/versions/{version_number}", response_model=ContentVersionRead)
async def get_specific_version(
    content_type: ContentTypeEnum,
    content_id: int,
    version_number: int,
    db: Session = Depends(get_db)
):
    """Get a specific version of content."""
    versioning_service = ContentVersioningService(db)
    
    version = versioning_service.get_version(
        content_type=content_type,
        content_id=content_id,
        version_number=version_number
    )
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found"
        )
    
    return version


@router.get("/content/{content_type}/{content_id}/compare", response_model=ContentVersionCompareResponse)
async def compare_versions(
    content_type: ContentTypeEnum,
    content_id: int,
    version_a: int = Query(..., description="First version to compare"),
    version_b: int = Query(..., description="Second version to compare"),
    db: Session = Depends(get_db)
):
    """Compare two versions of content."""
    versioning_service = ContentVersioningService(db)
    
    comparison = versioning_service.compare_versions(
        content_type=content_type,
        content_id=content_id,
        version_a=version_a,
        version_b=version_b
    )
    
    return comparison


@router.post("/content/{content_type}/{content_id}/restore/{version_number}", response_model=ContentRestoreResponse)
async def restore_content_version(
    content_type: ContentTypeEnum,
    content_id: int,
    version_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore content to a previous version."""
    versioning_service = ContentVersioningService(db)
    
    # TODO: Add permission check - user should own the content or have edit rights
    
    result = versioning_service.restore_version(
        content_type=content_type,
        content_id=content_id,
        version_number=version_number,
        user_id=current_user.id
    )
    
    return result


@router.delete("/content/{content_type}/{content_id}/cleanup-versions")
async def cleanup_old_versions(
    content_type: ContentTypeEnum,
    content_id: int,
    keep_latest: int = Query(10, ge=1, le=50, description="Number of latest versions to keep"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete old versions, keeping only the latest N versions."""
    versioning_service = ContentVersioningService(db)
    
    # TODO: Add permission check - user should own the content or be admin
    
    deleted_count = versioning_service.delete_old_versions(
        content_type=content_type,
        content_id=content_id,
        keep_latest=keep_latest
    )
    
    return {
        "message": f"Deleted {deleted_count} old versions",
        "deleted_count": deleted_count,
        "kept_latest": keep_latest
    } 