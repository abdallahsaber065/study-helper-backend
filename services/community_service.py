"""
Community Service for managing communities, memberships, and content curation.
"""
import secrets
import string
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from fastapi import HTTPException, status
from models.models import (
    User, Community, CommunityMember, CommunitySubjectLink, 
    CommunitySubjectFile, Subject, PhysicalFile, UserFileAccess,
    CommunityRoleEnum, McqQuiz, Summary
)
from schemas.community import (
    CommunityCreate, CommunityUpdate, CommunityJoinRequest,
    CommunityMemberCreate, CommunityMemberUpdate,
    CommunitySubjectLinkCreate, CommunitySubjectFileCreate,
    CommunitySubjectFileUpdate
)
from core.config import settings


class CommunityService:
    """Service for managing community operations."""

    def __init__(self, db: Session):
        self.db = db

    def _generate_community_code(self) -> str:
        """Generate a unique community code."""
        while True:
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) 
                          for _ in range(settings.community_code_length))
            
            # Check if code already exists
            existing = self.db.query(Community).filter(Community.community_code == code).first()
            if not existing:
                return code

    def _check_admin_or_moderator(self, user: User, community_id: int) -> CommunityMember:
        """Check if user is admin or moderator of the community."""
        membership = self.db.query(CommunityMember).filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user.id
        ).first()
        
        if not membership or membership.role == CommunityRoleEnum.member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin or moderator access required"
            )
        
        return membership

    def _check_community_member(self, user: User, community_id: int) -> CommunityMember:
        """Check if user is a member of the community."""
        membership = self.db.query(CommunityMember).filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user.id
        ).first()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Community membership required"
            )
        
        return membership

    def create_community(self, community_data: CommunityCreate, creator: User) -> Community:
        """Create a new community."""
        # Check user's community creation limit
        user_communities_count = self.db.query(Community).filter(
            Community.creator_id == creator.id
        ).count()
        
        if user_communities_count >= settings.max_communities_per_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create more than {settings.max_communities_per_user} communities"
            )

        # Check if community name already exists
        existing_community = self.db.query(Community).filter(
            Community.name == community_data.name
        ).first()
        
        if existing_community:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Community with this name already exists"
            )

        # Create community
        community = Community(
            **community_data.dict(),
            creator_id=creator.id,
            community_code=self._generate_community_code()
        )
        
        self.db.add(community)
        self.db.commit()
        self.db.refresh(community)

        # Add creator as admin
        membership = CommunityMember(
            community_id=community.id,
            user_id=creator.id,
            role=CommunityRoleEnum.admin
        )
        self.db.add(membership)
        self.db.commit()

        return community

    def get_community(self, community_id: int, user: User) -> Community:
        """Get community details with access check."""
        community = self.db.query(Community).filter(Community.id == community_id).first()
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Community not found"
            )

        # Check if user has access to private community
        if community.is_private:
            membership = self.db.query(CommunityMember).filter(
                CommunityMember.community_id == community_id,
                CommunityMember.user_id == user.id
            ).first()
            
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to private community"
                )

        return community

    def list_communities(self, user: User, skip: int = 0, limit: int = 100, 
                        my_communities: bool = False, search: Optional[str] = None) -> List[Community]:
        """List communities with filtering."""
        query = self.db.query(Community)

        if my_communities:
            # Get communities where user is a member
            query = query.join(CommunityMember).filter(
                CommunityMember.user_id == user.id
            )
        else:
            # Show public communities and user's private communities
            user_community_ids = self.db.query(CommunityMember.community_id).filter(
                CommunityMember.user_id == user.id
            ).subquery()
            
            query = query.filter(
                (Community.is_private == False) | 
                (Community.id.in_(user_community_ids.select()))
            )

        if search:
            query = query.filter(Community.name.ilike(f"%{search}%"))

        return query.offset(skip).limit(limit).all()

    def update_community(self, community_id: int, update_data: CommunityUpdate, user: User) -> Community:
        """Update community (admin only)."""
        community = self.get_community(community_id, user)
        
        # Check if user is admin
        membership = self.db.query(CommunityMember).filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user.id
        ).first()
        
        if not membership or membership.role != CommunityRoleEnum.admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )

        # Update fields
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(community, field, value)

        community.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(community)
        
        return community

    def delete_community(self, community_id: int, user: User):
        """Delete community (creator only)."""
        community = self.get_community(community_id, user)
        
        if community.creator_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only community creator can delete the community"
            )

        self.db.delete(community)
        self.db.commit()

    def join_community(self, join_request: CommunityJoinRequest, user: User) -> CommunityMember:
        """Join a community using community code."""
        # Check user's membership limit
        user_memberships_count = self.db.query(CommunityMember).filter(
            CommunityMember.user_id == user.id
        ).count()
        
        if user_memberships_count >= settings.max_community_memberships_per_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot join more than {settings.max_community_memberships_per_user} communities"
            )

        # Find community by code
        community = self.db.query(Community).filter(
            Community.community_code == join_request.community_code
        ).first()
        
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid community code"
            )

        # Check if already a member
        existing_membership = self.db.query(CommunityMember).filter(
            CommunityMember.community_id == community.id,
            CommunityMember.user_id == user.id
        ).first()
        
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
        self.db.commit()
        self.db.refresh(membership)
        
        return membership

    def leave_community(self, community_id: int, user: User):
        """Leave a community."""
        community = self.get_community(community_id, user)
        
        # Creator cannot leave their own community
        if community.creator_id == user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Community creator cannot leave. Transfer ownership or delete the community."
            )

        membership = self.db.query(CommunityMember).filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == user.id
        ).first()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Not a member of this community"
            )

        self.db.delete(membership)
        self.db.commit()

    def get_community_members(self, community_id: int, user: User) -> List[CommunityMember]:
        """Get community members."""
        # Check access
        self._check_community_member(user, community_id)
        
        members = self.db.query(CommunityMember).options(
            joinedload(CommunityMember.user)
        ).filter(CommunityMember.community_id == community_id).all()
        
        return members

    def update_member_role(self, community_id: int, target_user_id: int, 
                          role_update: CommunityMemberUpdate, user: User) -> CommunityMember:
        """Update member role (admin only)."""
        # Check if current user is admin
        self._check_admin_or_moderator(user, community_id)
        
        # Cannot change creator's role
        community = self.get_community(community_id, user)
        if target_user_id == community.creator_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change community creator's role"
            )

        membership = self.db.query(CommunityMember).filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == target_user_id
        ).first()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found"
            )

        membership.role = role_update.role
        self.db.commit()
        self.db.refresh(membership)
        
        return membership

    def remove_member(self, community_id: int, target_user_id: int, user: User):
        """Remove member from community (admin only)."""
        # Check if current user is admin
        self._check_admin_or_moderator(user, community_id)
        
        # Cannot remove creator
        community = self.get_community(community_id, user)
        if target_user_id == community.creator_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove community creator"
            )

        membership = self.db.query(CommunityMember).filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id == target_user_id
        ).first()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found"
            )

        self.db.delete(membership)
        self.db.commit()

    def add_subject_to_community(self, community_id: int, subject_link: CommunitySubjectLinkCreate, 
                                user: User) -> CommunitySubjectLink:
        """Add subject to community (admin/moderator only)."""
        # Check permissions
        self._check_admin_or_moderator(user, community_id)
        
        # Check if subject exists
        subject = self.db.query(Subject).filter(Subject.id == subject_link.subject_id).first()
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not found"
            )

        # Check if already linked
        existing_link = self.db.query(CommunitySubjectLink).filter(
            CommunitySubjectLink.community_id == community_id,
            CommunitySubjectLink.subject_id == subject_link.subject_id
        ).first()
        
        if existing_link:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subject already linked to this community"
            )

        # Create link
        link = CommunitySubjectLink(
            community_id=community_id,
            subject_id=subject_link.subject_id,
            added_by_user_id=user.id
        )
        
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        
        return link

    def remove_subject_from_community(self, community_id: int, subject_id: int, user: User):
        """Remove subject from community (admin/moderator only)."""
        # Check permissions
        self._check_admin_or_moderator(user, community_id)
        
        link = self.db.query(CommunitySubjectLink).filter(
            CommunitySubjectLink.community_id == community_id,
            CommunitySubjectLink.subject_id == subject_id
        ).first()
        
        if not link:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject not linked to this community"
            )

        self.db.delete(link)
        self.db.commit()

    def get_community_subjects(self, community_id: int, user: User) -> List[CommunitySubjectLink]:
        """Get subjects linked to community."""
        # Check access
        self._check_community_member(user, community_id)
        
        subjects = self.db.query(CommunitySubjectLink).options(
            joinedload(CommunitySubjectLink.subject),
            joinedload(CommunitySubjectLink.added_by_user)
        ).filter(CommunitySubjectLink.community_id == community_id).all()
        
        return subjects

    def add_file_to_community_subject(self, community_id: int, file_data: CommunitySubjectFileCreate, 
                                     user: User) -> CommunitySubjectFile:
        """Add file to community subject (admin/moderator only)."""
        # Check permissions
        self._check_admin_or_moderator(user, community_id)
        
        # Check if subject is linked to community
        subject_link = self.db.query(CommunitySubjectLink).filter(
            CommunitySubjectLink.community_id == community_id,
            CommunitySubjectLink.subject_id == file_data.subject_id
        ).first()
        
        if not subject_link:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subject not linked to this community"
            )

        # Check if file exists and user has access
        file_access = self.db.query(UserFileAccess).filter(
            UserFileAccess.user_id == user.id,
            UserFileAccess.physical_file_id == file_data.physical_file_id
        ).first()
        
        if not file_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to this file"
            )

        # Check if file already linked
        existing_file = self.db.query(CommunitySubjectFile).filter(
            CommunitySubjectFile.community_id == community_id,
            CommunitySubjectFile.subject_id == file_data.subject_id,
            CommunitySubjectFile.physical_file_id == file_data.physical_file_id
        ).first()
        
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
        self.db.commit()
        self.db.refresh(community_file)
        
        return community_file

    def get_community_subject_files(self, community_id: int, subject_id: int, user: User) -> List[CommunitySubjectFile]:
        """Get files for a specific subject in community."""
        # Check access
        self._check_community_member(user, community_id)
        
        files = self.db.query(CommunitySubjectFile).options(
            joinedload(CommunitySubjectFile.physical_file),
            joinedload(CommunitySubjectFile.subject),
            joinedload(CommunitySubjectFile.uploaded_by_user)
        ).filter(
            CommunitySubjectFile.community_id == community_id,
            CommunitySubjectFile.subject_id == subject_id
        ).all()
        
        return files

    def get_community_stats(self, community_id: int, user: User) -> dict:
        """Get community statistics."""
        # Check access
        self._check_community_member(user, community_id)
        
        # Count members
        member_count = self.db.query(CommunityMember).filter(
            CommunityMember.community_id == community_id
        ).count()
        
        # Count subjects
        subject_count = self.db.query(CommunitySubjectLink).filter(
            CommunitySubjectLink.community_id == community_id
        ).count()
        
        # Count files
        file_count = self.db.query(CommunitySubjectFile).filter(
            CommunitySubjectFile.community_id == community_id
        ).count()
        
        # Count quizzes
        quiz_count = self.db.query(McqQuiz).filter(
            McqQuiz.community_id == community_id
        ).count()
        
        # Count summaries
        summary_count = self.db.query(Summary).filter(
            Summary.community_id == community_id
        ).count()
        
        return {
            "total_members": member_count,
            "total_subjects": subject_count,
            "total_files": file_count,
            "total_quizzes": quiz_count,
            "total_summaries": summary_count,
            "recent_activity_count": 0  # Placeholder for future implementation
        } 