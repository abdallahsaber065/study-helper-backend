"""
Pydantic schemas for MCQ and Quiz functionality.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from models.models import DifficultyLevelEnum, McqQuestion
import enum


# Enums for MCQ responses
class CorrectAnswerEnum(str, enum.Enum):
    A = "A"
    B = "B" 
    C = "C"
    D = "D"


# Question Tag Schemas
class QuestionTagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class QuestionTagCreate(QuestionTagBase):
    pass


class QuestionTagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class QuestionTagRead(QuestionTagBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# MCQ Question Schemas
class McqQuestionBase(BaseModel):
    question_text: str = Field(..., min_length=10, max_length=1000)
    option_a: str = Field(..., min_length=1, max_length=500)
    option_b: str = Field(..., min_length=1, max_length=500)
    option_c: Optional[str] = Field(None, max_length=500)
    option_d: Optional[str] = Field(None, max_length=500)
    correct_option: CorrectAnswerEnum
    explanation: Optional[str] = Field(None, max_length=1000)
    hint: Optional[str] = Field(None, max_length=500)
    difficulty_level: DifficultyLevelEnum


class McqQuestionCreate(McqQuestionBase):
    tag_ids: Optional[List[int]] = []


class McqQuestionUpdate(BaseModel):
    question_text: Optional[str] = Field(None, min_length=10, max_length=1000)
    option_a: Optional[str] = Field(None, min_length=1, max_length=500)
    option_b: Optional[str] = Field(None, min_length=1, max_length=500)
    option_c: Optional[str] = Field(None, max_length=500)
    option_d: Optional[str] = Field(None, max_length=500)
    correct_option: Optional[CorrectAnswerEnum] = None
    explanation: Optional[str] = Field(None, max_length=1000)
    hint: Optional[str] = Field(None, max_length=500)
    difficulty_level: Optional[DifficultyLevelEnum] = None
    tag_ids: Optional[List[int]] = None


class McqQuestionRead(McqQuestionBase):
    id: int
    user_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    tags: List[QuestionTagRead] = []

    class Config:
        from_attributes = True


# MCQ Quiz Schemas
class McqQuizBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    difficulty_level: DifficultyLevelEnum
    is_active: bool = True
    is_public: bool = False
    subject_id: Optional[int] = None
    community_id: Optional[int] = None


class McqQuizCreate(McqQuizBase):
    question_ids: Optional[List[int]] = []


class McqQuizUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    difficulty_level: Optional[DifficultyLevelEnum] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None
    subject_id: Optional[int] = None
    community_id: Optional[int] = None
    question_ids: Optional[List[int]] = None


class McqQuizRead(McqQuizBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    question_count: int = 0

    class Config:
        from_attributes = True


class McqQuizWithQuestions(McqQuizRead):
    questions: List[McqQuestionRead] = []


# Quiz Session Schemas
class QuizSessionBase(BaseModel):
    quiz_id: int


class QuizSessionCreate(QuizSessionBase):
    pass


class QuizSessionAnswer(BaseModel):
    question_id: int
    selected_option: CorrectAnswerEnum


class QuizSessionSubmit(BaseModel):
    answers: List[QuizSessionAnswer]


class QuizSessionRead(BaseModel):
    id: int
    user_id: int
    quiz_id: int
    quiz_title: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime]
    score: Optional[int]
    total_questions: int
    answers_json: Optional[Dict[str, Any]]
    time_taken_seconds: Optional[int]

    class Config:
        from_attributes = True


# AI MCQ Generation Schemas
class MCQGenerationOptions(BaseModel):
    A: str = Field(..., description="Option A")
    B: str = Field(..., description="Option B")
    C: str = Field(..., description="Option C")
    D: str = Field(..., description="Option D")


class MCQGenerationQuestion(BaseModel):
    question: str = Field(..., description="Question text")
    options: MCQGenerationOptions = Field(..., description="Answer options")
    correct_answer: CorrectAnswerEnum = Field(..., description="Correct answer")
    explanation: str = Field(..., description="Explanation")
    hint: str = Field(..., description="Hint")
    difficulty: DifficultyLevelEnum = Field(..., description="Difficulty")
    category: str = Field(..., description="Category")


class MCQGenerationSet(BaseModel):
    title: str = Field(..., description="Title")
    description: str = Field(..., description="Description")
    questions: List[MCQGenerationQuestion] = Field(..., description="Questions")
    tags: List[str] = Field(..., description="Tags")
    difficulty_level: DifficultyLevelEnum = Field(..., description="Difficulty")


class MCQGenerationResponse(BaseModel):
    mcq_set: MCQGenerationSet


class MCQGenerationRequest(BaseModel):
    physical_file_ids: List[int] = Field(..., min_items=1)
    num_questions: int = Field(default=30, ge=1, le=60)
    difficulty_level: Optional[DifficultyLevelEnum] = None
    custom_instructions: Optional[str] = None
    create_quiz: bool = Field(default=True, description="Whether to create a quiz from generated questions")
    quiz_title: Optional[str] = None
    quiz_description: Optional[str] = None
    community_id: Optional[int] = Field(None, description="Community ID to associate quiz with") 

def _convert_question_to_read(question: McqQuestion) -> McqQuestionRead:
    """Convert a question with its tag links to McqQuestionRead format."""
    question_dict = {
        "id": question.id,
        "question_text": question.question_text,
        "option_a": question.option_a,
        "option_b": question.option_b,
        "option_c": question.option_c,
        "option_d": question.option_d,
        "correct_option": question.correct_option,
        "explanation": question.explanation,
        "hint": question.hint,
        "difficulty_level": question.difficulty_level,
        "user_id": question.user_id,
        "created_at": question.created_at,
        "updated_at": question.updated_at,
        "tags": [QuestionTagRead.from_orm(link.tag) for link in question.tag_links] if hasattr(question, 'tag_links') else []
    }
    return McqQuestionRead(**question_dict)

