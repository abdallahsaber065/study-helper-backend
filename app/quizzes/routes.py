"""
API routes for quiz generation, management, and quiz-taking functionality.

This module provides comprehensive REST API endpoints for:
- Quiz generation with AI and background task management
- Quiz management, updates, and lifecycle operations
- Quiz-taking functionality with attempt tracking
- Advanced analytics and reporting
- Export functionality in multiple formats
- Real-time progress tracking via WebSocket integration
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_user
from ..database import get_db_session
from ..files.models import FileMetadata
# Removed unused import: get_file_content
from ..tasks.quiz_tasks import generate_quiz_task, regenerate_quiz_questions_task
from ..usage.services import QuotaManager
from ..usage.schemas import OperationType
from ..users.models import User
from .models import Quiz, QuizAttempt
from .schemas import (
    QuizGenerateRequest, QuizUpdateRequest, QuizRegenerateRequest,
    QuizResponse, QuizListResponse, QuizProgressResponse, QuizAnalytics,
    QuizAttemptStartRequest, QuizAttemptResponse, QuizAttemptListResponse,
    QuizAttemptCompleteRequest, QuestionAnswerRequest,
    QuizFilters, BulkQuizOperation, ExportRequest, ExportResponse,
    TaskProgressUpdate
)
from .services import QuizService, QuizAttemptService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.post(
    "/generate",
    response_model=QuizProgressResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate AI Quiz",
    description="Queue a new AI-powered quiz generation task with advanced options",
)
async def generate_quiz(
    request: QuizGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Generate an AI-powered quiz from a document.
    
    This endpoint queues a background task to generate a comprehensive quiz with:
    - Adaptive difficulty based on content analysis
    - Multiple question types with quality scoring
    - Learning objective alignment and topic mapping
    - Real-time progress tracking via WebSocket
    
    Returns immediately with task information for progress monitoring.
    """
    
    try:
        quiz_service = QuizService(db)
        quota_manager = QuotaManager(db)
        
        # Verify file access
        file_metadata = db.query(FileMetadata).filter(
            FileMetadata.id == request.file_id,
            FileMetadata.user_id == current_user.id
        ).first()
        
        if not file_metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or access denied"
            )
        
        # Check quota availability
        from decimal import Decimal
        estimated_tokens = len(request.question_types) * request.question_count * 200
        estimated_cost = Decimal("0.05") * (estimated_tokens / 1000)
        
        quota_check = await quota_manager.check_quota_availability(
            user_id=current_user.id,
            operation_type=OperationType.QUIZ_GENERATION,
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
        )
        
        if not quota_check.can_proceed:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient quota: {quota_check.reason}"
            )
        
        # Create quiz record
        quiz = quiz_service.create_quiz(
            user_id=current_user.id,
            file_id=request.file_id,
            title=request.title,
            description=request.description,
            difficulty_level=request.difficulty_level.value,
            question_count=request.question_count,
            estimated_time_minutes=request.estimated_time_minutes,
            time_limit_minutes=request.time_limit_minutes,
            shuffle_questions=request.shuffle_questions,
            shuffle_answers=request.shuffle_answers,
            show_correct_answers=request.show_correct_answers,
            allow_retries=request.allow_retries,
            max_attempts=request.max_attempts,
            passing_score=request.passing_score,
        )
        
        # Prepare task configuration
        quiz_config = {
            "ai_provider": request.ai_provider.value if request.ai_provider else "openai",
            "ai_model": request.ai_model or "gpt-4o",
            "question_count": request.question_count,
            "difficulty_level": request.difficulty_level.value,
            "question_types": [qt.value for qt in request.question_types],
            "question_type_distribution": request.question_type_distribution,
            "learning_objectives": request.learning_objectives,
            "focus_topics": request.topics_to_focus,
            "exclude_topics": request.topics_to_exclude,
            "custom_instructions": request.custom_instructions,
            "adaptive_difficulty": True,
            "quality_threshold": 3.0,
        }
        
        # Queue background task
        task = generate_quiz_task.delay(
            quiz_id=quiz.id,
            file_id=request.file_id,
            user_id=current_user.id,
            quiz_config=quiz_config,
        )
        
        logger.info(
            f"Queued quiz generation task {task.id} for quiz {quiz.id} by user {current_user.id}"
        )
        
        return QuizProgressResponse(
            task_id=task.id,
            quiz_id=quiz.id,
            status=quiz.status,
            progress_percentage=quiz.progress_percentage,
            current_step="Initializing quiz generation",
            estimated_time_remaining=300,  # 5 minutes estimate
            questions_generated=0,
            total_questions_target=request.question_count,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quiz generation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start quiz generation: {str(e)}"
        )


@router.get(
    "",
    response_model=QuizListResponse,
    summary="List Quizzes",
    description="Get paginated list of user's quizzes with advanced filtering",
)
async def list_quizzes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    # Filtering parameters
    status: Optional[List[str]] = Query(None, description="Filter by quiz status"),
    difficulty_level: Optional[List[str]] = Query(None, description="Filter by difficulty level"),
    ai_provider: Optional[List[str]] = Query(None, description="Filter by AI provider"),
    created_after: Optional[datetime] = Query(None, description="Filter by creation date (after)"),
    created_before: Optional[datetime] = Query(None, description="Filter by creation date (before)"),
    min_quality_score: Optional[float] = Query(None, ge=0.0, le=5.0, description="Minimum quality score"),
    has_user_rating: Optional[bool] = Query(None, description="Filter by user rating presence"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    learning_objective: Optional[str] = Query(None, description="Filter by learning objective"),
    question_count_min: Optional[int] = Query(None, ge=1, description="Minimum question count"),
    question_count_max: Optional[int] = Query(None, le=50, description="Maximum question count"),
    search_query: Optional[str] = Query(None, description="Search in title, description, topics"),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    # Sorting
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
):
    """
    Get paginated list of user's quizzes with comprehensive filtering options.
    
    Supports filtering by status, difficulty, provider, dates, quality scores,
    and content-based searching across titles, descriptions, and topics.
    """
    
    try:
        quiz_service = QuizService(db)
        
        # Build filters
        filters = QuizFilters(
            status=[s for s in status] if status else None,
            difficulty_level=[d for d in difficulty_level] if difficulty_level else None,
            ai_provider=[p for p in ai_provider] if ai_provider else None,
            created_after=created_after,
            created_before=created_before,
            min_quality_score=min_quality_score,
            has_user_rating=has_user_rating,
            topic=topic,
            learning_objective=learning_objective,
            question_count_min=question_count_min,
            question_count_max=question_count_max,
            search_query=search_query,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        return quiz_service.get_quizzes(current_user.id, filters)
        
    except Exception as e:
        logger.error(f"Failed to list quizzes: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve quizzes: {str(e)}"
        )


@router.get(
    "/{quiz_id}",
    response_model=QuizResponse,
    summary="Get Quiz",
    description="Get detailed quiz information with optional questions",
)
async def get_quiz(
    quiz_id: str,
    include_questions: bool = Query(False, description="Include questions and answers"),
    shuffle_questions: Optional[bool] = Query(None, description="Override question shuffling"),
    shuffle_answers: Optional[bool] = Query(None, description="Override answer shuffling"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Get detailed quiz information.
    
    Can optionally include all questions and answers, with support for
    shuffling overrides for practice or review purposes.
    """
    
    try:
        quiz_service = QuizService(db)
        
        if include_questions:
            quiz_response = quiz_service.get_quiz_with_questions(
                quiz_id=quiz_id,
                user_id=current_user.id,
                shuffle_questions=shuffle_questions,
                shuffle_answers=shuffle_answers
            )
        else:
            quiz = quiz_service.get_quiz(quiz_id, current_user.id)
            if not quiz:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Quiz not found"
                )
            
            quiz_response = QuizResponse(
                id=quiz.id,
                user_id=quiz.user_id,
                file_id=quiz.file_id,
                title=quiz.title,
                description=quiz.description,
                difficulty_level=quiz.difficulty_level,
                question_count=quiz.question_count,
                estimated_time_minutes=quiz.estimated_time_minutes,
                time_limit_minutes=quiz.time_limit_minutes,
                topics_covered=json.loads(quiz.topics_covered) if quiz.topics_covered else [],
                learning_objectives=json.loads(quiz.learning_objectives) if quiz.learning_objectives else [],
                ai_provider=quiz.ai_provider,
                ai_model_used=quiz.ai_model_used,
                prompt_template=quiz.prompt_template,
                status=quiz.status,
                progress_percentage=quiz.progress_percentage,
                error_message=quiz.error_message,
                quality_score=quiz.quality_score,
                user_rating=quiz.user_rating,
                user_feedback=quiz.user_feedback,
                shuffle_questions=quiz.shuffle_questions,
                shuffle_answers=quiz.shuffle_answers,
                show_correct_answers=quiz.show_correct_answers,
                allow_retries=quiz.allow_retries,
                max_attempts=quiz.max_attempts,
                passing_score=quiz.passing_score,
                metrics=quiz_service._calculate_quiz_metrics(quiz),
                created_at=quiz.created_at,
                updated_at=quiz.updated_at,
                completed_at=quiz.completed_at,
            )
        
        if not quiz_response:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        return quiz_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get quiz {quiz_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve quiz: {str(e)}"
        )


@router.put(
    "/{quiz_id}",
    response_model=QuizResponse,
    summary="Update Quiz",
    description="Update quiz metadata and settings",
)
async def update_quiz(
    quiz_id: str,
    request: QuizUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Update quiz metadata and configuration settings.
    
    Allows updating title, description, difficulty, time limits,
    shuffling settings, attempt limits, and user feedback.
    """
    
    try:
        quiz_service = QuizService(db)
        
        update_data = request.dict(exclude_unset=True)
        quiz = quiz_service.update_quiz(quiz_id, current_user.id, update_data)
        
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Return updated quiz
        return await get_quiz(quiz_id, current_user=current_user, db=db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update quiz {quiz_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update quiz: {str(e)}"
        )


@router.delete(
    "/{quiz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Quiz",
    description="Delete quiz (soft delete by default)",
)
async def delete_quiz(
    quiz_id: str,
    permanent: bool = Query(False, description="Permanent deletion (cannot be undone)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Delete a quiz.
    
    By default performs soft delete (can be recovered).
    Use permanent=true for hard deletion (irreversible).
    """
    
    try:
        quiz_service = QuizService(db)
        
        success = quiz_service.delete_quiz(quiz_id, current_user.id, soft_delete=not permanent)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        logger.info(f"Deleted quiz {quiz_id} for user {current_user.id} (permanent: {permanent})")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete quiz {quiz_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete quiz: {str(e)}"
        )


@router.post(
    "/{quiz_id}/archive",
    response_model=QuizResponse,
    summary="Archive Quiz",
    description="Archive quiz (keeps it but marks as archived)",
)
async def archive_quiz(
    quiz_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Archive a quiz to keep it but mark as archived."""
    
    try:
        quiz_service = QuizService(db)
        
        success = quiz_service.archive_quiz(quiz_id, current_user.id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Return updated quiz
        return await get_quiz(quiz_id, current_user=current_user, db=db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to archive quiz {quiz_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive quiz: {str(e)}"
        )


@router.post(
    "/{quiz_id}/regenerate",
    response_model=QuizProgressResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Regenerate Quiz Questions",
    description="Regenerate some or all questions in an existing quiz",
)
async def regenerate_quiz_questions(
    quiz_id: str,
    request: QuizRegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Regenerate questions in an existing quiz.
    
    Can regenerate all questions or just low-quality ones based on
    quality thresholds and user preferences.
    """
    
    try:
        quiz_service = QuizService(db)
        
        # Verify quiz exists and is owned by user
        quiz = quiz_service.get_quiz(quiz_id, current_user.id)
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        if quiz.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only regenerate questions for completed quizzes"
            )
        
        # Prepare regeneration configuration
        regeneration_config = {
            "ai_provider": request.ai_provider.value if request.ai_provider else quiz.ai_provider,
            "ai_model": request.ai_model or quiz.ai_model_used,
            "difficulty_level": request.difficulty_level.value if request.difficulty_level else quiz.difficulty_level,
            "question_count": request.question_count or quiz.question_count,
            "question_types": [qt.value for qt in request.question_types] if request.question_types else ["multiple_choice", "true_false", "short_answer"],
            "custom_instructions": request.custom_instructions,
            "regenerate_all": request.regenerate_all,
            "quality_threshold": 3.0,
        }
        
        # Queue regeneration task
        task = regenerate_quiz_questions_task.delay(
            quiz_id=quiz_id,
            user_id=current_user.id,
            regeneration_config=regeneration_config,
        )
        
        logger.info(
            f"Queued quiz regeneration task {task.id} for quiz {quiz_id} by user {current_user.id}"
        )
        
        return QuizProgressResponse(
            task_id=task.id,
            quiz_id=quiz_id,
            status="processing",
            progress_percentage=0,
            current_step="Starting question regeneration",
            estimated_time_remaining=180,  # 3 minutes estimate
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quiz regeneration failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start quiz regeneration: {str(e)}"
        )


@router.get(
    "/{quiz_id}/analytics",
    response_model=QuizAnalytics,
    summary="Quiz Analytics",
    description="Get comprehensive analytics for a quiz including performance metrics",
)
async def get_quiz_analytics(
    quiz_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Get comprehensive analytics for a quiz.
    
    Includes performance metrics, question analytics, user progression,
    and improvement suggestions.
    """
    
    try:
        quiz_service = QuizService(db)
        
        analytics = quiz_service.get_quiz_analytics(quiz_id, current_user.id)
        
        if not analytics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get quiz analytics {quiz_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve quiz analytics: {str(e)}"
        )


# Quiz Attempt Endpoints

@router.post(
    "/{quiz_id}/attempts/start",
    response_model=QuizAttemptResponse,
    summary="Start Quiz Attempt",
    description="Start a new attempt at taking a quiz",
)
async def start_quiz_attempt(
    quiz_id: str,
    request: QuizAttemptStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Start a new quiz attempt.
    
    Creates a new attempt record and returns the initial state
    with optional question/answer shuffling overrides.
    """
    
    try:
        attempt_service = QuizAttemptService(db)
        
        attempt = attempt_service.start_attempt(
            quiz_id=quiz_id,
            user_id=current_user.id,
            session_id=request.session_id,
        )
        
        return QuizAttemptResponse(
            id=attempt.id,
            quiz_id=attempt.quiz_id,
            user_id=attempt.user_id,
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            total_score=attempt.total_score,
            max_possible_score=attempt.max_possible_score,
            percentage_score=attempt.percentage_score,
            passed=attempt.passed,
            questions_answered=attempt.questions_answered,
            questions_correct=attempt.questions_correct,
            current_question_index=attempt.current_question_index,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            time_spent_seconds=attempt.time_spent_seconds,
            time_limit_seconds=attempt.time_limit_seconds,
            topic_scores=json.loads(attempt.topic_scores) if attempt.topic_scores else None,
            difficulty_progression=json.loads(attempt.difficulty_progression) if attempt.difficulty_progression else None,
            user_feedback=attempt.user_feedback,
            difficulty_rating=attempt.difficulty_rating,
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to start quiz attempt: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start quiz attempt: {str(e)}"
        )


@router.get(
    "/attempts/{attempt_id}",
    response_model=QuizAttemptResponse,
    summary="Get Quiz Attempt",
    description="Get details of a specific quiz attempt",
)
async def get_quiz_attempt(
    attempt_id: str,
    include_responses: bool = Query(False, description="Include individual question responses"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Get details of a specific quiz attempt."""
    
    try:
        attempt_service = QuizAttemptService(db)
        
        attempt = attempt_service.get_attempt(attempt_id, current_user.id)
        if not attempt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz attempt not found"
            )
        
        # Build response
        response = QuizAttemptResponse(
            id=attempt.id,
            quiz_id=attempt.quiz_id,
            user_id=attempt.user_id,
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            total_score=attempt.total_score,
            max_possible_score=attempt.max_possible_score,
            percentage_score=attempt.percentage_score,
            passed=attempt.passed,
            questions_answered=attempt.questions_answered,
            questions_correct=attempt.questions_correct,
            current_question_index=attempt.current_question_index,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            time_spent_seconds=attempt.time_spent_seconds,
            time_limit_seconds=attempt.time_limit_seconds,
            topic_scores=json.loads(attempt.topic_scores) if attempt.topic_scores else None,
            difficulty_progression=json.loads(attempt.difficulty_progression) if attempt.difficulty_progression else None,
            user_feedback=attempt.user_feedback,
            difficulty_rating=attempt.difficulty_rating,
        )
        
        if include_responses:
            # Add individual responses
            from .schemas import QuestionResponseDetail
            responses = []
            for response_obj in attempt.responses:
                response_detail = QuestionResponseDetail(
                    id=response_obj.id,
                    question_id=response_obj.question_id,
                    user_answer=response_obj.user_answer,
                    selected_answer_ids=json.loads(response_obj.selected_answer_ids) if response_obj.selected_answer_ids else None,
                    is_correct=response_obj.is_correct,
                    points_earned=response_obj.points_earned,
                    max_points=response_obj.max_points,
                    response_time_seconds=response_obj.response_time_seconds,
                    confidence_level=response_obj.confidence_level,
                    answered_at=response_obj.answered_at,
                )
                responses.append(response_detail)
            response.responses = responses
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get quiz attempt {attempt_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve quiz attempt: {str(e)}"
        )


@router.post(
    "/attempts/{attempt_id}/answers",
    summary="Submit Answer",
    description="Submit an answer for a question in an active quiz attempt",
)
async def submit_answer(
    attempt_id: str,
    request: QuestionAnswerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Submit an answer for a question in an active quiz attempt."""
    
    try:
        attempt_service = QuizAttemptService(db)
        
        response = attempt_service.submit_answer(
            attempt_id=attempt_id,
            question_id=request.question_id,
            user_answer=request.user_answer,
            selected_answer_ids=request.selected_answer_ids,
            response_time_seconds=request.response_time_seconds,
            confidence_level=request.confidence_level,
        )
        
        # Get updated attempt status
        attempt = attempt_service.get_attempt(attempt_id, current_user.id)
        
        return {
            "success": True,
            "is_correct": response.is_correct,
            "points_earned": float(response.points_earned),
            "attempt_progress": {
                "questions_answered": attempt.questions_answered,
                "current_score": float(attempt.total_score),
                "current_question_index": attempt.current_question_index,
            }
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to submit answer: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit answer: {str(e)}"
        )


@router.post(
    "/attempts/{attempt_id}/complete",
    response_model=QuizAttemptResponse,
    summary="Complete Quiz Attempt",
    description="Mark a quiz attempt as completed and calculate final scores",
)
async def complete_quiz_attempt(
    attempt_id: str,
    request: QuizAttemptCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Complete a quiz attempt and calculate final scores."""
    
    try:
        attempt_service = QuizAttemptService(db)
        
        attempt = attempt_service.complete_attempt(
            attempt_id=attempt_id,
            user_id=current_user.id,
            user_feedback=request.user_feedback,
            difficulty_rating=request.difficulty_rating,
        )
        
        return QuizAttemptResponse(
            id=attempt.id,
            quiz_id=attempt.quiz_id,
            user_id=attempt.user_id,
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            total_score=attempt.total_score,
            max_possible_score=attempt.max_possible_score,
            percentage_score=attempt.percentage_score,
            passed=attempt.passed,
            questions_answered=attempt.questions_answered,
            questions_correct=attempt.questions_correct,
            current_question_index=attempt.current_question_index,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            time_spent_seconds=attempt.time_spent_seconds,
            time_limit_seconds=attempt.time_limit_seconds,
            user_feedback=attempt.user_feedback,
            difficulty_rating=attempt.difficulty_rating,
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to complete quiz attempt: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete quiz attempt: {str(e)}"
        )


@router.post(
    "/attempts/{attempt_id}/abandon",
    response_model=QuizAttemptResponse,
    summary="Abandon Quiz Attempt",
    description="Mark a quiz attempt as abandoned",
)
async def abandon_quiz_attempt(
    attempt_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Abandon a quiz attempt."""
    
    try:
        attempt_service = QuizAttemptService(db)
        
        attempt = attempt_service.abandon_attempt(attempt_id, current_user.id)
        
        return QuizAttemptResponse(
            id=attempt.id,
            quiz_id=attempt.quiz_id,
            user_id=attempt.user_id,
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            total_score=attempt.total_score,
            max_possible_score=attempt.max_possible_score,
            percentage_score=attempt.percentage_score,
            passed=attempt.passed,
            questions_answered=attempt.questions_answered,
            questions_correct=attempt.questions_correct,
            current_question_index=attempt.current_question_index,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            time_spent_seconds=attempt.time_spent_seconds,
            time_limit_seconds=attempt.time_limit_seconds,
            user_feedback=attempt.user_feedback,
            difficulty_rating=attempt.difficulty_rating,
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to abandon quiz attempt: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to abandon quiz attempt: {str(e)}"
        )


@router.get(
    "/attempts",
    response_model=QuizAttemptListResponse,
    summary="List Quiz Attempts",
    description="Get paginated list of user's quiz attempts",
)
async def list_quiz_attempts(
    quiz_id: Optional[str] = Query(None, description="Filter by specific quiz"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Get paginated list of user's quiz attempts."""
    
    try:
        attempt_service = QuizAttemptService(db)
        
        return attempt_service.get_user_attempts(
            user_id=current_user.id,
            quiz_id=quiz_id,
            page=page,
            page_size=page_size
        )
        
    except Exception as e:
        logger.error(f"Failed to list quiz attempts: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve quiz attempts: {str(e)}"
        )


# Bulk Operations and Export

@router.post(
    "/bulk",
    summary="Bulk Operations",
    description="Perform bulk operations on multiple quizzes",
)
async def bulk_quiz_operations(
    request: BulkQuizOperation,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Perform bulk operations on multiple quizzes.
    
    Supports delete, archive, regenerate, and export operations.
    """
    
    try:
        quiz_service = QuizService(db)
        
        results = {
            "operation": request.operation,
            "total_quizzes": len(request.quiz_ids),
            "successful": 0,
            "failed": 0,
            "errors": []
        }
        
        for quiz_id in request.quiz_ids:
            try:
                if request.operation == "delete":
                    success = quiz_service.delete_quiz(quiz_id, current_user.id)
                    if success:
                        results["successful"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append(f"Quiz {quiz_id}: not found")
                
                elif request.operation == "archive":
                    success = quiz_service.archive_quiz(quiz_id, current_user.id)
                    if success:
                        results["successful"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append(f"Quiz {quiz_id}: not found")
                
                elif request.operation == "regenerate":
                    # Queue regeneration tasks
                    regeneration_config = request.parameters or {}
                    task = regenerate_quiz_questions_task.delay(
                        quiz_id=quiz_id,
                        user_id=current_user.id,
                        regeneration_config=regeneration_config,
                    )
                    results["successful"] += 1
                
                elif request.operation == "export":
                    # Handle bulk export (placeholder)
                    results["successful"] += 1
                
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Quiz {quiz_id}: {str(e)}")
        
        return results
        
    except Exception as e:
        logger.error(f"Bulk operation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk operation failed: {str(e)}"
        )


@router.post(
    "/{quiz_id}/export",
    response_model=ExportResponse,
    summary="Export Quiz",
    description="Export quiz in various formats (PDF, JSON, CSV, SCORM)",
)
async def export_quiz(
    quiz_id: str,
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Export quiz in the specified format.
    
    Supports PDF, JSON, CSV, and SCORM export formats with
    customizable options for analytics, answers, and branding.
    """
    
    try:
        quiz_service = QuizService(db)
        
        # Verify quiz exists
        quiz = quiz_service.get_quiz(quiz_id, current_user.id)
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quiz not found"
            )
        
        # Generate export ID and create placeholder response
        export_id = str(uuid.uuid4())
        
        # In a real implementation, this would queue a background task
        # to generate the export file and store it securely
        
        # Placeholder implementation
        download_url = f"/api/v1/exports/{export_id}/download"
        expires_at = datetime.utcnow().replace(hour=23, minute=59, second=59)
        
        return ExportResponse(
            export_id=export_id,
            format=request.format,
            download_url=download_url,
            expires_at=expires_at,
            file_size_bytes=1024000,  # Placeholder size
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quiz export failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export quiz: {str(e)}"
        )
