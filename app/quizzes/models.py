"""
Quiz database models for AI-powered quiz generation system.

This module contains all database models for the quiz system including:
- Quiz: Main quiz container with metadata and configuration
- Question: Individual questions with multiple types and difficulty levels
- Answer: Possible answers for questions (MCQ options, correct answers)
- QuizAttempt: User attempts at quizzes with scoring and analytics
- QuizSession: Session management for ongoing quiz attempts
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import (
    DateTime, ForeignKey, Integer, Numeric, String, Text, Float, Boolean, 
    JSON, func, Index, CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from ..users.models import User
    from ..files.models import FileMetadata


class QuizDifficulty(str, Enum):
    """Quiz difficulty levels."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    ADAPTIVE = "adaptive"  # AI determines difficulty based on content


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


class QuizStatus(str, Enum):
    """Quiz generation and lifecycle status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class AttemptStatus(str, Enum):
    """Quiz attempt status."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    TIME_EXPIRED = "time_expired"


class Quiz(Base):
    """
    Main quiz model containing quiz metadata, configuration, and AI generation tracking.
    
    This model tracks all aspects of AI-powered quiz generation including:
    - Quiz configuration and parameters
    - AI processing status and metrics
    - Question relationships and analytics
    - User interaction and performance data
    """
    
    __tablename__ = "quizzes"

    # Primary identification
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Foreign key relationships
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    file_id: Mapped[str] = mapped_column(ForeignKey("file_metadata.id"), nullable=False)
    
    # Quiz metadata and configuration
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    difficulty_level: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default=QuizDifficulty.INTERMEDIATE
    )
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    estimated_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    time_limit_minutes: Mapped[Optional[int]] = mapped_column(Integer)  # Optional time limit
    
    # Content analysis and learning objectives
    topics_covered: Mapped[Optional[str]] = mapped_column(JSON)  # List of topics
    learning_objectives: Mapped[Optional[str]] = mapped_column(JSON)  # Learning goals
    content_complexity_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    
    # AI processing information
    ai_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_template: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Usage and cost tracking
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    generation_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Task processing tracking
    task_id: Mapped[Optional[str]] = mapped_column(String(36))
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default=QuizStatus.PENDING
    )
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Quality metrics and validation
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))  # 0.00-5.00
    ai_confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    question_quality_avg: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    user_rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5 stars
    user_feedback: Mapped[Optional[str]] = mapped_column(Text)
    
    # Quiz configuration and parameters
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=True)
    shuffle_answers: Mapped[bool] = mapped_column(Boolean, default=True)
    show_correct_answers: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_retries: Mapped[bool] = mapped_column(Boolean, default=True)
    max_attempts: Mapped[Optional[int]] = mapped_column(Integer)
    passing_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))  # Percentage
    
    # Performance analytics
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    completed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    average_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    average_completion_time: Mapped[Optional[int]] = mapped_column(Integer)  # seconds
    difficulty_rating: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))  # User feedback
    
    # Generation parameters
    custom_instructions: Mapped[Optional[str]] = mapped_column(Text)
    focus_areas: Mapped[Optional[str]] = mapped_column(JSON)  # List of focus areas
    excluded_topics: Mapped[Optional[str]] = mapped_column(JSON)  # Topics to exclude
    question_types: Mapped[Optional[str]] = mapped_column(JSON)  # Allowed question types
    
    # Audit and timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Soft delete support
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="quizzes")
    file_metadata: Mapped["FileMetadata"] = relationship("FileMetadata", back_populates="quizzes")
    questions: Mapped[List["Question"]] = relationship(
        "Question", 
        back_populates="quiz", 
        cascade="all, delete-orphan",
        order_by="Question.order_index"
    )
    attempts: Mapped[List["QuizAttempt"]] = relationship(
        "QuizAttempt", 
        back_populates="quiz", 
        cascade="all, delete-orphan"
    )
    
    # Database constraints
    __table_args__ = (
        CheckConstraint('question_count > 0', name='positive_question_count'),
        CheckConstraint('estimated_time_minutes > 0', name='positive_estimated_time'),
        CheckConstraint('progress_percentage >= 0 AND progress_percentage <= 100', name='valid_progress'),
        CheckConstraint('quality_score IS NULL OR (quality_score >= 0.0 AND quality_score <= 5.0)', name='valid_quality_score'),
        CheckConstraint('user_rating IS NULL OR (user_rating >= 1 AND user_rating <= 5)', name='valid_user_rating'),
        Index('idx_quiz_user_status', 'user_id', 'status'),
        Index('idx_quiz_file_status', 'file_id', 'status'),
        Index('idx_quiz_created_at', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<Quiz(id={self.id}, title='{self.title}', status='{self.status}')>"
    
    @property
    def is_completed(self) -> bool:
        """Check if quiz generation is completed."""
        return self.status == QuizStatus.COMPLETED
    
    @property
    def is_failed(self) -> bool:
        """Check if quiz generation failed."""
        return self.status == QuizStatus.FAILED
    
    @property
    def is_processing(self) -> bool:
        """Check if quiz is currently being processed."""
        return self.status in [QuizStatus.PENDING, QuizStatus.PROCESSING]
    
    def mark_as_processing(self, task_id: str, correlation_id: str) -> None:
        """Mark quiz as processing with task identifiers."""
        self.status = QuizStatus.PROCESSING
        self.task_id = task_id
        self.correlation_id = correlation_id
        self.progress_percentage = 0
    
    def mark_as_completed(self, processing_time_ms: int) -> None:
        """Mark quiz as completed with processing time."""
        self.status = QuizStatus.COMPLETED
        self.progress_percentage = 100
        self.processing_time_ms = processing_time_ms
        self.completed_at = func.now()
        self.error_message = None
    
    def mark_as_failed(self, error_message: str) -> None:
        """Mark quiz as failed with error message."""
        self.status = QuizStatus.FAILED
        self.error_message = error_message[:1000]  # Truncate long error messages
        self.completed_at = func.now()
    
    def update_progress(self, percentage: int) -> None:
        """Update processing progress percentage."""
        if 0 <= percentage <= 100:
            self.progress_percentage = percentage
    
    def soft_delete(self) -> None:
        """Soft delete the quiz."""
        self.deleted_at = func.now()
    
    def archive(self) -> None:
        """Archive the quiz."""
        self.archived_at = func.now()
        self.status = QuizStatus.ARCHIVED
    
    def update_analytics(self, attempt_score: Decimal, completion_time: int) -> None:
        """Update quiz analytics with new attempt data."""
        self.total_attempts += 1
        
        # Update average score
        if self.average_score is None:
            self.average_score = attempt_score
        else:
            total_score = self.average_score * (self.total_attempts - 1) + attempt_score
            self.average_score = total_score / self.total_attempts
        
        # Update average completion time
        if self.average_completion_time is None:
            self.average_completion_time = completion_time
        else:
            total_time = self.average_completion_time * (self.total_attempts - 1) + completion_time
            self.average_completion_time = int(total_time / self.total_attempts)


class Question(Base):
    """
    Individual question model with support for multiple question types and difficulty levels.
    
    This model supports various question types with flexible answer storage
    and comprehensive analytics tracking.
    """
    
    __tablename__ = "questions"
    
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id"), nullable=False)
    
    # Question content and metadata
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default=QuestionType.MULTIPLE_CHOICE
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Difficulty and scoring
    difficulty_level: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default=QuizDifficulty.INTERMEDIATE
    )
    points: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=1.0)
    time_limit_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Content analysis and categorization
    topic: Mapped[Optional[str]] = mapped_column(String(100))
    learning_objective: Mapped[Optional[str]] = mapped_column(String(200))
    cognitive_level: Mapped[Optional[str]] = mapped_column(String(50))  # Bloom's taxonomy
    
    # Question context and references
    context: Mapped[Optional[str]] = mapped_column(Text)  # Additional context
    source_reference: Mapped[Optional[str]] = mapped_column(String(200))  # Reference to source material
    explanation: Mapped[Optional[str]] = mapped_column(Text)  # Explanation for correct answer
    
    # Quality and validation metrics
    quality_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    ai_confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    difficulty_rating: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))  # From user feedback
    clarity_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    
    # Performance analytics
    times_answered: Mapped[int] = mapped_column(Integer, default=0)
    times_correct: Mapped[int] = mapped_column(Integer, default=0)
    average_response_time: Mapped[Optional[int]] = mapped_column(Integer)  # seconds
    discrimination_index: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))  # Item analysis
    
    # Question-specific configuration
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_partial_credit: Mapped[bool] = mapped_column(Boolean, default=False)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)  # For text answers
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    quiz: Mapped[Quiz] = relationship("Quiz", back_populates="questions")
    answers: Mapped[List["Answer"]] = relationship(
        "Answer", 
        back_populates="question", 
        cascade="all, delete-orphan",
        order_by="Answer.order_index"
    )
    responses: Mapped[List["QuestionResponse"]] = relationship(
        "QuestionResponse", 
        back_populates="question", 
        cascade="all, delete-orphan"
    )
    
    # Database constraints
    __table_args__ = (
        CheckConstraint('points > 0', name='positive_points'),
        CheckConstraint('order_index >= 0', name='non_negative_order'),
        CheckConstraint('times_correct <= times_answered', name='logical_answer_counts'),
        Index('idx_question_quiz_order', 'quiz_id', 'order_index'),
        Index('idx_question_type_difficulty', 'question_type', 'difficulty_level'),
    )
    
    def __repr__(self) -> str:
        return f"<Question(id={self.id}, type='{self.question_type}', quiz_id='{self.quiz_id}')>"
    
    @property
    def success_rate(self) -> Optional[float]:
        """Calculate success rate for this question."""
        if self.times_answered == 0:
            return None
        return float(self.times_correct) / float(self.times_answered)
    
    def update_analytics(self, is_correct: bool, response_time: int) -> None:
        """Update question analytics with new response data."""
        self.times_answered += 1
        if is_correct:
            self.times_correct += 1
        
        # Update average response time
        if self.average_response_time is None:
            self.average_response_time = response_time
        else:
            total_time = self.average_response_time * (self.times_answered - 1) + response_time
            self.average_response_time = int(total_time / self.times_answered)


class Answer(Base):
    """
    Answer options and correct answers for questions.
    
    This model handles multiple answer types:
    - Multiple choice options
    - Correct answers for any question type
    - Partial scoring for complex answers
    """
    
    __tablename__ = "answers"
    
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), nullable=False)
    
    # Answer content
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Answer properties
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    points: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))  # Partial credit
    
    # Answer analysis and feedback
    explanation: Mapped[Optional[str]] = mapped_column(Text)  # Why this answer is correct/incorrect
    distractor_type: Mapped[Optional[str]] = mapped_column(String(50))  # Type of incorrect answer
    
    # Performance tracking
    times_selected: Mapped[int] = mapped_column(Integer, default=0)
    selection_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    
    # Relationships
    question: Mapped[Question] = relationship("Question", back_populates="answers")
    
    # Database constraints
    __table_args__ = (
        CheckConstraint('order_index >= 0', name='non_negative_order'),
        CheckConstraint('times_selected >= 0', name='non_negative_selections'),
        Index('idx_answer_question_order', 'question_id', 'order_index'),
        Index('idx_answer_correct', 'question_id', 'is_correct'),
    )
    
    def __repr__(self) -> str:
        return f"<Answer(id={self.id}, question_id='{self.question_id}', is_correct={self.is_correct})>"
    
    def update_selection_stats(self, total_responses: int) -> None:
        """Update selection statistics for this answer."""
        if total_responses > 0:
            self.selection_percentage = Decimal(self.times_selected) / Decimal(total_responses) * 100


class QuizAttempt(Base):
    """
    User attempts at quizzes with comprehensive tracking and analytics.
    
    This model tracks complete quiz attempts including:
    - Scoring and performance metrics
    - Time tracking and session management
    - Individual question responses
    - Learning analytics and insights
    """
    
    __tablename__ = "quiz_attempts"
    
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Foreign key relationships
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    
    # Attempt metadata
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default=AttemptStatus.IN_PROGRESS
    )
    
    # Scoring and performance
    total_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal('0.00'))
    max_possible_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    percentage_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    
    # Time tracking
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    time_spent_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    time_limit_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Progress tracking
    questions_answered: Mapped[int] = mapped_column(Integer, default=0)
    questions_correct: Mapped[int] = mapped_column(Integer, default=0)
    current_question_index: Mapped[int] = mapped_column(Integer, default=0)
    
    # Session and environment
    session_id: Mapped[Optional[str]] = mapped_column(String(36))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Learning analytics
    learning_path: Mapped[Optional[str]] = mapped_column(JSON)  # Question order taken
    difficulty_progression: Mapped[Optional[str]] = mapped_column(JSON)  # Difficulty over time
    topic_scores: Mapped[Optional[str]] = mapped_column(JSON)  # Score by topic
    response_patterns: Mapped[Optional[str]] = mapped_column(JSON)  # Response time patterns
    
    # Feedback and notes
    user_feedback: Mapped[Optional[str]] = mapped_column(Text)
    difficulty_rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5
    instructor_notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Audit trail
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    quiz: Mapped[Quiz] = relationship("Quiz", back_populates="attempts")
    user: Mapped["User"] = relationship("User", back_populates="quiz_attempts")
    responses: Mapped[List["QuestionResponse"]] = relationship(
        "QuestionResponse", 
        back_populates="attempt", 
        cascade="all, delete-orphan"
    )
    
    # Database constraints
    __table_args__ = (
        CheckConstraint('attempt_number > 0', name='positive_attempt_number'),
        CheckConstraint('total_score >= 0', name='non_negative_score'),
        CheckConstraint('questions_correct <= questions_answered', name='logical_correct_count'),
        CheckConstraint('difficulty_rating IS NULL OR (difficulty_rating >= 1 AND difficulty_rating <= 5)', name='valid_difficulty_rating'),
        Index('idx_attempt_quiz_user', 'quiz_id', 'user_id'),
        Index('idx_attempt_status_started', 'status', 'started_at'),
    )
    
    def __repr__(self) -> str:
        return f"<QuizAttempt(id={self.id}, quiz_id='{self.quiz_id}', user_id={self.user_id}, attempt={self.attempt_number})>"
    
    def calculate_percentage_score(self) -> Optional[Decimal]:
        """Calculate and update percentage score."""
        if self.max_possible_score > 0:
            self.percentage_score = (self.total_score / self.max_possible_score) * 100
            return self.percentage_score
        return None
    
    def mark_completed(self) -> None:
        """Mark attempt as completed and calculate final metrics."""
        self.status = AttemptStatus.COMPLETED
        self.completed_at = func.now()
        
        if self.started_at and self.completed_at:
            self.time_spent_seconds = int((self.completed_at - self.started_at).total_seconds())
        
        self.calculate_percentage_score()
        
        # Determine if passed (if quiz has passing score)
        if hasattr(self.quiz, 'passing_score') and self.quiz.passing_score is not None:
            self.passed = self.percentage_score >= self.quiz.passing_score
    
    def abandon(self) -> None:
        """Mark attempt as abandoned."""
        self.status = AttemptStatus.ABANDONED
        self.completed_at = func.now()
        
        if self.started_at and self.completed_at:
            self.time_spent_seconds = int((self.completed_at - self.started_at).total_seconds())


class QuestionResponse(Base):
    """
    Individual question responses within quiz attempts.
    
    This model tracks detailed response data for learning analytics
    and performance analysis.
    """
    
    __tablename__ = "question_responses"
    
    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    
    # Foreign key relationships
    attempt_id: Mapped[str] = mapped_column(ForeignKey("quiz_attempts.id"), nullable=False)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), nullable=False)
    
    # Response data
    user_answer: Mapped[Optional[str]] = mapped_column(Text)  # User's response
    selected_answer_ids: Mapped[Optional[str]] = mapped_column(JSON)  # For MCQ, multiple selection
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    points_earned: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal('0.00'))
    max_points: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    
    # Timing and interaction data
    response_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    time_to_first_interaction: Mapped[Optional[int]] = mapped_column(Integer)  # Time to first click/type
    interaction_count: Mapped[int] = mapped_column(Integer, default=1)  # Number of changes made
    
    # Answer analysis
    confidence_level: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5 if asked
    difficulty_perception: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5 user rating
    
    # Timestamps
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    
    # Relationships
    attempt: Mapped[QuizAttempt] = relationship("QuizAttempt", back_populates="responses")
    question: Mapped[Question] = relationship("Question", back_populates="responses")
    
    # Database constraints
    __table_args__ = (
        CheckConstraint('points_earned <= max_points', name='earned_not_exceed_max'),
        CheckConstraint('response_time_seconds >= 0', name='non_negative_response_time'),
        CheckConstraint('interaction_count >= 0', name='non_negative_interactions'),
        CheckConstraint('confidence_level IS NULL OR (confidence_level >= 1 AND confidence_level <= 5)', name='valid_confidence'),
        CheckConstraint('difficulty_perception IS NULL OR (difficulty_perception >= 1 AND difficulty_perception <= 5)', name='valid_difficulty_perception'),
        Index('idx_response_attempt_question', 'attempt_id', 'question_id'),
        Index('idx_response_correct_time', 'is_correct', 'response_time_seconds'),
    )
    
    def __repr__(self) -> str:
        return f"<QuestionResponse(id={self.id}, attempt_id='{self.attempt_id}', is_correct={self.is_correct})>"
    
    def calculate_partial_credit(self, grading_rubric: dict) -> Decimal:
        """Calculate partial credit based on grading rubric."""
        # Implementation would depend on question type and rubric
        # This is a placeholder for the scoring algorithm
        return self.points_earned
