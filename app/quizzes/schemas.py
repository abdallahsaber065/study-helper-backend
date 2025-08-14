"""
Pydantic schemas for quiz API requests and responses.

This module contains all request and response schemas for the quiz system,
including validation, serialization, and comprehensive data models.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator, validator


# Enums matching database models
class QuizStatus(str, Enum):
    """Quiz generation and lifecycle status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class QuizDifficulty(str, Enum):
    """Quiz difficulty levels."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    ADAPTIVE = "adaptive"


class QuestionType(str, Enum):
    """Types of questions supported in quizzes."""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    LONG_ANSWER = "long_answer"
    ESSAY = "essay"
    FILL_IN_BLANK = "fill_in_blank"
    MATCHING = "matching"
    ORDERING = "ordering"


class AttemptStatus(str, Enum):
    """Quiz attempt status."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    TIME_EXPIRED = "time_expired"


class AIProvider(str, Enum):
    """Supported AI providers for quiz generation."""
    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"


# Request schemas
class QuizGenerateRequest(BaseModel):
    """Request schema for generating a new quiz."""
    
    file_id: str = Field(..., description="ID of the file to generate quiz from")
    title: str = Field(..., min_length=1, max_length=255, description="Title for the quiz")
    description: Optional[str] = Field(
        None, 
        max_length=1000, 
        description="Optional description of the quiz"
    )
    
    # Quiz configuration
    difficulty_level: QuizDifficulty = Field(
        default=QuizDifficulty.INTERMEDIATE,
        description="Target difficulty level for the quiz"
    )
    question_count: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of questions to generate"
    )
    estimated_time_minutes: int = Field(
        default=30,
        ge=5,
        le=180,
        description="Estimated time to complete the quiz"
    )
    time_limit_minutes: Optional[int] = Field(
        None,
        ge=5,
        le=300,
        description="Time limit for quiz completion"
    )
    
    # Question type preferences
    question_types: Optional[List[QuestionType]] = Field(
        default=None,
        description="Preferred question types to include"
    )
    question_type_distribution: Optional[Dict[str, int]] = Field(
        default=None,
        description="Distribution of question types (type -> count)"
    )
    
    # Content focus
    topics_to_focus: Optional[List[str]] = Field(
        default=None,
        max_items=20,
        description="Specific topics to focus on"
    )
    topics_to_exclude: Optional[List[str]] = Field(
        default=None,
        max_items=20,
        description="Topics to exclude from the quiz"
    )
    learning_objectives: Optional[List[str]] = Field(
        default=None,
        max_items=10,
        description="Specific learning objectives to target"
    )
    
    # AI processing options
    ai_provider: Optional[AIProvider] = Field(
        default=None,
        description="AI provider to use (defaults to system default)"
    )
    ai_model: Optional[str] = Field(
        default=None,
        pattern=r"^[a-zA-Z0-9\-_.]+$",
        description="Specific AI model to use"
    )
    custom_instructions: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Custom instructions for quiz generation"
    )
    
    # Quiz settings
    shuffle_questions: bool = Field(
        default=True,
        description="Whether to shuffle question order"
    )
    shuffle_answers: bool = Field(
        default=True,
        description="Whether to shuffle answer options"
    )
    show_correct_answers: bool = Field(
        default=True,
        description="Show correct answers after completion"
    )
    allow_retries: bool = Field(
        default=True,
        description="Allow multiple attempts"
    )
    max_attempts: Optional[int] = Field(
        default=None,
        ge=1,
        le=10,
        description="Maximum number of attempts allowed"
    )
    passing_score: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="Minimum percentage score to pass"
    )

    @field_validator("file_id")
    @classmethod
    def validate_file_id(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("File ID is required")
        return v.strip()

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Title is required")
        return v.strip()

    @field_validator("question_types")
    @classmethod
    def validate_question_types(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError("If provided, question_types must not be empty")
        return v

    @model_validator(mode='after')
    def validate_question_distribution(self):
        """Validate that question type distribution matches total count."""
        if self.question_type_distribution:
            total_distributed = sum(self.question_type_distribution.values())
            if total_distributed != self.question_count:
                raise ValueError(f"Question type distribution total ({total_distributed}) must equal question_count ({self.question_count})")
        
        return self


class QuizUpdateRequest(BaseModel):
    """Request schema for updating quiz metadata."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    difficulty_level: Optional[QuizDifficulty] = None
    time_limit_minutes: Optional[int] = Field(None, ge=5, le=300)
    
    # Quiz settings
    shuffle_questions: Optional[bool] = None
    shuffle_answers: Optional[bool] = None
    show_correct_answers: Optional[bool] = None
    allow_retries: Optional[bool] = None
    max_attempts: Optional[int] = Field(None, ge=1, le=10)
    passing_score: Optional[int] = Field(None, ge=0, le=100)
    
    # User feedback
    user_rating: Optional[int] = Field(None, ge=1, le=5)
    user_feedback: Optional[str] = Field(None, max_length=2000)
    difficulty_rating: Optional[int] = Field(None, ge=1, le=5)


class QuizRegenerateRequest(BaseModel):
    """Request schema for regenerating quiz questions."""
    
    ai_provider: Optional[AIProvider] = None
    ai_model: Optional[str] = Field(None, pattern=r"^[a-zA-Z0-9\-_.]+$")
    difficulty_level: Optional[QuizDifficulty] = None
    question_count: Optional[int] = Field(None, ge=1, le=50)
    question_types: Optional[List[QuestionType]] = None
    custom_instructions: Optional[str] = Field(None, max_length=2000)
    regenerate_all: bool = Field(
        default=False,
        description="Whether to regenerate all questions or just add new ones"
    )


class QuizAttemptStartRequest(BaseModel):
    """Request schema for starting a quiz attempt."""
    
    session_id: Optional[str] = Field(None, max_length=36)
    shuffle_questions: Optional[bool] = Field(
        None,
        description="Override quiz setting for question shuffling"
    )
    shuffle_answers: Optional[bool] = Field(
        None,
        description="Override quiz setting for answer shuffling"
    )


class QuestionAnswerRequest(BaseModel):
    """Request schema for answering a question."""

    question_id: str = Field(..., description="ID of the question being answered")
    user_answer: Optional[str] = Field(None, description="Text answer for open-ended questions")
    selected_answer_ids: Optional[List[str]] = Field(
        None,
        description="Selected answer IDs for multiple choice questions"
    )
    response_time_seconds: int = Field(
        ...,
        ge=0,
        description="Time taken to answer the question"
    )
    confidence_level: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="User's confidence level in their answer"
    )

    @model_validator(mode='after')
    def validate_answer_provided(self): 
        """Ensure at least one answer is provided."""
        if not self.user_answer and not self.selected_answer_ids:
            raise ValueError("Either user_answer or selected_answer_ids must be provided")
        
        return self


class QuizAttemptCompleteRequest(BaseModel):
    """Request schema for completing a quiz attempt."""
    
    user_feedback: Optional[str] = Field(None, max_length=2000)
    difficulty_rating: Optional[int] = Field(None, ge=1, le=5)


# Response schemas
class AnswerResponse(BaseModel):
    """Response schema for quiz answer options."""
    
    id: str
    answer_text: str
    order_index: int
    is_correct: Optional[bool] = None  # Only shown after completion if configured
    explanation: Optional[str] = None
    points: Optional[Decimal] = None
    
    class Config:
        from_attributes = True


class QuestionResponse(BaseModel):
    """Response schema for quiz questions."""
    
    id: str
    question_text: str
    question_type: QuestionType
    order_index: int
    difficulty_level: QuizDifficulty
    points: Decimal
    time_limit_seconds: Optional[int] = None
    
    # Content metadata
    topic: Optional[str] = None
    learning_objective: Optional[str] = None
    cognitive_level: Optional[str] = None
    context: Optional[str] = None
    
    # Quality metrics (for analytics)
    quality_score: Optional[Decimal] = None
    success_rate: Optional[float] = None
    average_response_time: Optional[int] = None
    
    # Answers
    answers: List[AnswerResponse] = []
    
    class Config:
        from_attributes = True


class QuizProgressResponse(BaseModel):
    """Response schema for quiz generation progress."""
    
    task_id: str
    quiz_id: str
    status: QuizStatus
    progress_percentage: int = Field(ge=0, le=100)
    current_step: Optional[str] = None
    estimated_time_remaining: Optional[int] = None
    questions_generated: Optional[int] = None
    total_questions_target: Optional[int] = None


class QuizMetrics(BaseModel):
    """Quiz generation and performance metrics."""
    
    # Generation metrics
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    generation_cost: Optional[Decimal] = None
    processing_time_ms: Optional[int] = None
    
    # Content analysis
    content_complexity_score: Optional[Decimal] = None
    question_quality_avg: Optional[Decimal] = None
    ai_confidence_score: Optional[Decimal] = None
    
    # Performance metrics
    total_attempts: int = 0
    completed_attempts: int = 0
    average_score: Optional[Decimal] = None
    average_completion_time: Optional[int] = None
    success_rate: Optional[float] = None
    
    # Question analytics
    question_difficulty_distribution: Optional[Dict[str, int]] = None
    question_type_distribution: Optional[Dict[str, int]] = None
    topic_coverage: Optional[Dict[str, int]] = None


class QuizResponse(BaseModel):
    """Response schema for quiz data."""
    
    id: str
    user_id: int
    file_id: str
    title: str
    description: Optional[str] = None
    
    # Configuration
    difficulty_level: QuizDifficulty
    question_count: int
    estimated_time_minutes: int
    time_limit_minutes: Optional[int] = None
    
    # Content metadata
    topics_covered: Optional[List[str]] = None
    learning_objectives: Optional[List[str]] = None
    
    # AI processing info
    ai_provider: str
    ai_model_used: str
    prompt_template: Optional[str] = None
    
    # Status and progress
    status: QuizStatus
    progress_percentage: int
    error_message: Optional[str] = None
    
    # Quality and feedback
    quality_score: Optional[Decimal] = None
    user_rating: Optional[int] = None
    user_feedback: Optional[str] = None
    
    # Settings
    shuffle_questions: bool
    shuffle_answers: bool
    show_correct_answers: bool
    allow_retries: bool
    max_attempts: Optional[int] = None
    passing_score: Optional[Decimal] = None
    
    # Analytics
    metrics: Optional[QuizMetrics] = None
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    # Questions (optional, for detailed responses)
    questions: Optional[List[QuestionResponse]] = None
    
    class Config:
        from_attributes = True


class QuizListResponse(BaseModel):
    """Response schema for paginated quiz lists."""
    
    quizzes: List[QuizResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    
    # Aggregated statistics
    summary_stats: Optional[Dict[str, Any]] = None


class QuestionResponseDetail(BaseModel):
    """Response schema for individual question responses."""
    
    id: str
    question_id: str
    user_answer: Optional[str] = None
    selected_answer_ids: Optional[List[str]] = None
    is_correct: bool
    points_earned: Decimal
    max_points: Decimal
    response_time_seconds: int
    confidence_level: Optional[int] = None
    answered_at: datetime
    
    class Config:
        from_attributes = True


class QuizAttemptResponse(BaseModel):
    """Response schema for quiz attempt data."""
    
    id: str
    quiz_id: str
    user_id: int
    attempt_number: int
    status: AttemptStatus
    
    # Scoring
    total_score: Decimal
    max_possible_score: Decimal
    percentage_score: Optional[Decimal] = None
    passed: Optional[bool] = None
    
    # Progress
    questions_answered: int
    questions_correct: int
    current_question_index: int
    
    # Timing
    started_at: datetime
    completed_at: Optional[datetime] = None
    time_spent_seconds: Optional[int] = None
    time_limit_seconds: Optional[int] = None
    
    # Analytics
    topic_scores: Optional[Dict[str, float]] = None
    difficulty_progression: Optional[List[str]] = None
    
    # Feedback
    user_feedback: Optional[str] = None
    difficulty_rating: Optional[int] = None
    
    # Responses (optional, for detailed view)
    responses: Optional[List[QuestionResponseDetail]] = None
    
    class Config:
        from_attributes = True


class QuizAttemptListResponse(BaseModel):
    """Response schema for paginated quiz attempt lists."""
    
    attempts: List[QuizAttemptResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class QuizAnalytics(BaseModel):
    """Comprehensive analytics for quiz performance."""
    
    quiz_id: str
    
    # Overall statistics
    total_attempts: int
    unique_users: int
    completion_rate: float
    average_score: Decimal
    pass_rate: Optional[float] = None
    
    # Time analytics
    average_completion_time: int
    time_distribution: Dict[str, int]  # time ranges -> count
    
    # Question analytics
    question_analytics: List[Dict[str, Any]]  # Per question stats
    difficult_questions: List[str]  # Question IDs with low success rate
    easy_questions: List[str]  # Question IDs with high success rate
    
    # Learning analytics
    learning_objectives_mastery: Optional[Dict[str, float]] = None
    topic_mastery: Optional[Dict[str, float]] = None
    common_misconceptions: Optional[List[str]] = None
    
    # Improvement suggestions
    suggested_improvements: List[str]
    
    # Comparative analytics
    performance_vs_difficulty: Dict[str, float]
    user_progression_patterns: Optional[List[Dict[str, Any]]] = None


class ExportRequest(BaseModel):
    """Request schema for exporting quizzes."""
    
    format: str = Field(..., pattern="^(pdf|json|csv|scorm)$")
    include_analytics: bool = Field(default=False)
    include_answers: bool = Field(default=True)
    include_explanations: bool = Field(default=True)
    custom_branding: Optional[Dict[str, str]] = None


class ExportResponse(BaseModel):
    """Response schema for quiz export."""
    
    export_id: str
    format: str
    download_url: str
    expires_at: datetime
    file_size_bytes: Optional[int] = None


# Validation and filtering schemas
class QuizFilters(BaseModel):
    """Filters for quiz queries."""
    
    status: Optional[List[QuizStatus]] = None
    difficulty_level: Optional[List[QuizDifficulty]] = None
    ai_provider: Optional[List[AIProvider]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    min_quality_score: Optional[float] = Field(None, ge=0.0, le=5.0)
    has_user_rating: Optional[bool] = None
    
    # Content filters
    topic: Optional[str] = Field(None, max_length=100)
    learning_objective: Optional[str] = Field(None, max_length=200)
    question_count_min: Optional[int] = Field(None, ge=1)
    question_count_max: Optional[int] = Field(None, le=50)
    
    # Search
    search_query: Optional[str] = Field(None, max_length=200)
    
    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    
    # Sorting
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")

    @validator("sort_by")
    def validate_sort_by(cls, v):
        allowed_fields = [
            "created_at", "updated_at", "title", "difficulty_level",
            "question_count", "user_rating", "total_attempts", "average_score"
        ]
        if v not in allowed_fields:
            raise ValueError(f"sort_by must be one of: {', '.join(allowed_fields)}")
        return v


class BulkQuizOperation(BaseModel):
    """Schema for bulk operations on quizzes."""
    
    quiz_ids: List[str] = Field(..., min_items=1, max_items=50)
    operation: str = Field(..., pattern="^(delete|archive|regenerate|export)$")
    parameters: Optional[Dict[str, Any]] = None

    @validator("parameters")
    def validate_parameters(cls, v, values):
        """Validate parameters based on operation type."""
        operation = values.get("operation")
        
        if operation == "export" and v:
            # Validate export parameters
            allowed_formats = ["pdf", "json", "csv", "scorm"]
            if "format" in v and v["format"] not in allowed_formats:
                raise ValueError(f"Export format must be one of: {', '.join(allowed_formats)}")
        
        return v


# WebSocket message schemas
class TaskProgressUpdate(BaseModel):
    """WebSocket message for task progress updates."""
    
    task_id: str
    quiz_id: str
    status: QuizStatus
    progress_percentage: int
    current_step: Optional[str] = None
    estimated_time_remaining: Optional[int] = None
    questions_generated: Optional[int] = None
    error_message: Optional[str] = None
    
    class Config:
        use_enum_values = True


class QuizAttemptUpdate(BaseModel):
    """WebSocket message for quiz attempt updates."""
    
    attempt_id: str
    quiz_id: str
    user_id: int
    status: AttemptStatus
    current_question_index: int
    questions_answered: int
    current_score: Decimal
    time_remaining_seconds: Optional[int] = None
    
    class Config:
        use_enum_values = True
