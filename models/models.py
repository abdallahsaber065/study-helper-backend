""" 
Database models for the application.
"""
import enum
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Enum as SAEnum,
    UniqueConstraint, PrimaryKeyConstraint, Index, CheckConstraint, Table
)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from db_config import Base

# --- ENUM Types (mirroring PostgreSQL ENUMs) ---
class UserRoleEnum(enum.Enum):
    user = "user"
    admin = "admin"
    moderator = "moderator"

class DifficultyLevelEnum(enum.Enum):
    Easy = "Easy"
    Medium = "Medium"
    Hard = "Hard"

class AiProviderEnum(enum.Enum):
    OpenAI = "OpenAI"
    Google = "Google"
    Other = "Other"

class ContentTypeEnum(enum.Enum):
    file = "file"
    summary = "summary"
    quiz = "quiz"

class CommunityRoleEnum(enum.Enum):
    admin = "admin"
    member = "member"
    moderator = "moderator"

class CommunityFileCategoryEnum(enum.Enum):
    lecture = "lecture"
    section = "section"
    exam = "exam"
    summary_material = "summary_material"
    general_resource = "general_resource"
    other = "other"

class NotificationTypeEnum(enum.Enum):
    new_content = "new_content"
    comment_reply = "comment_reply"
    quiz_result = "quiz_result"
    community_invite = "community_invite"
    mention = "mention"

class RatingValueEnum(enum.Enum):
    one = "1"
    two = "2"
    three = "3"
    four = "4"
    five = "5"

# --- Model Definitions ---

# User and Authentication Models
class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates
    last_login = Column(DateTime(timezone=True), server_default=func.now())

    profile_picture_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default='true')
    is_verified = Column(Boolean, nullable=False, server_default='false')
    role = Column(SAEnum(UserRoleEnum, name="user_role_enum", create_type=False), nullable=False, server_default=UserRoleEnum.user.value)    # Relationships
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("AiApiKey", back_populates="user", cascade="all, delete-orphan")
    created_questions = relationship("McqQuestion", back_populates="creator")
    created_quizzes = relationship("McqQuiz", back_populates="creator")
    quiz_sessions = relationship("QuizSession", back_populates="user", cascade="all, delete-orphan")
    summaries = relationship("Summary", back_populates="user", cascade="all, delete-orphan")
    uploaded_files = relationship("PhysicalFile", back_populates="uploader")
    file_access_entries = relationship("UserFileAccess", foreign_keys="[UserFileAccess.user_id]", back_populates="user", cascade="all, delete-orphan")
    granted_file_accesses = relationship("UserFileAccess", foreign_keys="[UserFileAccess.granted_by_user_id]", back_populates="granted_by")
    comments_authored = relationship("ContentComment", back_populates="author", cascade="all, delete-orphan")
    versions_created = relationship("ContentVersion", back_populates="user_creator", cascade="all, delete-orphan")
    # Relationships to new tables
    notifications = relationship("Notification", foreign_keys="[Notification.user_id]", back_populates="recipient_user", cascade="all, delete-orphan")
    triggered_notifications = relationship("Notification", foreign_keys="[Notification.actor_id]", back_populates="actor_user")
    ratings_given = relationship("ContentRating", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    created_communities = relationship("Community", back_populates="creator", cascade="all, delete-orphan")
    community_memberships = relationship("CommunityMember", back_populates="user", cascade="all, delete-orphan")
    community_subjects_added = relationship("CommunitySubjectLink", back_populates="added_by_user", cascade="all, delete-orphan")
    community_files_uploaded = relationship("CommunitySubjectFile", back_populates="uploaded_by_user", cascade="all, delete-orphan")
    free_api_usage = relationship("UserFreeApiUsage", back_populates="user", cascade="all, delete-orphan")

class UserSession(Base):
    __tablename__ = "user_session"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    session_token = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="sessions")

class AiApiKey(Base):
    __tablename__ = "ai_api_key"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    encrypted_api_key = Column(Text, nullable=False, unique=True)
    provider_name = Column(SAEnum(AiProviderEnum, name="ai_provider_enum", create_type=False), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default='true')

    user = relationship("User", back_populates="api_keys")

# Content Core Models
class Subject(Base):
    __tablename__ = "subject"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates

    quizzes = relationship("McqQuiz", back_populates="subject")
    community_links = relationship("CommunitySubjectLink", back_populates="subject", cascade="all, delete-orphan")
    community_files = relationship("CommunitySubjectFile", back_populates="subject", cascade="all, delete-orphan")

class PhysicalFile(Base):
    __tablename__ = "physical_file"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    file_hash = Column(String(100), nullable=False, unique=True, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(255), nullable=False, unique=True)
    file_type = Column(String(50), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False) # Original uploader/owner

    uploader = relationship("User", back_populates="uploaded_files")
    access_entries = relationship("UserFileAccess", back_populates="physical_file", cascade="all, delete-orphan")
    summaries_generated = relationship("Summary", back_populates="physical_file", cascade="all, delete-orphan")
    cache_entries = relationship("GeminiFileCache", back_populates="physical_file", cascade="all, delete-orphan")
    community_subject_files = relationship("CommunitySubjectFile", back_populates="physical_file", cascade="all, delete-orphan")


# Caching Model
class GeminiFileCache(Base):
    __tablename__ = "gemini_file_cache"
    __table_args__ = (
        UniqueConstraint("physical_file_id", "api_key_id", "gemini_file_uri", name="uq_gemini_file_cache"),
    )
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    physical_file_id = Column(Integer, ForeignKey("physical_file.id"), nullable=False)
    api_key_id = Column(Integer, ForeignKey("ai_api_key.id"), nullable=False)
    gemini_file_uri = Column(String(255), nullable=False, unique=True)
    gemini_display_name = Column(String(255), nullable=False)
    gemini_file_unique_name = Column(String(255), nullable=False, unique=True)
    expiration_time = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )  # DB trigger handles updates

    physical_file = relationship("PhysicalFile", back_populates="cache_entries")


class UserFileAccess(Base):
    __tablename__ = "user_file_access"
    __table_args__ = (PrimaryKeyConstraint("user_id", "physical_file_id"),)

    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    physical_file_id = Column(Integer, ForeignKey("physical_file.id"), primary_key=True)
    access_level = Column(String(20), nullable=False, server_default='read')  # read, write, admin
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    granted_by_user_id = Column(Integer, ForeignKey("user.id"), nullable=True)    
    user = relationship("User", foreign_keys=[user_id], back_populates="file_access_entries")
    physical_file = relationship("PhysicalFile", back_populates="access_entries")
    granted_by = relationship("User", foreign_keys=[granted_by_user_id], back_populates="granted_file_accesses")

# Summary Model
class Summary(Base):
    __tablename__ = "summary"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    physical_file_id = Column(Integer, ForeignKey("physical_file.id"), nullable=True)
    title = Column(String(255), nullable=False)
    full_markdown = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates
    community_id = Column(Integer, ForeignKey("community.id"), nullable=True)

    user = relationship("User", back_populates="summaries")
    physical_file = relationship("PhysicalFile", back_populates="summaries_generated")
    community = relationship("Community", back_populates="summaries")

# Quiz Core Models
class McqQuestionTagLink(Base):
    __tablename__ = "mcq_question_tag_link"
    __table_args__ = (PrimaryKeyConstraint("question_id", "tag_id"),)

    question_id = Column(Integer, ForeignKey("mcq_question.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("question_tag.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    question = relationship("McqQuestion", back_populates="tag_links")
    tag = relationship("QuestionTag", back_populates="question_links")

class McqQuestion(Base):
    __tablename__ = "mcq_question"
    __table_args__ = (
        CheckConstraint("correct_option IN ('A', 'B', 'C', 'D')", name="ck_mcq_question_correct_option"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    question_text = Column(Text, nullable=False)
    option_a = Column(Text, nullable=False)
    option_b = Column(Text, nullable=False)
    option_c = Column(Text, nullable=True)
    option_d = Column(Text, nullable=True)
    correct_option = Column(String(1), nullable=False)
    explanation = Column(Text, nullable=True)
    hint = Column(Text, nullable=True)
    difficulty_level = Column(SAEnum(DifficultyLevelEnum, name="difficulty_level_enum", create_type=False), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates
    user_id = Column(Integer, ForeignKey("user.id"), nullable=True)

    creator = relationship("User", back_populates="created_questions")
    tag_links = relationship("McqQuestionTagLink", back_populates="question", cascade="all, delete-orphan")
    quiz_links = relationship("McqQuizQuestionLink", back_populates="question", cascade="all, delete-orphan")

class QuestionTag(Base):
    __tablename__ = "question_tag"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates

    question_links = relationship("McqQuestionTagLink", back_populates="tag", cascade="all, delete-orphan")

class McqQuizQuestionLink(Base):
    __tablename__ = "mcq_quiz_question_link"
    __table_args__ = (PrimaryKeyConstraint("quiz_id", "question_id"),)

    quiz_id = Column(Integer, ForeignKey("mcq_quiz.id"), primary_key=True)
    question_id = Column(Integer, ForeignKey("mcq_question.id"), primary_key=True)
    display_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    quiz = relationship("McqQuiz", back_populates="question_links")
    question = relationship("McqQuestion", back_populates="quiz_links")

class McqQuiz(Base):
    __tablename__ = "mcq_quiz"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    difficulty_level = Column(SAEnum(DifficultyLevelEnum, name="difficulty_level_enum", create_type=False), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates
    is_active = Column(Boolean, nullable=False, server_default='true')
    is_public = Column(Boolean, nullable=False, server_default='false')
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subject.id"), nullable=True)
    community_id = Column(Integer, ForeignKey("community.id"), nullable=True)

    creator = relationship("User", back_populates="created_quizzes")
    subject = relationship("Subject", back_populates="quizzes")
    question_links = relationship("McqQuizQuestionLink", back_populates="quiz", cascade="all, delete-orphan")
    sessions = relationship("QuizSession", back_populates="quiz", cascade="all, delete-orphan")
    community = relationship("Community", back_populates="quizzes")

class QuizSession(Base):
    __tablename__ = "quiz_session"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    quiz_id = Column(Integer, ForeignKey("mcq_quiz.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    score = Column(Integer, nullable=True)
    total_questions = Column(Integer, nullable=False)
    answers_json = Column(JSONB, nullable=True)  # Store user answers as JSON
    time_taken_seconds = Column(Integer, nullable=True)

    user = relationship("User", back_populates="quiz_sessions")
    quiz = relationship("McqQuiz", back_populates="sessions")

# Content Interaction & Meta Models
class ContentComment(Base):
    __tablename__ = "content_comment"
    __table_args__ = (Index("idx_content_comment_type_id", "content_type", "content_id"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    author_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    content_type = Column(SAEnum(ContentTypeEnum, name="content_type_enum", create_type=False), nullable=False)
    content_id = Column(Integer, nullable=False)
    comment_text = Column(Text, nullable=False)
    parent_comment_id = Column(Integer, ForeignKey("content_comment.id"), nullable=True)
    is_deleted = Column(Boolean, nullable=False, server_default='false')
    is_edited = Column(Boolean, nullable=False, server_default='false')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates

    author = relationship("User", back_populates="comments_authored")
    parent_comment = relationship("ContentComment", remote_side=[id], backref=backref('replies', lazy='dynamic', cascade="all, delete-orphan"))

class ContentVersion(Base):
    __tablename__ = "content_version"
    __table_args__ = (
        UniqueConstraint("content_type", "content_id", "version_number", name="uq_content_version_type_id_version"),
        Index("idx_content_version_type_id", "content_type", "content_id"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    content_type = Column(SAEnum(ContentTypeEnum, name="content_type_enum", create_type=False), nullable=False)
    content_id = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    version_data = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user_creator = relationship("User", back_populates="versions_created")

class ContentAnalytics(Base):
    __tablename__ = "content_analytics"
    __table_args__ = (
        PrimaryKeyConstraint("content_type", "content_id", name="pk_content_analytics"),
    )

    content_type = Column(SAEnum(ContentTypeEnum, name="content_type_enum", create_type=False), primary_key=True)
    content_id = Column(Integer, primary_key=True)
    view_count = Column(Integer, nullable=False, server_default='0')
    like_count = Column(Integer, nullable=False, server_default='0')
    share_count = Column(Integer, nullable=False, server_default='0')
    comment_count = Column(Integer, nullable=False, server_default='0')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates

# --- Community Feature Models ---

class Community(Base):
    __tablename__ = "community"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    creator_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates
    is_private = Column(Boolean, nullable=False, server_default='false')

    creator = relationship("User", back_populates="created_communities")
    members = relationship("CommunityMember", back_populates="community", cascade="all, delete-orphan")
    subject_links = relationship("CommunitySubjectLink", back_populates="community", cascade="all, delete-orphan")
    subject_files = relationship("CommunitySubjectFile", back_populates="community", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="related_community", cascade="all, delete-orphan")
    quizzes = relationship("McqQuiz", back_populates="community")
    summaries = relationship("Summary", back_populates="community")

class CommunityMember(Base):
    __tablename__ = "community_member"
    __table_args__ = (PrimaryKeyConstraint("community_id", "user_id"),)

    community_id = Column(Integer, ForeignKey("community.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    role = Column(SAEnum(CommunityRoleEnum, name="community_role_enum", create_type=False), nullable=False, server_default=CommunityRoleEnum.member.value)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    # updated_at can be added if role/status changes are tracked with a DB trigger

    community = relationship("Community", back_populates="members")
    user = relationship("User", back_populates="community_memberships")

class CommunitySubjectLink(Base):
    __tablename__ = "community_subject_link"
    __table_args__ = (PrimaryKeyConstraint("community_id", "subject_id"),)

    community_id = Column(Integer, ForeignKey("community.id"), primary_key=True)
    subject_id = Column(Integer, ForeignKey("subject.id"), primary_key=True)
    added_by_user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    community = relationship("Community", back_populates="subject_links")
    subject = relationship("Subject", back_populates="community_links")
    added_by_user = relationship("User", back_populates="community_subjects_added")

class CommunitySubjectFile(Base):
    __tablename__ = "community_subject_file"
    __table_args__ = (
        UniqueConstraint("community_id", "subject_id", "physical_file_id", name="uq_community_subject_file"),
        # Consider adding a ForeignKeyConstraint to ensure (community_id, subject_id) exists in community_subject_link
        # ForeignKeyConstraint(['community_id', 'subject_id'], ['community_subject_link.community_id', 'community_subject_link.subject_id'])
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    community_id = Column(Integer, ForeignKey("community.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subject.id"), nullable=False)
    physical_file_id = Column(Integer, ForeignKey("physical_file.id"), nullable=False)
    file_category = Column(SAEnum(CommunityFileCategoryEnum, name="community_file_category_enum", create_type=False), nullable=False)
    uploaded_by_user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates

    community = relationship("Community", back_populates="subject_files")
    subject = relationship("Subject", back_populates="community_files")
    physical_file = relationship("PhysicalFile", back_populates="community_subject_files")
    uploaded_by_user = relationship("User", back_populates="community_files_uploaded")

# --- Enhanced Features Models ---

class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = (Index("idx_notification_user_read_created", "user_id", "is_read", "created_at"),)

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False) # Recipient
    notification_type = Column(SAEnum(NotificationTypeEnum, name="notification_type_enum", create_type=False), nullable=False)
    
    related_content_type = Column(SAEnum(ContentTypeEnum, name="content_type_enum", create_type=False), nullable=True)
    related_content_id = Column(Integer, nullable=True)
    related_community_id = Column(Integer, ForeignKey("community.id"), nullable=True)
    actor_id = Column(Integer, ForeignKey("user.id"), nullable=True) # User who triggered

    message = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, server_default='false')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger for is_read change

    recipient_user = relationship("User", foreign_keys=[user_id], back_populates="notifications")
    actor_user = relationship("User", foreign_keys=[actor_id], back_populates="triggered_notifications")
    related_community = relationship("Community", back_populates="notifications")
    # Polymorphic relationship to actual content (e.g., quiz, summary) can be set up in application logic
    # or via a more complex association if direct SQL joins are needed frequently.

class ContentRating(Base):
    __tablename__ = "content_rating"
    __table_args__ = (
        UniqueConstraint("user_id", "content_type", "content_id", name="uq_user_content_rating"),
        Index("idx_content_rating_type_id", "content_type", "content_id"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    content_type = Column(SAEnum(ContentTypeEnum, name="content_type_enum", create_type=False), nullable=False)
    content_id = Column(Integer, nullable=False)
    rating = Column(SAEnum(RatingValueEnum, name="rating_value_enum", create_type=False), nullable=False)
    review_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger if reviews can be edited

    user = relationship("User", back_populates="ratings_given")
    # Polymorphic relationship to actual content can be set up in application logic.

class UserPreference(Base):
    __tablename__ = "user_preference"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, unique=True)
    email_notifications_enabled = Column(Boolean, nullable=False, server_default='true')
    default_theme = Column(String(50), nullable=False, server_default='light')
    default_content_filter_difficulty = Column(SAEnum(DifficultyLevelEnum, name="difficulty_level_enum", create_type=False), nullable=True)
    preferences_json = Column(JSONB, nullable=True) # For more dynamic preferences
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates

    user = relationship("User", back_populates="preferences")

class UserFreeApiUsage(Base):
    __tablename__ = "user_free_api_usage"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, unique=True)
    api_provider = Column(SAEnum(AiProviderEnum, name="ai_provider_enum", create_type=False), nullable=False)
    usage_count = Column(Integer, nullable=False, server_default='0')
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now()) # DB trigger handles updates

    user = relationship("User", back_populates="free_api_usage")

__all__ = [
"User", "UserSession", "AiApiKey", "Subject", "PhysicalFile", "UserFileAccess",
"Summary", "McqQuestionTagLink", "McqQuestion", "QuestionTag",
"McqQuizQuestionLink", "McqQuiz", "QuizSession", "ContentComment",
"ContentVersion", "ContentAnalytics", "GeminiFileCache", "UserFreeApiUsage",
"Community", "CommunityMember", "CommunitySubjectLink", "CommunitySubjectFile",
"Notification", "ContentRating", "UserPreference",
"UserRoleEnum", "DifficultyLevelEnum", "AiProviderEnum", "ContentTypeEnum",
"CommunityRoleEnum", "CommunityFileCategoryEnum", "NotificationTypeEnum", "RatingValueEnum"
]
