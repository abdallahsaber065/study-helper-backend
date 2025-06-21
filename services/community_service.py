"""
Community Service for managing communities, memberships, and content curation.
"""
import secrets
import string
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func, delete
from fastapi import HTTPException, status
from models.models import (
    User, Community, CommunityMember, CommunitySubjectLink, 
    CommunitySubjectFile, Subject, PhysicalFile, UserFileAccess,
    CommunityRoleEnum, McqQuiz, Summary
)
from schemas.community import (
    CommunityCreate, CommunityUpdate, CommunityJoinRequest,
    CommunityMemberUpdate, CommunitySubjectLinkCreate, 
    CommunitySubjectFileCreate
)
from core.config import settings


class CommunityService:
    """Service for managing community operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _generate_community_code(self) -> str:
        """Generate a unique community code."""
        while True:
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) 
                          for _ in range(settings.community_code_length))
            
            # Check if code already exists
            stmt = select(Community).where(Community.community_code == code)
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()
            if not existing:
                return code

    async def _check_admin_or_moderator(self, user: User, community_id: int) -> CommunityMember:
        """Check if user is admin or moderator of the community."""
        stmt = select(CommunityMember).where(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user.id
        )
        result = await self.db.execute(stmt)
        membership = result.scalar_one_or_none()
        
        if not membership or membership.role == CommunityRoleEnum.member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or moderator access required"
            )
        
        return membership

    async def _check_community_member(self, user: User, community_id: int) -> CommunityMember:
        """Check if user is a member of the community."""
        stmt = select(CommunityMember).where(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user.id
        )
        result = await self.db.execute(stmt)
        membership = result.scalar_one_or_none()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Community membership required"
            )
        
        return membership

    async def _check_member_access(self, user: User, community_id: int) -> CommunityMember:
        """Check if user has access to the community (alias for _check_community_member)."""
        return await self._check_community_member(user, community_id)

    async def has_summary_access(self, summary_id: int, user_id: int) -> bool:
        """Check if user has access to a summary through community membership."""
        # Get the summary with community info
        stmt = select(Summary).where(Summary.id == summary_id)
        result = await self.db.execute(stmt)
        summary = result.scalar_one_or_none()
        
        if not summary:
            return False
            
        # If summary belongs to user, they have access
        if summary.user_id == user_id:
            return True
            
        # If summary is associated with a community, check membership
        if summary.community_id:
            membership_stmt = select(CommunityMember).where(
                CommunityMember.community_id == summary.community_id,
                CommunityMember.user_id == user_id
            )
            membership_result = await self.db.execute(membership_stmt)
            membership = membership_result.scalar_one_or_none()
            return membership is not None
            
        return False

    async def create_community(self, community_data: CommunityCreate, creator: User) -> Community:
        """Create a new community."""
        # Check user's community creation limit
        count_stmt = select(func.count(Community.id)).where(Community.creator_id == creator.id)
        count_result = await self.db.execute(count_stmt)
        user_communities_count = count_result.scalar()
        
        if user_communities_count >= settings.max_communities_per_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create more than {settings.max_communities_per_user} communities"
            )

        # Check if community name already exists
        existing_stmt = select(Community).where(Community.name == community_data.name)
        existing_result = await self.db.execute(existing_stmt)
        existing_community = existing_result.scalar_one_or_none()
        
        if existing_community:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Community with this name already exists"
            )

        # Create community
        community = Community(
            **community_data.model_dump(),
            creator_id=creator.id,
            community_code=await self._generate_community_code()
        )
        
        self.db.add(community)
        await self.db.commit()
        await self.db.refresh(community)

        # Add creator as admin
        membership = CommunityMember(
            community_id=community.id,
            user_id=creator.id,
            role=CommunityRoleEnum.admin
        )
        self.db.add(membership)
        await self.db.commit()

        return community

    async def get_community(self, community_id: int, user: User) -> Community:
        """Get community details with access check."""
        stmt = select(Community).where(Community.id == community_id)
        result = await self.db.execute(stmt)
        community = result.scalar_one_or_none()
        
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Community not found"
            )

        # Check if user has access to private community
        if community.is_private:
            membership_stmt = select(CommunityMember).where(
                CommunityMember.community_id == community_id,
                CommunityMember.user_id == user.id
            )
            membership_result = await self.db.execute(membership_stmt)
            membership = membership_result.scalar_one_or_none()
            
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to private community"
                )

        return community

    async def list_communities(
        self, 
        user: User, 
        skip: int = 0, 
        limit: int = 100, 
        my_communities: bool = False, 
        search: Optional[str] = None
    ) -> List[Community]:
        """List communities with filtering."""
        
        if my_communities:
            # Get communities where user is a member
            stmt = select(Community).join(CommunityMember).where(
                CommunityMember.user_id == user.id
            )
        else:
            # Show public communities and user's private communities
            user_community_ids_stmt = select(CommunityMember.community_id).where(
                CommunityMember.user_id == user.id
            )
            user_community_ids_result = await self.db.execute(user_community_ids_stmt)
            user_community_ids = [row[0] for row in user_community_ids_result.fetchall()]
            
            stmt = select(Community).where(
                (Community.is_private == False) | 
                (Community.id.in_(user_community_ids) if user_community_ids else False)
            )

        if search:
            stmt = stmt.where(Community.name.ilike(f"%{search}%"))

        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_community(self, community_id: int, update_data: CommunityUpdate, user: User) -> Community:
        """Update community (admin only)."""
        community = await self.get_community(community_id, user)
        
        # Check if user is admin
        membership_stmt = select(CommunityMember).where(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user.id
        )
        membership_result = await self.db.execute(membership_stmt)
        membership = membership_result.scalar_one_or_none()
        
        if not membership or membership.role != CommunityRoleEnum.admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )

        # Update fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(community, field, value)

        community.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(community)
        
        return community

    async def delete_community(self, community_id: int, user: User) -> None:
        """Delete community (creator only)."""
        community = await self.get_community(community_id, user)
        
        if community.creator_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only community creator can delete the community"
            )

        await self.db.delete(community)
        await self.db.commit()

    async def join_community(self, community_code: str, user: User) -> Dict[str, Any]:
        """Join a community using community code."""
        # Check user's membership limit
        count_stmt = select(func.count(CommunityMember.id)).where(CommunityMember.user_id == user.id)
        count_result = await self.db.execute(count_stmt)
        user_memberships_count = count_result.scalar()
        
        if user_memberships_count >= settings.max_community_memberships_per_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot join more than {settings.max_community_memberships_per_user} communities"
            )

        # Find community by code
        stmt = select(Community).where(Community.community_code == community_code)
        result = await self.db.execute(stmt)
        community = result.scalar_one_or_none()
        
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid community code"
            )

        # Check if already a member
        membership_stmt = select(CommunityMember).where(
            CommunityMember.community_id == community.id,
            CommunityMember.user_id == user.id
        )
        membership_result = await self.db.execute(membership_stmt)
        existing_membership = membership_result.scalar_one_or_none()
        
        if existing_membership:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already a member of this community"
            )

        # For private communities, joining requires admin approval (simplified for now)
        if community.is_private:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Private community requires admin approval (not implemented yet)"
            )

        # Create membership
        membership = CommunityMember(
            community_id=community.id,
            user_id=user.id,
            role=CommunityRoleEnum.member
        )
        
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(membership)
        
        return {
            "message": f"Successfully joined {community.name}",
            "community_id": community.id,
            "community_name": community.name
        }

    async def leave_community(self, community_id: int, user: User) -> None:
        """Leave a community."""
        community = await self.get_community(community_id, user)
        
        # Creator cannot leave their own community
        if community.creator_id == user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Community creator cannot leave. Transfer ownership or delete the community."
            )

        membership_stmt = select(CommunityMember).where(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user.id
        )
        membership_result = await self.db.execute(membership_stmt)
        membership = membership_result.scalar_one_or_none()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Not a member of this community"
            )

        await self.db.delete(membership)
        await self.db.commit()

    async def get_community_members(self, community_id: int, user: User) -> List[CommunityMember]:
        """Get community members."""
        # Check access
        await self._check_community_member(user, community_id)
        
        stmt = select(CommunityMember).options(
            selectinload(CommunityMember.user)
        ).where(CommunityMember.community_id == community_id)
        result = await self.db.execute(stmt)
        members = result.scalars().all()
        
        return members

    async def update_member_role(
        self, 
        community_id: int, 
        target_user_id: int, 
        new_role: CommunityRoleEnum, 
        user: User
    ) -> CommunityMember:
        """Update member role (admin only)."""
        # Check if current user is admin
        await self._check_admin_or_moderator(user, community_id)
        
        # Cannot change creator's role
        community = await self.get_community(community_id, user)
        if target_user_id == community.creator_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change community creator's role"
            )

        membership_stmt = select(CommunityMember).where(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == target_user_id
        )
        membership_result = await self.db.execute(membership_stmt)
        membership = membership_result.scalar_one_or_none()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found"
            )

        membership.role = new_role
        await self.db.commit()
        await self.db.refresh(membership)
        
        return membership

    async def remove_member(self, community_id: int, target_user_id: int, user: User) -> None:
        """Remove member from community (admin only)."""
        # Check if current user is admin
        await self._check_admin_or_moderator(user, community_id)
        
        # Cannot remove creator
        community = await self.get_community(community_id, user)
        if target_user_id == community.creator_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove community creator"
            )

        membership_stmt = select(CommunityMember).where(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == target_user_id
        )
        membership_result = await self.db.execute(membership_stmt)
        membership = membership_result.scalar_one_or_none()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found"
            )

        await self.db.delete(membership)
        await self.db.commit()

    async def add_subject_to_community(
        self, 
        community_id: int, 
        subject_id: int, 
        user: User
    ) -> CommunitySubjectLink:
        """Add subject to community (admin/moderator only)."""
        # Check permissions
        await self._check_admin_or_moderator(user, community_id)
        
        # Check if subject exists
        stmt = select(Subject).where(Subject.id == subject_id)
        result = await self.db.execute(stmt)
        subject = result.scalar_one_or_none()
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found"
            )

        # Check if already linked
        existing_stmt = select(CommunitySubjectLink).where(
            CommunitySubjectLink.community_id == community_id,
            CommunitySubjectLink.subject_id == subject_id
        )
        existing_result = await self.db.execute(existing_stmt)
        existing_link = existing_result.scalar_one_or_none()
        
        if existing_link:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subject already linked to this community"
            )

        # Create link
        link = CommunitySubjectLink(
            community_id=community_id,
            subject_id=subject_id,
            added_by_user_id=user.id
        )
        
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)
        
        return link

    async def remove_subject_from_community(self, community_id: int, subject_id: int, user: User) -> None:
        """Remove subject from community (admin/moderator only)."""
        # Check permissions
        await self._check_admin_or_moderator(user, community_id)
        
        stmt = select(CommunitySubjectLink).where(
            CommunitySubjectLink.community_id == community_id,
            CommunitySubjectLink.subject_id == subject_id
        )
        result = await self.db.execute(stmt)
        link = result.scalar_one_or_none()
        
        if not link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not linked to this community"
            )

        await self.db.delete(link)
        await self.db.commit()

    async def get_community_subjects(self, community_id: int, user: User) -> List[CommunitySubjectLink]:
        """Get subjects linked to community."""
        # Check access
        await self._check_community_member(user, community_id)
        
        stmt = select(CommunitySubjectLink).options(
            selectinload(CommunitySubjectLink.subject),
            selectinload(CommunitySubjectLink.added_by_user)
        ).where(CommunitySubjectLink.community_id == community_id)
        result = await self.db.execute(stmt)
        subjects = result.scalars().all()
        
        return subjects

    async def add_file_to_community_subject(
        self, 
        community_id: int, 
        file_data: CommunitySubjectFileCreate, 
        user: User
    ) -> CommunitySubjectFile:
        """Add file to community subject (admin/moderator only)."""
        # Check permissions
        await self._check_admin_or_moderator(user, community_id)
        
        # Check if subject is linked to community
        stmt = select(CommunitySubjectLink).where(
            CommunitySubjectLink.community_id == community_id,
            CommunitySubjectLink.subject_id == file_data.subject_id
        )
        result = await self.db.execute(stmt)
        subject_link = result.scalar_one_or_none()
        
        if not subject_link:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subject not linked to this community"
            )

        # Check if file exists and user has access
        stmt = select(UserFileAccess).where(
            UserFileAccess.user_id == user.id,
            UserFileAccess.physical_file_id == file_data.physical_file_id
        )
        result = await self.db.execute(stmt)
        file_access = result.scalar_one_or_none()
        
        if not file_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to this file"
            )

        # Check if file already linked
        existing_stmt = select(CommunitySubjectFile).where(
            CommunitySubjectFile.community_id == community_id,
            CommunitySubjectFile.subject_id == file_data.subject_id,
            CommunitySubjectFile.physical_file_id == file_data.physical_file_id
        )
        existing_result = await self.db.execute(existing_stmt)
        existing_file = existing_result.scalar_one_or_none()
        
        if existing_file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File already linked to this community subject"
            )

        # Create file link
        community_file = CommunitySubjectFile(
            community_id=community_id,
            subject_id=file_data.subject_id,
            physical_file_id=file_data.physical_file_id,
            file_category=file_data.file_category,
            description=file_data.description,
            uploaded_by_user_id=user.id
        )
        
        self.db.add(community_file)
        await self.db.commit()
        await self.db.refresh(community_file)
        
        return community_file

    async def get_community_subject_files(
        self, 
        community_id: int, 
        subject_id: int, 
        user: User
    ) -> List[CommunitySubjectFile]:
        """Get files for a specific subject in community."""
        # Check access
        await self._check_community_member(user, community_id)
        
        stmt = select(CommunitySubjectFile).options(
            selectinload(CommunitySubjectFile.physical_file),
            selectinload(CommunitySubjectFile.subject),
            selectinload(CommunitySubjectFile.uploaded_by_user)
        ).where(
            CommunitySubjectFile.community_id == community_id,
            CommunitySubjectFile.subject_id == subject_id
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()
        
        return files

    async def get_community_stats(self, community_id: int, user: User) -> Dict[str, Any]:
        """Get community statistics."""
        # Check access
        await self._check_community_member(user, community_id)
        
        # Count members (CommunityMember uses composite primary key, so count using community_id)
        stmt = select(func.count(CommunityMember.community_id)).where(CommunityMember.community_id == community_id)
        result = await self.db.execute(stmt)
        member_count = result.scalar()
        
        # Count subjects (CommunitySubjectLink uses composite primary key, so count using community_id)
        stmt = select(func.count(CommunitySubjectLink.community_id)).where(CommunitySubjectLink.community_id == community_id)
        result = await self.db.execute(stmt)
        subject_count = result.scalar()
        
        # Count files
        stmt = select(func.count(CommunitySubjectFile.id)).where(CommunitySubjectFile.community_id == community_id)
        result = await self.db.execute(stmt)
        file_count = result.scalar()
        
        # Count quizzes
        stmt = select(func.count(McqQuiz.id)).where(McqQuiz.community_id == community_id)
        result = await self.db.execute(stmt)
        quiz_count = result.scalar()
        
        # Count summaries
        stmt = select(func.count(Summary.id)).where(Summary.community_id == community_id)
        result = await self.db.execute(stmt)
        summary_count = result.scalar()
        
        return {
            "total_members": member_count,
            "total_subjects": subject_count,
            "total_files": file_count,
            "total_quizzes": quiz_count,
            "total_summaries": summary_count,
            "recent_activity_count": 0  # Placeholder for future implementation
        } 