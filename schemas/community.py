"""
Pydantic schemas for Community functionality.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from models.models import CommunityRoleEnum, CommunityFileCategoryEnum


# Community Schemas
class CommunityBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    is_private: bool = False


class CommunityCreate(CommunityBase):
    pass


class CommunityUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = None
    is_private: Optional[bool] = None


class CommunityRead(CommunityBase):
    id: int
    community_code: str
    creator_id: int
    created_at: datetime
    updated_at: datetime
    member_count: int = 0
    subject_count: int = 0

    class Config:
        from_attributes = True


class CommunityJoinRequest(BaseModel):
    community_code: str = Field(..., min_length=1, max_length=10)


# Community Member Schemas
class CommunityMemberBase(BaseModel):
    role: CommunityRoleEnum = CommunityRoleEnum.member


class CommunityMemberCreate(CommunityMemberBase):
    user_id: int


class CommunityMemberUpdate(BaseModel):
    role: Optional[CommunityRoleEnum] = None


class CommunityMemberRead(BaseModel):
    community_id: int
    user_id: int
    role: CommunityRoleEnum
    joined_at: datetime
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    class Config:
        from_attributes = True


# Community Subject Link Schemas
class CommunitySubjectLinkBase(BaseModel):
    subject_id: int


class CommunitySubjectLinkCreate(CommunitySubjectLinkBase):
    pass


class CommunitySubjectLinkRead(BaseModel):
    community_id: int
    subject_id: int
    added_by_user_id: int
    created_at: datetime
    subject_name: Optional[str] = None
    added_by_username: Optional[str] = None

    class Config:
        from_attributes = True


# Community Subject File Schemas
class CommunitySubjectFileBase(BaseModel):
    subject_id: int
    physical_file_id: int
    file_category: CommunityFileCategoryEnum
    description: Optional[str] = None


class CommunitySubjectFileCreate(CommunitySubjectFileBase):
    pass


class CommunitySubjectFileUpdate(BaseModel):
    file_category: Optional[CommunityFileCategoryEnum] = None
    description: Optional[str] = None


class CommunitySubjectFileRead(BaseModel):
    id: int
    community_id: int
    subject_id: int
    physical_file_id: int
    file_category: CommunityFileCategoryEnum
    uploaded_by_user_id: int
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    # Additional file info
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    subject_name: Optional[str] = None
    uploaded_by_username: Optional[str] = None

    class Config:
        from_attributes = True


# Community Details with Members and Subjects
class CommunityWithDetails(CommunityRead):
    members: List[CommunityMemberRead] = []
    subjects: List[CommunitySubjectLinkRead] = []


# Community Statistics
class CommunityStats(BaseModel):
    total_members: int
    total_subjects: int
    total_files: int
    total_quizzes: int
    total_summaries: int
    recent_activity_count: int 