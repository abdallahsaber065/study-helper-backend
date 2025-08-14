"""
Celery tasks for AI-powered quiz generation with comprehensive progress tracking.
"""

import asyncio
import json
import logging
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from celery import current_task
from sqlalchemy.orm import Session

from .celery_app import celery_app, celery_tasks_settings
from ..database import get_sync_db_session
from ..files.models import FileMetadata
from ..files.utils import get_file_content
from ..quizzes.models import Quiz, Question, Answer
from ..services.ai import AIProviderFactory, AIProviderType
from ..services.ai.errors import AIProviderError
from ..services.ai.quiz_generator import AIQuizGenerator, QuizGenerationRequest, QuizGenerationError
from ..usage.services import UsageTracker, QuotaManager
from ..usage.schemas import UsageRecordCreate, OperationType, UsageStatus
from ..websocket.manager import websocket_manager
from ..config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.quiz_tasks.generate_quiz_task",
    max_retries=celery_tasks_settings.MAX_RETRIES_API_ERROR,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
)
def generate_quiz_task(
    self,
    quiz_id: str,
    file_id: str,
    user_id: int,
    quiz_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate AI-powered quiz for a document.
    
    Args:
        quiz_id: ID of the quiz record
        file_id: ID of the file to generate quiz from
        user_id: ID of the user requesting the quiz
        quiz_config: Configuration for quiz generation
        
    Returns:
        Dict containing task result and metadata
    """

    task_id = self.request.id or str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    logger.info(
        "Starting quiz generation task",
        extra={
            "task_id": task_id,
            "quiz_id": quiz_id,
            "file_id": file_id,
            "user_id": user_id,
            "correlation_id": correlation_id,
        }
    )

    start_time = time.time()

    try:
        # Get database session
        with get_sync_db_session() as db_session:
            # Update task progress
            _update_task_progress(
                task_id=task_id,
                quiz_id=quiz_id,
                progress=5,
                step="Initializing quiz generation",
                db_session=db_session,
            )

            # Get quiz and file records
            quiz = db_session.query(Quiz).filter(Quiz.id == quiz_id).first()
            if not quiz:
                raise ValueError(f"Quiz not found: {quiz_id}")

            file_metadata = db_session.query(FileMetadata).filter(FileMetadata.id == file_id).first()
            if not file_metadata:
                raise ValueError(f"File not found: {file_id}")

            # Mark quiz as processing
            quiz.mark_as_processing(task_id, correlation_id)
            db_session.commit()

            _update_task_progress(
                task_id=task_id,
                quiz_id=quiz_id,
                progress=10,
                step="Reading source document",
                db_session=db_session,
            )

            # Read file content
            try:
                file_content = get_file_content(file_metadata.file_path)
                if not file_content:
                    raise ValueError("File content is empty or could not be read")
            except Exception as e:
                raise ValueError(f"Failed to read file content: {str(e)}")

            _update_task_progress(
                task_id=task_id,
                quiz_id=quiz_id,
                progress=20,
                step="Setting up AI provider",
                db_session=db_session,
            )

            # Setup AI provider
            ai_provider_type = AIProviderType(quiz_config.get("ai_provider", settings.AI_DEFAULT_PROVIDER))
            ai_provider = AIProviderFactory.create_provider(ai_provider_type)

            # Initialize quiz generator
            quiz_generator = AIQuizGenerator(ai_provider)

            _update_task_progress(
                task_id=task_id,
                quiz_id=quiz_id,
                progress=25,
                step="Analyzing content complexity",
                db_session=db_session,
            )

            # Create quiz generation request
            generation_request = QuizGenerationRequest(
                content_text=file_content,
                question_count=quiz_config.get("question_count", quiz.question_count),
                difficulty_level=quiz_config.get("difficulty_level", quiz.difficulty_level),
                question_types=quiz_config.get("question_types", ["multiple_choice", "true_false", "short_answer"]),
                learning_objectives=quiz_config.get("learning_objectives"),
                focus_topics=quiz_config.get("focus_topics"),
                exclude_topics=quiz_config.get("exclude_topics"),
                custom_instructions=quiz_config.get("custom_instructions"),
                adaptive_difficulty=quiz_config.get("adaptive_difficulty", True),
                quality_threshold=quiz_config.get("quality_threshold", 3.0),
            )

            _update_task_progress(
                task_id=task_id,
                quiz_id=quiz_id,
                progress=35,
                step="Generating quiz questions",
                db_session=db_session,
            )

            # Check user quotas before processing
            usage_tracker = UsageTracker(db_session)
            quota_manager = QuotaManager(db_session)
            
            # Estimate token usage (rough approximation)
            estimated_input_tokens = len(file_content.split()) * 1.3  # Rough token estimation
            estimated_output_tokens = generation_request.question_count * 200  # Estimate per question

            if not quota_manager.check_quota(
                user_id=user_id,
                operation_type=OperationType.QUIZ_GENERATION,
                estimated_tokens=int(estimated_input_tokens + estimated_output_tokens)
            ):
                raise QuizGenerationError("User quota exceeded for quiz generation")

            # Record usage start
            usage_record = usage_tracker.create_usage_record(
                UsageRecordCreate(
                    user_id=user_id,
                    operation_type=OperationType.QUIZ_GENERATION,
                    provider=ai_provider_type.value,
                    model=quiz_config.get("ai_model", settings.AI_DEFAULT_MODEL),
                    estimated_input_tokens=int(estimated_input_tokens),
                    estimated_output_tokens=int(estimated_output_tokens),
                    correlation_id=correlation_id,
                    resource_id=quiz_id,
                )
            )

            try:
                # Generate quiz with progress tracking
                async def progress_callback(progress: int, step: str, questions_generated: int = 0):
                    """Callback for quiz generation progress updates."""
                    actual_progress = 35 + int((progress / 100) * 50)  # Map to 35-85% range
                    _update_task_progress(
                        task_id=task_id,
                        quiz_id=quiz_id,
                        progress=actual_progress,
                        step=step,
                        questions_generated=questions_generated,
                        db_session=db_session,
                    )
                # Generate the quiz
                quiz_response = quiz_generator.generate_quiz(generation_request)

                _update_task_progress(
                    task_id=task_id,
                    quiz_id=quiz_id,
                    progress=85,
                    step="Saving generated questions",
                    db_session=db_session,
                )

                # Save generated questions to database
                saved_questions = []
                for i, generated_question in enumerate(quiz_response.questions):
                    question = Question(
                        quiz_id=quiz_id,
                        question_text=generated_question.question_text,
                        question_type=generated_question.question_type,
                        order_index=i,
                        difficulty_level=generated_question.difficulty_level,
                        points=Decimal(str(generated_question.points)),
                        topic=generated_question.topic,
                        learning_objective=generated_question.learning_objective,
                        cognitive_level=generated_question.cognitive_level,
                        context=generated_question.context,
                        source_reference=generated_question.source_reference,
                        explanation=generated_question.explanation,
                        estimated_time_seconds=generated_question.estimated_time_seconds,
                        quality_score=Decimal(str(generated_question.quality.overall_score)) if generated_question.quality else None,
                        ai_confidence_score=Decimal(str(generated_question.confidence_score)) if generated_question.confidence_score else None,
                    )
                    
                    db_session.add(question)
                    db_session.flush()  # Get the question ID
                    
                    # Add answers
                    answers = []
                    
                    # Add correct answers
                    for j, correct_answer in enumerate(generated_question.correct_answers):
                        answer = Answer(
                            question_id=question.id,
                            answer_text=correct_answer,
                            order_index=j,
                            is_correct=True,
                            points=question.points,
                            explanation=generated_question.explanation,
                        )
                        answers.append(answer)
                        db_session.add(answer)
                    
                    # Add incorrect options (for multiple choice)
                    if generated_question.question_type == "multiple_choice":
                        for j, incorrect_option in enumerate(generated_question.incorrect_options):
                            answer = Answer(
                                question_id=question.id,
                                answer_text=incorrect_option,
                                order_index=len(answers) + j,
                                is_correct=False,
                                points=Decimal("0.0"),
                            )
                            db_session.add(answer)
                    
                    saved_questions.append(question)

                _update_task_progress(
                    task_id=task_id,
                    quiz_id=quiz_id,
                    progress=95,
                    step="Finalizing quiz metadata",
                    db_session=db_session,
                )

                # Update quiz with generation results
                processing_time_ms = int((time.time() - start_time) * 1000)
                
                # Extract AI usage metrics if available
                ai_metrics = quiz_response.generation_metadata
                
                quiz.ai_provider = ai_provider_type.value
                quiz.ai_model_used = quiz_config.get("ai_model", settings.AI_DEFAULT_MODEL)
                quiz.prompt_template = "quiz_generation_v1"
                
                # Update content analysis results
                if quiz_response.content_analysis:
                    quiz.topics_covered = json.dumps(quiz_response.content_analysis.main_topics)
                    quiz.learning_objectives = json.dumps(quiz_response.content_analysis.learning_objectives)
                    quiz.content_complexity_score = Decimal(str(quiz_response.content_analysis.technical_depth))
                
                # Update quality metrics
                quiz.quality_score = Decimal(str(quiz_response.quality_summary.get("average_quality", 0.0)))
                quiz.question_quality_avg = Decimal(str(quiz_response.quality_summary.get("average_quality", 0.0)))
                quiz.ai_confidence_score = Decimal("0.85")  # Default confidence
                
                # Update usage tracking (rough estimates - would be more accurate with actual API response)
                estimated_tokens = len(file_content.split()) + (len(quiz_response.questions) * 150)
                quiz.input_tokens = int(len(file_content.split()) * 1.3)
                quiz.output_tokens = len(quiz_response.questions) * 150
                quiz.total_tokens = quiz.input_tokens + quiz.output_tokens
                quiz.generation_cost = Decimal("0.01") * (quiz.total_tokens / 1000)  # Rough cost estimate
                
                # Mark as completed
                quiz.mark_as_completed(processing_time_ms)
                
                # Update usage record with actual results
                usage_tracker.update_usage_record(
                    usage_record.id,
                    actual_input_tokens=quiz.input_tokens,
                    actual_output_tokens=quiz.output_tokens,
                    actual_cost=quiz.generation_cost,
                    status=UsageStatus.COMPLETED,
                    response_data={
                        "questions_generated": len(saved_questions),
                        "average_quality": float(quiz.quality_score),
                        "content_complexity": quiz_response.content_analysis.complexity_level.value if quiz_response.content_analysis else "unknown",
                    }
                )
                
                db_session.commit()

                _update_task_progress(
                    task_id=task_id,
                    quiz_id=quiz_id,
                    progress=100,
                    step="Quiz generation completed",
                    questions_generated=len(saved_questions),
                    db_session=db_session,
                )

                logger.info(
                    "Quiz generation completed successfully",
                    extra={
                        "task_id": task_id,
                        "quiz_id": quiz_id,
                        "questions_generated": len(saved_questions),
                        "processing_time_ms": processing_time_ms,
                        "quality_score": float(quiz.quality_score),
                    }
                )

                return {
                    "status": "completed",
                    "quiz_id": quiz_id,
                    "questions_generated": len(saved_questions),
                    "processing_time_ms": processing_time_ms,
                    "quality_score": float(quiz.quality_score),
                    "recommendations": quiz_response.recommendations,
                }

            except Exception as e:
                # Update usage record as failed
                usage_tracker.update_usage_record(
                    usage_record.id,
                    status=UsageStatus.FAILED,
                    error_details={"error": str(e), "error_type": type(e).__name__}
                )
                raise e

    except Exception as e:
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        logger.error(
            "Quiz generation failed",
            extra={
                "task_id": task_id,
                "quiz_id": quiz_id,
                "error": str(e),
                "processing_time_ms": processing_time_ms,
            },
            exc_info=True
        )

        # Update quiz as failed
        try:
            with get_sync_db_session() as db_session:
                quiz = db_session.query(Quiz).filter(Quiz.id == quiz_id).first()
                if quiz:
                    quiz.mark_as_failed(str(e))
                    db_session.commit()
                    
                    # Send failure notification via WebSocket
                    _send_websocket_update(
                        user_id=user_id,
                        task_id=task_id,
                        quiz_id=quiz_id,
                        status="failed",
                        progress=0,
                        error_message=str(e)
                    )
        except Exception as db_error:
            logger.error(
                "Failed to update quiz status after error",
                extra={"quiz_id": quiz_id, "db_error": str(db_error)}
            )

        # Determine if we should retry
        if isinstance(e, (AIProviderError, QuizGenerationError)):
            error_type = getattr(e, 'error_type', 'unknown')
            if error_type in ['rate_limit_error', 'timeout_error', 'network_error']:
                logger.info(f"Retrying quiz generation due to {error_type}")
                raise self.retry(countdown=60, max_retries=3)

        raise e


@celery_app.task(
    bind=True,
    name="app.tasks.quiz_tasks.regenerate_quiz_questions_task",
    max_retries=celery_tasks_settings.MAX_RETRIES_API_ERROR,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
)
def regenerate_quiz_questions_task(
    self,
    quiz_id: str,
    user_id: int,
    regeneration_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Regenerate specific questions in an existing quiz.
    
    Args:
        quiz_id: ID of the quiz to regenerate questions for
        user_id: ID of the user requesting regeneration
        regeneration_config: Configuration for regeneration
        
    Returns:
        Dict containing task result and metadata
    """

    task_id = self.request.id or str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    logger.info(
        "Starting quiz question regeneration task",
        extra={
            "task_id": task_id,
            "quiz_id": quiz_id,
            "user_id": user_id,
            "correlation_id": correlation_id,
        }
    )

    start_time = time.time()

    try:
        with get_sync_db_session() as db_session:
            # Get quiz record
            quiz = db_session.query(Quiz).filter(Quiz.id == quiz_id).first()
            if not quiz:
                raise ValueError(f"Quiz not found: {quiz_id}")

            # Get file content for regeneration
            file_metadata = db_session.query(FileMetadata).filter(FileMetadata.id == quiz.file_id).first()
            if not file_metadata:
                raise ValueError(f"Original file not found for quiz: {quiz_id}")

            file_content = get_file_content(file_metadata.file_path)
            
            # Setup AI provider
            ai_provider_type = AIProviderType(regeneration_config.get("ai_provider", quiz.ai_provider))
            ai_provider = AIProviderFactory.create_provider(ai_provider_type)
            quiz_generator = AIQuizGenerator(ai_provider)

            regenerate_all = regeneration_config.get("regenerate_all", False)
            
            if regenerate_all:
                # Delete existing questions
                db_session.query(Question).filter(Question.quiz_id == quiz_id).delete()
                question_count = regeneration_config.get("question_count", quiz.question_count)
            else:
                # Regenerate only low-quality questions
                low_quality_questions = db_session.query(Question).filter(
                    Question.quiz_id == quiz_id,
                    Question.quality_score < 3.0
                ).all()
                
                for question in low_quality_questions:
                    db_session.delete(question)
                
                question_count = len(low_quality_questions)

            if question_count == 0:
                return {
                    "status": "completed",
                    "quiz_id": quiz_id,
                    "questions_regenerated": 0,
                    "message": "No questions needed regeneration"
                }

            # Create regeneration request
            generation_request = QuizGenerationRequest(
                content_text=file_content,
                question_count=question_count,
                difficulty_level=regeneration_config.get("difficulty_level", quiz.difficulty_level),
                question_types=regeneration_config.get("question_types", ["multiple_choice", "true_false", "short_answer"]),
                custom_instructions=regeneration_config.get("custom_instructions"),
                quality_threshold=regeneration_config.get("quality_threshold", 3.5),
            )
            # Generate new questions
            quiz_response = quiz_generator.generate_quiz(generation_request)

            # Save regenerated questions
            for i, generated_question in enumerate(quiz_response.questions):
                question = Question(
                    quiz_id=quiz_id,
                    question_text=generated_question.question_text,
                    question_type=generated_question.question_type,
                    order_index=i,
                    difficulty_level=generated_question.difficulty_level,
                    points=Decimal(str(generated_question.points)),
                    topic=generated_question.topic,
                    learning_objective=generated_question.learning_objective,
                    cognitive_level=generated_question.cognitive_level,
                    context=generated_question.context,
                    explanation=generated_question.explanation,
                    quality_score=Decimal(str(generated_question.quality.overall_score)) if generated_question.quality else None,
                    ai_confidence_score=Decimal(str(generated_question.confidence_score)) if generated_question.confidence_score else None,
                )
                
                db_session.add(question)
                db_session.flush()
                
                # Add answers
                for j, correct_answer in enumerate(generated_question.correct_answers):
                    answer = Answer(
                        question_id=question.id,
                        answer_text=correct_answer,
                        order_index=j,
                        is_correct=True,
                        points=question.points,
                        explanation=generated_question.explanation,
                    )
                    db_session.add(answer)
                
                if generated_question.question_type == "multiple_choice":
                    for j, incorrect_option in enumerate(generated_question.incorrect_options):
                        answer = Answer(
                            question_id=question.id,
                            answer_text=incorrect_option,
                            order_index=len(generated_question.correct_answers) + j,
                            is_correct=False,
                            points=Decimal("0.0"),
                        )
                        db_session.add(answer)

            # Update quiz metadata
            processing_time_ms = int((time.time() - start_time) * 1000)
            quiz.question_quality_avg = Decimal(str(quiz_response.quality_summary.get("average_quality", 0.0)))
            quiz.updated_at = time.time()
            
            db_session.commit()

            logger.info(
                "Quiz regeneration completed successfully",
                extra={
                    "task_id": task_id,
                    "quiz_id": quiz_id,
                    "questions_regenerated": len(quiz_response.questions),
                    "processing_time_ms": processing_time_ms,
                }
            )

            return {
                "status": "completed",
                "quiz_id": quiz_id,
                "questions_regenerated": len(quiz_response.questions),
                "processing_time_ms": processing_time_ms,
                "new_quality_score": float(quiz.question_quality_avg),
            }

    except Exception as e:
        logger.error(
            "Quiz regeneration failed",
            extra={
                "task_id": task_id,
                "quiz_id": quiz_id,
                "error": str(e),
            },
            exc_info=True
        )
        raise e


def _update_task_progress(
    task_id: str,
    quiz_id: str,
    progress: int,
    step: str,
    db_session: Session,
    questions_generated: int = 0,
) -> None:
    """Update task progress in database and via WebSocket."""
    
    try:
        # Update quiz progress
        quiz = db_session.query(Quiz).filter(Quiz.id == quiz_id).first()
        if quiz:
            quiz.update_progress(progress)
            db_session.commit()

        # Send WebSocket update
        _send_websocket_update(
            user_id=quiz.user_id if quiz else None,
            task_id=task_id,
            quiz_id=quiz_id,
            status="processing",
            progress=progress,
            current_step=step,
            questions_generated=questions_generated,
        )

        logger.debug(
            "Task progress updated",
            extra={
                "task_id": task_id,
                "quiz_id": quiz_id,
                "progress": progress,
                "step": step,
                "questions_generated": questions_generated,
            }
        )

    except Exception as e:
        logger.warning(
            "Failed to update task progress",
            extra={
                "task_id": task_id,
                "quiz_id": quiz_id,
                "error": str(e),
            }
        )


def _send_websocket_update(
    user_id: Optional[int],
    task_id: str,
    quiz_id: str,
    status: str,
    progress: int,
    current_step: Optional[str] = None,
    questions_generated: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """Send progress update via WebSocket."""
    
    if not user_id:
        return

    try:
        update_data = {
            "status": status,
            "progress": progress,
            "current_step": current_step,
            "questions_generated": questions_generated,
        }
        
        if error_message:
            update_data["error_message"] = error_message

        # Send quiz progress update using asyncio.run for sync context
        async def send_update():
            await websocket_manager.send_quiz_progress_update(
                task_id=task_id,
                quiz_id=quiz_id,
                progress_update=update_data
            )
        
        # Run the async function in a new event loop
        try:
            asyncio.run(send_update())
            
            # Also send completion notification if quiz is completed
            if progress >= 100:
                _send_quiz_completion_notification(user_id, quiz_id, status == "completed")
                
        except Exception as async_error:
            logger.warning(
                "Failed to send WebSocket update via async",
                extra={
                    "user_id": user_id,
                    "task_id": task_id,
                    "async_error": str(async_error),
                }
            )
        
    except Exception as e:
        logger.warning(
            "Failed to send WebSocket update",
            extra={
                "user_id": user_id,
                "task_id": task_id,
                "error": str(e),
            }
        )


def _send_quiz_completion_notification(user_id: int, quiz_id: str, success: bool) -> None:
    """Send quiz generation completion notification to user."""
    try:
        from ..notifications.services import notification_service
        from ..notifications.models import NotificationType, NotificationPriority, DeliveryChannel
        from ..notifications.schemas import NotificationCreate
        
        # Create appropriate notification
        if success:
            notification_data = NotificationCreate(
                type=NotificationType.QUIZ_GENERATED,
                priority=NotificationPriority.NORMAL,
                title="Quiz Generated Successfully",
                message="Your quiz has been generated and is ready for use.",
                data={
                    "quiz_id": quiz_id,
                    "action": "view_quiz"
                },
                action_url=f"/quizzes/{quiz_id}",
                action_text="View Quiz",
                channels=[DeliveryChannel.IN_APP, DeliveryChannel.PUSH],
                source_id=quiz_id,
                source_type="quiz"
            )
        else:
            notification_data = NotificationCreate(
                type=NotificationType.QUIZ_FAILED,
                priority=NotificationPriority.HIGH,
                title="Quiz Generation Failed",
                message="We encountered an error while generating your quiz. Please try again.",
                data={
                    "quiz_id": quiz_id,
                    "action": "retry_quiz"
                },
                action_url=f"/quizzes/{quiz_id}/retry",
                action_text="Try Again",
                channels=[DeliveryChannel.IN_APP, DeliveryChannel.PUSH],
                source_id=quiz_id,
                source_type="quiz"
            )
        
        # Send notification asynchronously
        async def send_notification():
            await notification_service.create_notification(user_id, notification_data)
        
        try:
            asyncio.run(send_notification())
        except Exception as async_error:
            logger.warning(f"Failed to send quiz completion notification via async: {str(async_error)}")
        
    except Exception as e:
        logger.warning(f"Failed to send quiz completion notification: {str(e)}")


def _log_quiz_activity_progress(user_id: int, activity_id: str, success: bool) -> None:
    """Log quiz activity completion for dashboard tracking."""
    try:
        from ..dashboards.services import activity_tracker
        
        # Complete the activity
        async def complete_activity():
            error_message = None if success else "Quiz generation failed"
            await activity_tracker.complete_activity(activity_id, success, error_message)
        
        try:
            asyncio.run(complete_activity())
        except Exception as async_error:
            logger.warning(f"Failed to log quiz activity completion via async: {str(async_error)}")
        
    except Exception as e:
        logger.warning(f"Failed to log quiz activity completion: {str(e)}")
