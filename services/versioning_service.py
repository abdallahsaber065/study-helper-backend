"""
Content versioning service for tracking content changes.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, delete
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

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_content_data(self, content_type: ContentTypeEnum, content_id: int) -> Optional[Dict[str, Any]]:
        """Get current content data as a dictionary."""
        if content_type == ContentTypeEnum.summary:
            stmt = select(Summary).where(Summary.id == content_id)
            result = await self.db.execute(stmt)
            content = result.scalar_one_or_none()
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
            stmt = select(McqQuiz).where(McqQuiz.id == content_id)
            result = await self.db.execute(stmt)
            content = result.scalar_one_or_none()
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
            stmt = select(PhysicalFile).where(PhysicalFile.id == content_id)
            result = await self.db.execute(stmt)
            content = result.scalar_one_or_none()
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

    async def _verify_content_exists(self, content_type: ContentTypeEnum, content_id: int) -> bool:
        """Verify that content exists."""
        content_data = await self._get_content_data(content_type, content_id)
        return content_data is not None

    async def create_version(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        user_id: int
    ) -> ContentVersion:
        """Create a new version of content."""
        # Verify content exists
        if not await self._verify_content_exists(content_type, content_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{content_type.value.title()} not found"
            )

        # Get current content data
        content_data = await self._get_content_data(content_type, content_id)
        if not content_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to capture content data"
            )

        # Get next version number
        latest_version_stmt = select(ContentVersion).where(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id
        ).order_by(ContentVersion.version_number.desc())
        
        latest_version_result = await self.db.execute(latest_version_stmt)
        latest_version = latest_version_result.scalar_one_or_none()

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
        await self.db.commit()
        await self.db.refresh(version)
        
        return version

    async def get_content_versions(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        skip: int = 0,
        limit: int = 50
    ) -> tuple[List[ContentVersionRead], int, int]:
        """Get versions for content with pagination."""
        # Verify content exists
        if not await self._verify_content_exists(content_type, content_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{content_type.value.title()} not found"
            )

        base_stmt = select(ContentVersion).options(
            selectinload(ContentVersion.user_creator)
        ).where(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id
        )

        # Get total count
        from sqlalchemy import func
        count_stmt = select(func.count(ContentVersion.id)).where(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id
        )
        count_result = await self.db.execute(count_stmt)
        total_count = count_result.scalar()
        
        # Get current version number
        latest_version_stmt = base_stmt.order_by(ContentVersion.version_number.desc())
        latest_version_result = await self.db.execute(latest_version_stmt)
        latest_version = latest_version_result.scalars().first()
        current_version = latest_version.version_number if latest_version else 1

        # Get paginated results
        versions_stmt = base_stmt.order_by(
            ContentVersion.version_number.desc()
        ).offset(skip).limit(limit)
        
        versions_result = await self.db.execute(versions_stmt)
        versions = versions_result.scalars().all()

        # Convert to read schemas
        version_reads = []
        for version in versions:
            version_read = ContentVersionRead.model_validate(version)
            
            # Add user details
            if version.user_creator:
                version_read.username = version.user_creator.username
                version_read.first_name = version.user_creator.first_name
                version_read.last_name = version.user_creator.last_name
            
            version_reads.append(version_read)

        return version_reads, total_count, current_version

    async def get_version(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        version_number: int
    ) -> Optional[ContentVersionRead]:
        """Get a specific version."""
        stmt = select(ContentVersion).options(
            selectinload(ContentVersion.user_creator)
        ).where(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id,
            ContentVersion.version_number == version_number
        )
        
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()

        if not version:
            return None

        version_read = ContentVersionRead.model_validate(version)
        
        # Add user details
        if version.user_creator:
            version_read.username = version.user_creator.username
            version_read.first_name = version.user_creator.first_name
            version_read.last_name = version.user_creator.last_name
        
        return version_read

    async def compare_versions(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        version_a: int,
        version_b: int
    ) -> ContentVersionCompareResponse:
        """Compare two versions of content."""
        # Get both versions
        version_a_data = await self.get_version(content_type, content_id, version_a)
        version_b_data = await self.get_version(content_type, content_id, version_b)
        
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
        """Calculate differences between two versions."""
        differences = {
            "changed_fields": [],
            "field_changes": {},
            "summary": {
                "total_changes": 0,
                "fields_modified": 0,
                "content_similarity": 0.0
            }
        }
        
        # Compare each field
        all_fields = set(data_a.keys()) | set(data_b.keys())
        
        for field in all_fields:
            value_a = data_a.get(field)
            value_b = data_b.get(field)
            
            if value_a != value_b:
                differences["changed_fields"].append(field)
                differences["field_changes"][field] = {
                    "old_value": value_a,
                    "new_value": value_b,
                    "change_type": self._get_change_type(value_a, value_b)
                }
                
                # For text fields, calculate text diff
                if isinstance(value_a, str) and isinstance(value_b, str):
                    differences["field_changes"][field]["text_diff"] = self._calculate_text_diff(value_a, value_b)
        
        # Calculate summary statistics
        differences["summary"]["fields_modified"] = len(differences["changed_fields"])
        differences["summary"]["total_changes"] = len(differences["changed_fields"])
        
        # Calculate content similarity (simple approach)
        if data_a and data_b:
            total_fields = len(all_fields)
            unchanged_fields = total_fields - len(differences["changed_fields"])
            differences["summary"]["content_similarity"] = (unchanged_fields / total_fields) * 100 if total_fields > 0 else 100.0
        
        return differences
    
    def _get_change_type(self, old_value: Any, new_value: Any) -> str:
        """Determine the type of change between two values."""
        if old_value is None and new_value is not None:
            return "added"
        elif old_value is not None and new_value is None:
            return "removed"
        elif type(old_value) != type(new_value):
            return "type_changed"
        else:
            return "modified"
    
    def _calculate_text_diff(self, old_text: str, new_text: str) -> Dict[str, Any]:
        """Calculate detailed text differences."""
        diff = list(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile='old',
            tofile='new'
        ))
        
        return {
            "unified_diff": ''.join(diff),
            "changes_count": len([line for line in diff if line.startswith(('+', '-')) and not line.startswith(('+++', '---'))])
        }

    async def restore_version(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        version_number: int,
        user_id: int
    ) -> ContentRestoreResponse:
        """Restore content to a specific version."""
        # Get the version to restore
        version_data = await self.get_version(content_type, content_id, version_number)
        if not version_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_number} not found"
            )
        
        # Create a backup of current version before restoring
        await self.create_version(content_type, content_id, user_id)
        
        # Restore the content (this would need to be implemented for each content type)
        # For now, we'll return the version data to be applied by the caller
        
        return ContentRestoreResponse(
            content_type=content_type,
            content_id=content_id,
            restored_version=version_data,
            backup_created=True,
            message=f"Content restored to version {version_number}"
        )

    async def delete_old_versions(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        keep_latest: int = 10
    ) -> int:
        """Delete old versions, keeping only the latest N versions."""
        # Get all versions for this content, ordered by version number desc
        stmt = select(ContentVersion).where(
            ContentVersion.content_type == content_type,
            ContentVersion.content_id == content_id
        ).order_by(ContentVersion.version_number.desc()).offset(keep_latest)
        
        result = await self.db.execute(stmt)
        versions_to_delete = result.scalars().all()
        
        if not versions_to_delete:
            return 0
        
        # Delete the old versions
        version_ids = [v.id for v in versions_to_delete]
        delete_stmt = delete(ContentVersion).where(ContentVersion.id.in_(version_ids))
        await self.db.execute(delete_stmt)
        await self.db.commit()
        
        return len(versions_to_delete) 