"""
Content versioning service for tracking content changes.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
import json
import difflib

from models.models import (
    User, ContentVersion, ContentTypeEnum, Summary, McqQuiz, PhysicalFile
)
from schemas.versioning import (
    ContentVersionCreate, ContentVersionRead, ContentVersionListResponse,
    ContentVersionCompareResponse, ContentRestoreResponse
)


class ContentVersioningService:
    """Service for managing content versions."""

    def __init__(self, db: Session):
        self.db = db

    def _get_content_data(self, content_type: ContentTypeEnum, content_id: int) -> Optional[Dict[str, Any]]:
        """Get current content data as a dictionary."""
        if content_type == ContentTypeEnum.summary:
            content = self.db.query(Summary).filter(Summary.id == content_id).first()
            if content:
                return {
                    "id": content.id,
                    "title": content.title,
                    "full_markdown": content.full_markdown,
                    "user_id": content.user_id,
                    "physical_file_id": content.physical_file_id,
                    "community_id": content.community_id,
                    "created_at": content.created_at.isoformat(),
                    "updated_at": content.updated_at.isoformat()
                }
        elif content_type == ContentTypeEnum.quiz:
            content = self.db.query(McqQuiz).filter(McqQuiz.id == content_id).first()
            if content:
                return {
                    "id": content.id,
                    "title": content.title,
                    "description": content.description,
                    "difficulty_level": content.difficulty_level.value,
                    "is_active": content.is_active,
                    "is_public": content.is_public,
                    "user_id": content.user_id,
                    "subject_id": content.subject_id,
                    "community_id": content.community_id,
                    "created_at": content.created_at.isoformat(),
                    "updated_at": content.updated_at.isoformat()
                }
        elif content_type == ContentTypeEnum.file:
            content = self.db.query(PhysicalFile).filter(PhysicalFile.id == content_id).first()
            if content:
                return {
                    "id": content.id,
                    "file_name": content.file_name,
                    "file_type": content.file_type,
                    "file_size_bytes": content.file_size_bytes,
                    "mime_type": content.mime_type,
                    "user_id": content.user_id,
                    "uploaded_at": content.uploaded_at.isoformat()
                }
        return None

    def _verify_content_exists(self, content_type: ContentTypeEnum, content_id: int) -> bool:
        """Verify that content exists."""
        return self._get_content_data(content_type, content_id) is not None

    def create_version(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        user_id: int
    ) -> ContentVersion:
        """Create a new version of content."""
        # Verify content exists
        if not self._verify_content_exists(content_type, content_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{content_type.value.title()} not found"
            )

        # Get current content data
        content_data = self._get_content_data(content_type, content_id)
        if not content_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to capture content data"
            )

        # Get next version number
        latest_version = self.db.query(ContentVersion).filter(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id
        ).order_by(ContentVersion.version_number.desc()).first()

        version_number = (latest_version.version_number + 1) if latest_version else 1

        # Create version record
        version = ContentVersion(
            content_type=content_type,
            content_id=content_id,
            user_id=user_id,
            version_number=version_number,
            version_data=content_data
        )

        self.db.add(version)
        self.db.commit()
        self.db.refresh(version)
        
        return version

    def get_content_versions(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[ContentVersionRead], int, int]:
        """Get versions for content with pagination."""
        # Verify content exists
        if not self._verify_content_exists(content_type, content_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{content_type.value.title()} not found"
            )

        query = self.db.query(ContentVersion).options(
            joinedload(ContentVersion.user_creator)
        ).filter(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id
        )

        total_count = query.count()
        
        # Get current version number
        latest_version = query.order_by(ContentVersion.version_number.desc()).first()
        current_version = latest_version.version_number if latest_version else 1

        # Get paginated results
        versions = query.order_by(
            ContentVersion.version_number.desc()
        ).offset(skip).limit(limit).all()

        # Convert to read schemas
        version_reads = []
        for version in versions:
            version_read = ContentVersionRead.from_orm(version)
            
            # Add user details
            if version.user_creator:
                version_read.username = version.user_creator.username
                version_read.first_name = version.user_creator.first_name
                version_read.last_name = version.user_creator.last_name
            
            version_reads.append(version_read)

        return version_reads, total_count, current_version

    def get_version(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        version_number: int
    ) -> Optional[ContentVersionRead]:
        """Get a specific version."""
        version = self.db.query(ContentVersion).options(
            joinedload(ContentVersion.user_creator)
        ).filter(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id,
            ContentVersion.version_number == version_number
        ).first()

        if not version:
            return None

        version_read = ContentVersionRead.from_orm(version)
        
        # Add user details
        if version.user_creator:
            version_read.username = version.user_creator.username
            version_read.first_name = version.user_creator.first_name
            version_read.last_name = version.user_creator.last_name
        
        return version_read

    def compare_versions(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        version_a: int,
        version_b: int
    ) -> ContentVersionCompareResponse:
        """Compare two versions of content."""
        # Get both versions
        version_a_data = self.get_version(content_type, content_id, version_a)
        version_b_data = self.get_version(content_type, content_id, version_b)

        if not version_a_data or not version_b_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or both versions not found"
            )

        # Calculate differences
        differences = self._calculate_differences(
            version_a_data.version_data,
            version_b_data.version_data,
            version_a,
            version_b
        )

        return ContentVersionCompareResponse(
            content_type=content_type,
            content_id=content_id,
            version_a=version_a_data,
            version_b=version_b_data,
            differences=differences
        )

    def _calculate_differences(self, data_a: Dict[str, Any], data_b: Dict[str, Any], version_a: int = None, version_b: int = None) -> Dict[str, Any]:
        """Calculate differences between two version data dictionaries."""
        differences = {
            "changed_fields": [],
            "field_changes": {},
            "summary": {
                "total_changes": 0,
                "added_fields": [],
                "removed_fields": [],
                "modified_fields": []
            }
        }

        all_keys = set(data_a.keys()) | set(data_b.keys())
        
        for key in all_keys:
            if key not in data_a:
                differences["summary"]["added_fields"].append(key)
                differences["field_changes"][key] = {
                    "change_type": "added",
                    "old_value": None,
                    "new_value": data_b[key]
                }
            elif key not in data_b:
                differences["summary"]["removed_fields"].append(key)
                differences["field_changes"][key] = {
                    "change_type": "removed",
                    "old_value": data_a[key],
                    "new_value": None
                }
            elif data_a[key] != data_b[key]:
                differences["summary"]["modified_fields"].append(key)
                differences["field_changes"][key] = {
                    "change_type": "modified",
                    "old_value": data_a[key],
                    "new_value": data_b[key]
                }
                
                # For text fields, provide detailed diff
                if isinstance(data_a[key], str) and isinstance(data_b[key], str):
                    diff = list(difflib.unified_diff(
                        data_a[key].splitlines(keepends=True),
                        data_b[key].splitlines(keepends=True),
                        fromfile=f"Version {version_a or 'A'}",
                        tofile=f"Version {version_b or 'B'}",
                        lineterm=""
                    ))
                    differences["field_changes"][key]["text_diff"] = diff

        differences["summary"]["total_changes"] = len(differences["field_changes"])
        differences["changed_fields"] = list(differences["field_changes"].keys())

        return differences

    def restore_version(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        version_number: int,
        user_id: int
    ) -> ContentRestoreResponse:
        """Restore content to a previous version."""
        # Get the version to restore
        version_to_restore = self.db.query(ContentVersion).filter(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id,
            ContentVersion.version_number == version_number
        ).first()

        if not version_to_restore:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Version not found"
            )

        # Create a new version before restoring (backup current state)
        current_version = self.create_version(content_type, content_id, user_id)

        # Restore the content
        restored_data = version_to_restore.version_data
        
        if content_type == ContentTypeEnum.summary:
            content = self.db.query(Summary).filter(Summary.id == content_id).first()
            if content:
                content.title = restored_data.get("title", content.title)
                content.full_markdown = restored_data.get("full_markdown", content.full_markdown)
                content.updated_at = datetime.now(timezone.utc)
        elif content_type == ContentTypeEnum.quiz:
            content = self.db.query(McqQuiz).filter(McqQuiz.id == content_id).first()
            if content:
                content.title = restored_data.get("title", content.title)
                content.description = restored_data.get("description", content.description)
                if restored_data.get("difficulty_level"):
                    # Handle enum conversion
                    from models.models import DifficultyLevelEnum
                    content.difficulty_level = DifficultyLevelEnum(restored_data["difficulty_level"])
                content.is_active = restored_data.get("is_active", content.is_active)
                content.is_public = restored_data.get("is_public", content.is_public)
                content.updated_at = datetime.now(timezone.utc)

        self.db.commit()

        return ContentRestoreResponse(
            message=f"Content restored to version {version_number}",
            content_type=content_type,
            content_id=content_id,
            restored_from_version=version_number,
            new_version_number=current_version.version_number
        )

    def delete_old_versions(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        keep_latest: int = 10
    ) -> int:
        """Delete old versions, keeping only the latest N versions."""
        versions = self.db.query(ContentVersion).filter(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id
        ).order_by(ContentVersion.version_number.desc()).offset(keep_latest).all()

        deleted_count = len(versions)
        for version in versions:
            self.db.delete(version)
        
        self.db.commit()
        return deleted_count 