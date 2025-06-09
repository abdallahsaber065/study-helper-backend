"""
Router for Community functionality.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func

from db_config import get_async_db
from core.security import get_current_user
from models.models import CommunitySubjectFile, User, Subject, CommunityMember, CommunitySubjectLink, Summary, McqQuiz
from schemas.community import (
    CommunityCreate, CommunityRead, CommunityUpdate, CommunityJoinRequest,
    CommunityWithDetails, CommunityMemberRead, CommunityMemberUpdate,
    CommunitySubjectLinkCreate, CommunitySubjectLinkRead,
    CommunitySubjectFileCreate, CommunitySubjectFileRead, CommunitySubjectFileUpdate,
    CommunityStats
)
from schemas.subject import SubjectCreate, SubjectRead
from services.community_service import CommunityService

router = APIRouter(prefix="/communities", tags=["Communities"])


def _convert_member_to_read(member: CommunityMember) -> CommunityMemberRead:
    """Convert CommunityMember with user data to read format."""
    return CommunityMemberRead(
        community_id=member.community_id,
        user_id=member.user_id,
        role=member.role,
        joined_at=member.joined_at,
        username=member.user.username if hasattr(member, 'user') and member.user else None,
        first_name=member.user.first_name if hasattr(member, 'user') and member.user else None,
        last_name=member.user.last_name if hasattr(member, 'user') and member.user else None
    )


def _convert_subject_link_to_read(link) -> CommunitySubjectLinkRead:
    """Convert CommunitySubjectLink with related data to read format."""
    return CommunitySubjectLinkRead(
        community_id=link.community_id,
        subject_id=link.subject_id,
        added_by_user_id=link.added_by_user_id,
        created_at=link.created_at,
        subject_name=link.subject.name if hasattr(link, 'subject') and link.subject else None,
        added_by_username=link.added_by_user.username if hasattr(link, 'added_by_user') and link.added_by_user else None
    )


def _convert_file_to_read(community_file: CommunitySubjectFile) -> CommunitySubjectFileRead:
    """Convert CommunitySubjectFile with related data to read format."""
    return CommunitySubjectFileRead(
        id=community_file.id,
        community_id=community_file.community_id,
        subject_id=community_file.subject_id,
        physical_file_id=community_file.physical_file_id,
        file_category=community_file.file_category,
        uploaded_by_user_id=community_file.uploaded_by_user_id,
        description=community_file.description,
        created_at=community_file.created_at,
        updated_at=community_file.updated_at,
        file_name=community_file.physical_file.file_name if hasattr(community_file, 'physical_file') and community_file.physical_file else None,
        file_type=community_file.physical_file.file_type if hasattr(community_file, 'physical_file') and community_file.physical_file else None,
        file_size_bytes=community_file.physical_file.file_size_bytes if hasattr(community_file, 'physical_file') and community_file.physical_file else None,
        subject_name=community_file.subject.name if hasattr(community_file, 'subject') and community_file.subject else None,
        uploaded_by_username=community_file.uploaded_by_user.username if hasattr(community_file, 'uploaded_by_user') and community_file.uploaded_by_user else None
    )


# ============ Community Management ============

# ============ Subject CRUD (Global) ============

@router.post("/subjects", response_model=SubjectRead, status_code=status.HTTP_201_CREATED)
async def create_subject(
    subject: SubjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new subject (global)."""
    # Check if subject already exists
    existing_stmt = select(Subject).where(Subject.name == subject.name)
    existing_result = await db.execute(existing_stmt)
    existing_subject = existing_result.scalar_one_or_none()
    
    if existing_subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subject with this name already exists"
        )
    
    db_subject = Subject(**subject.model_dump())
    db.add(db_subject)
    await db.commit()
    await db.refresh(db_subject)
    
    return SubjectRead.model_validate(db_subject)


@router.get("/subjects", response_model=List[SubjectRead])
async def list_subjects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db)
):
    """List all subjects."""
    stmt = select(Subject)
    
    if search:
        stmt = stmt.where(Subject.name.ilike(f"%{search}%"))
    
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    subjects = result.scalars().all()
    
    return [SubjectRead.model_validate(subject) for subject in subjects]


@router.get("/subjects/{subject_id}", response_model=SubjectRead)
async def get_subject(
    subject_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Get a specific subject."""
    stmt = select(Subject).where(Subject.id == subject_id)
    result = await db.execute(stmt)
    subject = result.scalar_one_or_none()
    
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    
    return SubjectRead.model_validate(subject)


@router.post("", response_model=CommunityRead, status_code=status.HTTP_201_CREATED)
async def create_community(
    community: CommunityCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Create a new community."""
    service = CommunityService(db)
    created_community = await service.create_community(community, current_user)
    
    # Add counts
    result = CommunityRead.model_validate(created_community)
    result.member_count = 1  # Creator is the first member
    result.subject_count = 0
    
    return result


@router.get("", response_model=List[CommunityRead])
async def list_communities(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    my_communities: bool = Query(False),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """List communities with filtering options."""
    service = CommunityService(db)
    communities = await service.list_communities(
        user=current_user,
        skip=skip,
        limit=limit,
        my_communities=my_communities,
        search=search
    )
    
    # Add counts for each community
    result = []
    for community in communities:
        community_read = CommunityRead.model_validate(community)
        
        # Get member count
        member_count_stmt = select(func.count(CommunityMember.community_id)).where(
            CommunityMember.community_id == community.id
        )
        member_count_result = await db.execute(member_count_stmt)
        member_count = member_count_result.scalar()
        community_read.member_count = member_count
        
        # Get subject count
        subject_count_stmt = select(func.count(CommunitySubjectLink.community_id)).where(
            CommunitySubjectLink.community_id == community.id
        )
        subject_count_result = await db.execute(subject_count_stmt)
        subject_count = subject_count_result.scalar()
        community_read.subject_count = subject_count
        
        result.append(community_read)
    
    return result


@router.get("/{community_id}", response_model=CommunityWithDetails)
async def get_community(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get community details with members and subjects."""
    service = CommunityService(db)
    community = await service.get_community(community_id, current_user)
    
    # Get members
    members = await service.get_community_members(community_id, current_user)
    member_reads = [_convert_member_to_read(member) for member in members]
    
    # Get subjects
    subjects = await service.get_community_subjects(community_id, current_user)
    subject_reads = [_convert_subject_link_to_read(subject) for subject in subjects]
    
    # Create detailed response
    community_details = CommunityWithDetails.model_validate(community)
    community_details.members = member_reads
    community_details.subjects = subject_reads
    community_details.member_count = len(member_reads)
    community_details.subject_count = len(subject_reads)
    
    return community_details


@router.put("/{community_id}", response_model=CommunityRead)
async def update_community(
    community_id: int,
    community_update: CommunityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update community details (admins only)."""
    service = CommunityService(db)
    updated_community = await service.update_community(community_id, community_update, current_user)
    
    # Add counts
    result = CommunityRead.model_validate(updated_community)
    
    # Get member count
    member_count_stmt = select(func.count(CommunityMember.community_id)).where(
        CommunityMember.community_id == community_id
    )
    member_count_result = await db.execute(member_count_stmt)
    result.member_count = member_count_result.scalar()
    
    # Get subject count
    subject_count_stmt = select(func.count(CommunitySubjectLink.community_id)).where(
        CommunitySubjectLink.community_id == community_id
    )
    subject_count_result = await db.execute(subject_count_stmt)
    result.subject_count = subject_count_result.scalar()
    
    return result


@router.delete("/{community_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_community(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a community (admins only)."""
    service = CommunityService(db)
    await service.delete_community(community_id, current_user)


# ============ Community Membership ============

@router.post("/join", response_model=dict)
async def join_community(
    join_request: CommunityJoinRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Join a community using community code."""
    service = CommunityService(db)
    result = await service.join_community(join_request.community_code, current_user)
    return result


@router.post("/{community_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_community(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Leave a community."""
    service = CommunityService(db)
    await service.leave_community(community_id, current_user)


@router.get("/{community_id}/members", response_model=List[CommunityMemberRead])
async def get_community_members(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get community members."""
    service = CommunityService(db)
    members = await service.get_community_members(community_id, current_user)
    return [_convert_member_to_read(member) for member in members]


@router.put("/{community_id}/members/{user_id}", response_model=CommunityMemberRead)
async def update_member_role(
    community_id: int,
    user_id: int,
    role_update: CommunityMemberUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update member role (admins only)."""
    service = CommunityService(db)
    updated_member = await service.update_member_role(community_id, user_id, role_update.role, current_user)
    return _convert_member_to_read(updated_member)


@router.delete("/{community_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    community_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Remove member from community (admins only)."""
    service = CommunityService(db)
    await service.remove_member(community_id, user_id, current_user)


# ============ Subject Management ============

@router.post("/{community_id}/subjects", response_model=CommunitySubjectLinkRead, status_code=status.HTTP_201_CREATED)
async def add_subject_to_community(
    community_id: int,
    subject_link: CommunitySubjectLinkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Add subject to community (admins/moderators only)."""
    service = CommunityService(db)
    created_link = await service.add_subject_to_community(community_id, subject_link.subject_id, current_user)
    return _convert_subject_link_to_read(created_link)


@router.delete("/{community_id}/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_subject_from_community(
    community_id: int,
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Remove subject from community (admins/moderators only)."""
    service = CommunityService(db)
    await service.remove_subject_from_community(community_id, subject_id, current_user)


@router.get("/{community_id}/subjects", response_model=List[CommunitySubjectLinkRead])
async def get_community_subjects(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get subjects linked to community."""
    service = CommunityService(db)
    subjects = await service.get_community_subjects(community_id, current_user)
    return [_convert_subject_link_to_read(subject) for subject in subjects]


# ============ File Management ============

@router.post("/{community_id}/files", response_model=CommunitySubjectFileRead, status_code=status.HTTP_201_CREATED)
async def add_file_to_community_subject(
    community_id: int,
    file_data: CommunitySubjectFileCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Add file to community subject (admins/moderators only)."""
    service = CommunityService(db)
    created_file = await service.add_file_to_community_subject(community_id, file_data, current_user)
    return _convert_file_to_read(created_file)


@router.get("/{community_id}/subjects/{subject_id}/files", response_model=List[CommunitySubjectFileRead])
async def get_community_subject_files(
    community_id: int,
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get files for a specific community subject."""
    service = CommunityService(db)
    files = await service.get_community_subject_files(community_id, subject_id, current_user)
    return [_convert_file_to_read(file) for file in files]


# ============ Community Statistics ============

@router.get("/{community_id}/stats", response_model=CommunityStats)
async def get_community_stats(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get community statistics."""
    service = CommunityService(db)
    stats = await service.get_community_stats(community_id, current_user)
    return stats


# ============ Community Content ============

@router.get("/{community_id}/summaries", response_model=List[dict])
async def get_community_summaries(
    community_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get summaries created for this community."""
    service = CommunityService(db)
    await service._check_member_access(current_user, community_id)
    
    # Get summaries for this community
    stmt = select(Summary).options(
        selectinload(Summary.user),
        selectinload(Summary.physical_file)
    ).where(
        Summary.community_id == community_id
    ).order_by(Summary.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    summaries = result.scalars().all()
    
    # Convert to dict format with user and file details
    result_data = []
    for summary in summaries:
        summary_dict = {
            "id": summary.id,
            "title": summary.title,
            "created_at": summary.created_at,
            "updated_at": summary.updated_at,
            "user_id": summary.user_id,
            "username": summary.user.username if summary.user else None,
            "file_id": summary.physical_file_id,
            "file_name": summary.physical_file.file_name if summary.physical_file else None
        }
        result_data.append(summary_dict)
    
    return result_data


@router.get("/{community_id}/quizzes", response_model=List[dict])
async def get_community_quizzes(
    community_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get quizzes created for this community."""
    service = CommunityService(db)
    await service._check_member_access(current_user, community_id)
    
    # Get quizzes for this community
    stmt = select(McqQuiz).options(
        selectinload(McqQuiz.creator),
        selectinload(McqQuiz.subject)
    ).where(
        McqQuiz.community_id == community_id
    ).order_by(McqQuiz.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    quizzes = result.scalars().all()
    
    # Convert to dict format with user and subject details
    result_data = []
    for quiz in quizzes:
        quiz_dict = {
            "id": quiz.id,
            "title": quiz.title,
            "description": quiz.description,
            "difficulty_level": quiz.difficulty_level,
            "is_public": quiz.is_public,
            "created_at": quiz.created_at,
            "updated_at": quiz.updated_at,
            "user_id": quiz.user_id,
            "username": quiz.creator.username if quiz.creator else None,
            "subject_id": quiz.subject_id,
            "subject_name": quiz.subject.name if quiz.subject else None
        }
        result_data.append(quiz_dict)
    
    return result_data 