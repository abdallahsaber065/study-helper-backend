"""
Router for Community functionality.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from db_config import get_db
from core.security import get_current_user
from models.models import User, Subject, CommunityMember, CommunitySubjectLink
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


def _convert_member_to_read(member) -> CommunityMemberRead:
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


def _convert_file_to_read(community_file) -> CommunitySubjectFileRead:
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
    db: Session = Depends(get_db)
):
    """Create a new subject (global)."""
    # Check if subject already exists
    existing_subject = db.query(Subject).filter(Subject.name == subject.name).first()
    if existing_subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subject with this name already exists"
        )
    
    db_subject = Subject(**subject.dict())
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    
    return SubjectRead.from_orm(db_subject)


@router.get("/subjects", response_model=List[SubjectRead])
async def list_subjects(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List all subjects."""
    query = db.query(Subject)
    
    if search:
        query = query.filter(Subject.name.ilike(f"%{search}%"))
    
    subjects = query.offset(skip).limit(limit).all()
    return [SubjectRead.from_orm(subject) for subject in subjects]


@router.get("/subjects/{subject_id}", response_model=SubjectRead)
async def get_subject(
    subject_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific subject."""
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    
    return SubjectRead.from_orm(subject)


@router.post("", response_model=CommunityRead, status_code=status.HTTP_201_CREATED)
async def create_community(
    community: CommunityCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new community."""
    service = CommunityService(db)
    created_community = service.create_community(community, current_user)
    
    # Add counts
    result = CommunityRead.from_orm(created_community)
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
    db: Session = Depends(get_db)
):
    """List communities with filtering options."""
    service = CommunityService(db)
    communities = service.list_communities(
        user=current_user,
        skip=skip,
        limit=limit,
        my_communities=my_communities,
        search=search
    )
    
    # Add counts for each community
    result = []
    for community in communities:
        community_read = CommunityRead.from_orm(community)
        
        # Get member count
        member_count = db.query(CommunityMember).filter(
            CommunityMember.community_id == community.id
        ).count()
        community_read.member_count = member_count
        
        # Get subject count
        subject_count = db.query(CommunitySubjectLink).filter(
            CommunitySubjectLink.community_id == community.id
        ).count()
        community_read.subject_count = subject_count
        
        result.append(community_read)
    
    return result


@router.get("/{community_id}", response_model=CommunityWithDetails)
async def get_community(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get community details with members and subjects."""
    service = CommunityService(db)
    community = service.get_community(community_id, current_user)
    
    # Get members
    members = service.get_community_members(community_id, current_user)
    member_reads = [_convert_member_to_read(member) for member in members]
    
    # Get subjects
    subjects = service.get_community_subjects(community_id, current_user)
    subject_reads = [_convert_subject_link_to_read(subject) for subject in subjects]
    
    # Build response
    result = CommunityWithDetails.from_orm(community)
    result.member_count = len(member_reads)
    result.subject_count = len(subject_reads)
    result.members = member_reads
    result.subjects = subject_reads
    
    return result


@router.put("/{community_id}", response_model=CommunityRead)
async def update_community(
    community_id: int,
    community_update: CommunityUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update community details (admin only)."""
    service = CommunityService(db)
    updated_community = service.update_community(community_id, community_update, current_user)
    
    result = CommunityRead.from_orm(updated_community)
    # Add counts
    stats = service.get_community_stats(community_id, current_user)
    result.member_count = stats["total_members"]
    result.subject_count = stats["total_subjects"]
    
    return result


@router.delete("/{community_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_community(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete community (creator only)."""
    service = CommunityService(db)
    service.delete_community(community_id, current_user)


# ============ Community Membership ============

@router.post("/join", response_model=dict)
async def join_community(
    join_request: CommunityJoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Join a community using community code."""
    service = CommunityService(db)
    membership = service.join_community(join_request, current_user)
    
    return {
        "message": "Successfully joined community",
        "community_id": membership.community_id,
        "role": membership.role.value
    }


@router.post("/{community_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_community(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Leave a community."""
    service = CommunityService(db)
    service.leave_community(community_id, current_user)


@router.get("/{community_id}/members", response_model=List[CommunityMemberRead])
async def get_community_members(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get community members."""
    service = CommunityService(db)
    members = service.get_community_members(community_id, current_user)
    
    return [_convert_member_to_read(member) for member in members]


@router.put("/{community_id}/members/{user_id}", response_model=CommunityMemberRead)
async def update_member_role(
    community_id: int,
    user_id: int,
    role_update: CommunityMemberUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update member role (admin only)."""
    service = CommunityService(db)
    updated_member = service.update_member_role(community_id, user_id, role_update, current_user)
    
    return _convert_member_to_read(updated_member)


@router.delete("/{community_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    community_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove member from community (admin only)."""
    service = CommunityService(db)
    service.remove_member(community_id, user_id, current_user)


# ============ Subject Management ============

@router.post("/{community_id}/subjects", response_model=CommunitySubjectLinkRead, status_code=status.HTTP_201_CREATED)
async def add_subject_to_community(
    community_id: int,
    subject_link: CommunitySubjectLinkCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add subject to community (admin/moderator only)."""
    service = CommunityService(db)
    link = service.add_subject_to_community(community_id, subject_link, current_user)
    
    return _convert_subject_link_to_read(link)


@router.delete("/{community_id}/subjects/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_subject_from_community(
    community_id: int,
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove subject from community (admin/moderator only)."""
    service = CommunityService(db)
    service.remove_subject_from_community(community_id, subject_id, current_user)


@router.get("/{community_id}/subjects", response_model=List[CommunitySubjectLinkRead])
async def get_community_subjects(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get subjects linked to community."""
    service = CommunityService(db)
    subjects = service.get_community_subjects(community_id, current_user)
    
    return [_convert_subject_link_to_read(subject) for subject in subjects]


# ============ File Management ============

@router.post("/{community_id}/files", response_model=CommunitySubjectFileRead, status_code=status.HTTP_201_CREATED)
async def add_file_to_community_subject(
    community_id: int,
    file_data: CommunitySubjectFileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add file to community subject (admin/moderator only)."""
    service = CommunityService(db)
    community_file = service.add_file_to_community_subject(community_id, file_data, current_user)
    
    return _convert_file_to_read(community_file)


@router.get("/{community_id}/subjects/{subject_id}/files", response_model=List[CommunitySubjectFileRead])
async def get_community_subject_files(
    community_id: int,
    subject_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get files for a specific subject in community."""
    service = CommunityService(db)
    files = service.get_community_subject_files(community_id, subject_id, current_user)
    
    return [_convert_file_to_read(file) for file in files]


# ============ Community Statistics ============

@router.get("/{community_id}/stats", response_model=CommunityStats)
async def get_community_stats(
    community_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get community statistics."""
    service = CommunityService(db)
    stats = service.get_community_stats(community_id, current_user)
    
    return CommunityStats(**stats)


# ============ Community Content ============

@router.get("/{community_id}/summaries", response_model=List[dict])
async def get_community_summaries(
    community_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get summaries for a specific community."""
    service = CommunityService(db)
    service._check_community_member(current_user, community_id)
    
    from models.models import Summary
    
    summaries = db.query(Summary).filter(
        Summary.community_id == community_id
    ).offset(skip).limit(limit).all()
    
    return [
        {
            "id": summary.id,
            "title": summary.title,
            "user_id": summary.user_id,
            "created_at": summary.created_at,
            "updated_at": summary.updated_at,
            "community_id": summary.community_id
        }
        for summary in summaries
    ]


@router.get("/{community_id}/quizzes", response_model=List[dict])
async def get_community_quizzes(
    community_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get quizzes for a specific community."""
    service = CommunityService(db)
    service._check_community_member(current_user, community_id)
    
    from models.models import McqQuiz
    
    quizzes = db.query(McqQuiz).filter(
        McqQuiz.community_id == community_id
    ).offset(skip).limit(limit).all()
    
    return [
        {
            "id": quiz.id,
            "title": quiz.title,
            "description": quiz.description,
            "difficulty_level": quiz.difficulty_level,
            "user_id": quiz.user_id,
            "created_at": quiz.created_at,
            "is_public": quiz.is_public,
            "community_id": quiz.community_id
        }
        for quiz in quizzes
    ] 