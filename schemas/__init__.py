# Schemas package for Pydantic models
from .user import UserCreate, UserRead, UserUpdate, UserSession
from .auth import Token, TokenData, LoginRequest, LoginResponse, RegisterResponse
from .subject import SubjectCreate, SubjectRead, SubjectUpdate
from .file import UserFileAccessRead, UserFileAccessCreate
from .mcq import (
    QuestionTagCreate, QuestionTagRead, QuestionTagUpdate,
    McqQuestionCreate, McqQuestionRead, McqQuestionUpdate,
    McqQuizCreate, McqQuizRead, McqQuizUpdate, McqQuizWithQuestions,
    QuizSessionCreate, QuizSessionRead, QuizSessionSubmit,
    MCQGenerationRequest, MCQGenerationResponse
)
from .community import (
    CommunityCreate, CommunityRead, CommunityUpdate, CommunityJoinRequest,
    CommunityWithDetails, CommunityMemberRead, CommunityMemberUpdate,
    CommunitySubjectLinkCreate, CommunitySubjectLinkRead,
    CommunitySubjectFileCreate, CommunitySubjectFileRead, CommunitySubjectFileUpdate,
    CommunityStats
)

__all__ = [
    "UserCreate", "UserRead", "UserUpdate", "UserSession",
    "Token", "TokenData", "LoginRequest", "LoginResponse", "RegisterResponse",
    "SubjectCreate", "SubjectRead", "SubjectUpdate",
    "UserFileAccessRead", "UserFileAccessCreate",
    "QuestionTagCreate", "QuestionTagRead", "QuestionTagUpdate",
    "McqQuestionCreate", "McqQuestionRead", "McqQuestionUpdate",
    "McqQuizCreate", "McqQuizRead", "McqQuizUpdate", "McqQuizWithQuestions",
    "QuizSessionCreate", "QuizSessionRead", "QuizSessionSubmit",
    "MCQGenerationRequest", "MCQGenerationResponse",
    "CommunityCreate", "CommunityRead", "CommunityUpdate", "CommunityJoinRequest",
    "CommunityWithDetails", "CommunityMemberRead", "CommunityMemberUpdate",
    "CommunitySubjectLinkCreate", "CommunitySubjectLinkRead",
    "CommunitySubjectFileCreate", "CommunitySubjectFileRead", "CommunitySubjectFileUpdate",
    "CommunityStats"
]
