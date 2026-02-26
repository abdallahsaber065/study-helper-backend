"""
Celery tasks for AI-powered summary generation.
"""

import logging
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

from celery import current_task
from sqlalchemy.orm import Session

from .celery_app import celery_app, celery_tasks_settings
from ..database import get_sync_db_session
from ..files.models import FileMetadata
from ..services.ai import AIProviderFactory, AIProviderType, RequestValidation
from ..services.ai.errors import AIProviderError
from ..summaries.models import Summary
from ..summaries.services import SummaryService, PromptTemplateService
from ..usage.services import UsageTracker, QuotaManager
from ..usage.schemas import UsageRecordCreate, OperationType, UsageStatus
from ..config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.summary_tasks.generate_summary_task",
    max_retries=celery_tasks_settings.MAX_RETRIES_API_ERROR,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
)
def generate_summary_task(
    self,
    summary_id: str,
    file_id: str,
    user_id: int,
    summary_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate AI summary for a document.
    
    Args:
        summary_id: ID of the summary record
        file_id: ID of the file to summarize
        user_id: ID of the user requesting the summary
        summary_config: Configuration for summary generation
        
    Returns:
        Dict containing task result and metadata
    """

    task_id = self.request.id or str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    logger.info(
        "Starting summary generation task",
        extra={
            "task_id": task_id,
            "summary_id": summary_id,
            "file_id": file_id,
            "user_id": user_id,
            "correlation_id": correlation_id,
        }
    )

    start_time = time.time()

    try:
        # Get database session
        with get_sync_db_session() as db_session:
            summary_service = SummaryService(db_session)

            # Update task progress
            _update_task_progress(
                task_id=task_id,
                summary_id=summary_id,
                progress=10,
                step="Initializing summary generation",
                db_session=db_session,
            )

            # Get summary and file records
            summary = db_session.query(Summary).filter(Summary.id == summary_id).first()
            if not summary:
                raise ValueError(f"Summary not found: {summary_id}")

            file_metadata = db_session.query(FileMetadata).filter(FileMetadata.id == file_id).first()
            if not file_metadata:
                raise ValueError(f"File not found: {file_id}")

            # Mark summary as processing
            summary.mark_as_processing(task_id, correlation_id)
            db_session.commit()

            _update_task_progress(
                task_id=task_id,
                summary_id=summary_id,
                progress=20,
                step="Loading file content",
                db_session=db_session,
            )

            # Load and validate file content
            file_content = _load_file_content(file_metadata.file_path)

            _update_task_progress(
                task_id=task_id,
                summary_id=summary_id,
                progress=30,
                step="Preparing AI request",
                db_session=db_session,
            )

            # Create AI provider
            ai_provider_type = AIProviderType(summary_config.get("ai_provider", "openai"))
            ai_provider = AIProviderFactory.create_from_env(ai_provider_type)

            # Generate prompt using template service
            prompt_service = PromptTemplateService()
            system_prompt, user_prompt = prompt_service.generate_summary_prompt(
                content=file_content,
                summary_type=summary_config.get("summary_type", "general"),
                max_length=summary_config.get("max_length"),
                custom_instructions=summary_config.get("custom_instructions"),
            )

            # Prepare AI request
            request_data = RequestValidation(
                system_instruction=system_prompt,
                user_text=user_prompt,
                model=summary_config.get("ai_model"),
                temperature=summary_config.get("temperature", 0.7),
                max_tokens=summary_config.get("max_tokens", 4000),
            )

            _update_task_progress(
                task_id=task_id,
                summary_id=summary_id,
                progress=50,
                step="Generating summary with AI",
                db_session=db_session,
            )

            # Generate summary using AI provider (run async code in sync context)
            import asyncio
            ai_response = asyncio.run(ai_provider.generate_with_monitoring(request_data))

            if not ai_response.text:
                raise ValueError("AI provider returned empty response")

            _update_task_progress(
                task_id=task_id,
                summary_id=summary_id,
                progress=80,
                step="Processing and saving summary",
                db_session=db_session,
            )

            # Calculate metrics
            processing_time_ms = int((time.time() - start_time) * 1000)
            original_word_count = len(file_content.split())
            summary_word_count = len(ai_response.text.split())

            # Update summary with results
            summary.content = ai_response.text
            summary.ai_provider = ai_provider_type.value
            summary.ai_model_used = ai_response.model
            summary.correlation_id = correlation_id
            summary.input_tokens = getattr(ai_response.raw, 'usage', {}).get('prompt_tokens')
            summary.output_tokens = getattr(ai_response.raw, 'usage', {}).get('completion_tokens')
            summary.total_tokens = getattr(ai_response.raw, 'usage', {}).get('total_tokens')
            summary.original_word_count = original_word_count
            summary.summary_word_count = summary_word_count
            summary.processing_time_ms = processing_time_ms

            # Calculate compression ratio
            summary.calculate_compression_ratio()

            # Estimate cost (simplified calculation)
            if summary.total_tokens:
                estimated_cost = _estimate_ai_cost(
                    provider=ai_provider_type.value,
                    model=ai_response.model,
                    tokens=summary.total_tokens
                )
                summary.generation_cost = estimated_cost

            # Calculate quality score (placeholder)
            quality_score = _calculate_quality_score(
                original_text=file_content,
                summary_text=ai_response.text,
                summary_type=summary_config.get("summary_type", "general")
            )
            summary.quality_score = quality_score

            # Record usage for tracking and billing
            _record_usage_sync(
                db_session=db_session,
                user_id=user_id,
                operation_type=OperationType.SUMMARY,
                resource_id=summary_id,
                ai_provider=ai_provider_type.value,
                ai_model=ai_response.model,
                input_tokens=getattr(ai_response.raw, 'usage', {}).get('prompt_tokens', 0),
                output_tokens=getattr(ai_response.raw, 'usage', {}).get('completion_tokens', 0),
                total_tokens=summary.total_tokens or 0,
                cost=summary.generation_cost or Decimal("0.0000"),
                processing_time_ms=processing_time_ms,
                correlation_id=correlation_id,
                task_id=task_id,
                quality_score=quality_score,
            )

            # Mark as completed
            summary.mark_as_completed(processing_time_ms)
            db_session.commit()

            _update_task_progress(
                task_id=task_id,
                summary_id=summary_id,
                progress=100,
                step="Summary generation completed",
                db_session=db_session,
                user_id=user_id,
            )
            
            # Log activity completion for dashboard tracking
            _log_activity_progress(user_id, task_id, True)

            logger.info(
                "Summary generation completed successfully",
                extra={
                    "task_id": task_id,
                    "summary_id": summary_id,
                    "processing_time_ms": processing_time_ms,
                    "word_count": summary_word_count,
                    "compression_ratio": float(summary.compression_ratio or 0),
                    "correlation_id": correlation_id,
                }
            )

            return {
                "task_id": task_id,
                "summary_id": summary_id,
                "status": "completed",
                "processing_time_ms": processing_time_ms,
                "word_count": summary_word_count,
                "compression_ratio": float(summary.compression_ratio or 0),
                "quality_score": float(quality_score or 0),
            }

    except AIProviderError as e:
        logger.error(
            "AI provider error during summary generation",
            extra={
                "task_id": task_id,
                "summary_id": summary_id,
                "error_type": e.error_type.value,
                "error_message": str(e),
                "correlation_id": correlation_id,
            }
        )

        # Handle retries for specific error types
        if e.error_type.value == "rate_limit_error":
            # Retry with exponential backoff for rate limits
            raise self.retry(countdown=min(60 * (2 ** self.request.retries), 300))
        elif e.error_type.value in ["network_error", "timeout_error"]:
            # Retry network/timeout errors
            raise self.retry(countdown=30)

        # Mark summary as failed
        try:
            with get_sync_db_session() as error_db_session:
                summary = error_db_session.query(Summary).filter(Summary.id == summary_id).first()
                if summary:
                    summary.mark_as_failed(str(e))
                    error_db_session.commit()
                    
                    # Log activity failure for dashboard tracking
                    _log_activity_progress(summary.user_id, task_id, False)
                    
                    # Send failure notification
                    _send_completion_notification(summary.user_id, summary_id, False)
                    
        except Exception as db_error:
            logger.error(f"Failed to update summary status to failed: {db_error}")

        raise e

    except Exception as e:
        logger.error(
            "Unexpected error during summary generation",
            extra={
                "task_id": task_id,
                "summary_id": summary_id,
                "error": str(e),
                "correlation_id": correlation_id,
            }
        )

        # Mark summary as failed
        try:
            with get_sync_db_session() as error_db_session:
                summary = error_db_session.query(Summary).filter(Summary.id == summary_id).first()
                if summary:
                    summary.mark_as_failed(str(e))
                    error_db_session.commit()
                    
                    # Log activity failure for dashboard tracking
                    _log_activity_progress(summary.user_id, task_id, False)
                    
                    # Send failure notification
                    _send_completion_notification(summary.user_id, summary_id, False)
                    
        except Exception as db_error:
            logger.error(f"Failed to update summary status to failed: {db_error}")

        raise e


def _send_websocket_progress_update(
    task_id: str,
    summary_id: str,
    progress: int,
    step: str,
    status: str,
    user_id: Optional[int] = None,
) -> None:
    """Send WebSocket progress update to connected clients."""
    try:
        # Import here to avoid circular imports
        from ..websocket.manager import websocket_manager
        from ..summaries.schemas import TaskProgressUpdate
        
        # Create progress update
        progress_update = TaskProgressUpdate(
            task_id=task_id,
            summary_id=summary_id,
            status=status,
            progress_percentage=progress,
            current_step=step,
        )
        
        # Send update in background (non-blocking)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in current thread, create new one for this task
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Schedule the WebSocket update
        loop.create_task(websocket_manager.send_task_progress(task_id, progress_update))
        
        # Also send user notification if user_id is provided
        if user_id and progress >= 100:
            _send_completion_notification(user_id, summary_id, status == "completed")
        
    except Exception as e:
        # Don't fail the task if WebSocket update fails
        logger.warning(f"Failed to send WebSocket progress update: {str(e)}")


def _send_completion_notification(user_id: int, summary_id: str, success: bool) -> None:
    """Send completion notification to user."""
    try:
        import asyncio
        from ..notifications.services import notification_service
        from ..notifications.models import NotificationType, NotificationPriority, DeliveryChannel
        from ..notifications.schemas import NotificationCreate
        
        # Create appropriate notification
        if success:
            notification_data = NotificationCreate(
                type=NotificationType.SUMMARY_GENERATED,
                priority=NotificationPriority.NORMAL,
                title="Summary Generated Successfully",
                message="Your document summary has been generated and is ready to view.",
                data={
                    "summary_id": summary_id,
                    "action": "view_summary"
                },
                action_url=f"/summaries/{summary_id}",
                action_text="View Summary",
                channels=[DeliveryChannel.IN_APP, DeliveryChannel.PUSH],
                source_id=summary_id,
                source_type="summary"
            )
        else:
            notification_data = NotificationCreate(
                type=NotificationType.SUMMARY_FAILED,
                priority=NotificationPriority.HIGH,
                title="Summary Generation Failed",
                message="We encountered an error while generating your document summary. Please try again.",
                data={
                    "summary_id": summary_id,
                    "action": "retry_summary"
                },
                action_url=f"/summaries/{summary_id}/retry",
                action_text="Try Again",
                channels=[DeliveryChannel.IN_APP, DeliveryChannel.PUSH],
                source_id=summary_id,
                source_type="summary"
            )
        
        # Send notification asynchronously
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.create_task(notification_service.create_notification(user_id, notification_data))
        
    except Exception as e:
        logger.warning(f"Failed to send completion notification: {str(e)}")


def _log_activity_progress(user_id: int, activity_id: str, success: bool) -> None:
    """Log activity completion for dashboard tracking."""
    try:
        import asyncio
        from ..dashboards.services import activity_tracker
        
        # Complete the activity
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        error_message = None if success else "Summary generation failed"
        loop.create_task(activity_tracker.complete_activity(activity_id, success, error_message))
        
    except Exception as e:
        logger.warning(f"Failed to log activity completion: {str(e)}")


def _update_task_progress(
    task_id: str,
    summary_id: str,
    progress: int,
    step: str,
    db_session: Session,
    user_id: Optional[int] = None,
) -> None:
    """Update task progress in database and send WebSocket update."""
    
    # Update database
    summary = db_session.query(Summary).filter(Summary.id == summary_id).first()
    if summary:
        summary.update_progress(progress)
        db_session.commit()
        
        # Get user_id from summary if not provided
        if not user_id:
            user_id = summary.user_id
    
    # Update Celery task state
    if current_task:
        current_task.update_state(
            state="PROGRESS",
            meta={
                "progress": progress,
                "step": step,
                "summary_id": summary_id,
                "user_id": user_id,
            }
        )
    
    # Send WebSocket update to client with comprehensive real-time updates
    _send_websocket_progress_update(
        task_id=task_id,
        summary_id=summary_id,
        progress=progress,
        step=step,
        status="processing" if progress < 100 else "completed",
        user_id=user_id
    )


def _load_file_content(file_path: str) -> str:
    """Load and extract text content from file."""
    
    try:
        # For now, assume text files. In production, add proper file processing
        # for PDFs, Word docs, etc.
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if not content.strip():
            raise ValueError("File appears to be empty")
            
        # Basic content validation
        if len(content) < 100:
            raise ValueError("File content too short for meaningful summarization")
            
        if len(content) > 1000000:  # 1MB text limit
            raise ValueError("File content too large for processing")
            
        return content
        
    except UnicodeDecodeError:
        raise ValueError("Unable to decode file content as text")
    except FileNotFoundError:
        raise ValueError("File not found on disk")
    except Exception as e:
        raise ValueError(f"Error reading file: {str(e)}")


def _estimate_ai_cost(provider: str, model: str, tokens: int) -> Decimal:
    """Estimate AI API cost based on provider, model, and token usage."""
    
    # Simplified cost estimation - in production, use actual API pricing
    cost_per_1k_tokens = {
        "openai": {
            "gpt-4o": 0.015,
            "gpt-4o-mini": 0.0015,
            "gpt-4": 0.030,
            "gpt-3.5-turbo": 0.002,
        },
        "gemini": {
            "gemini-2.0-flash": 0.001,
            "gemini-1.5-pro": 0.005,
        },
        "anthropic": {
            "claude-4-opus": 0.075,
            "claude-3.5-sonnet": 0.015,
            "claude-3-haiku": 0.0008,
        }
    }
    
    rate = cost_per_1k_tokens.get(provider, {}).get(model, 0.01)  # Default rate
    cost = (tokens / 1000) * rate
    
    return Decimal(str(round(cost, 4)))


def _calculate_quality_score(
    original_text: str,
    summary_text: str,
    summary_type: str
) -> Decimal:
    """Calculate a quality score for the generated summary."""
    
    # Placeholder quality scoring algorithm
    # In production, this would use more sophisticated NLP metrics
    
    score = 3.5  # Base score
    
    # Check summary length appropriateness
    original_words = len(original_text.split())
    summary_words = len(summary_text.split())
    compression_ratio = summary_words / original_words if original_words > 0 else 0
    
    # Ideal compression ratio depends on summary type
    ideal_ratios = {
        "executive": 0.05,    # Very brief
        "general": 0.15,      # Moderate
        "detailed": 0.30,     # More comprehensive
        "academic": 0.20,     # Academic style
        "technical": 0.25,    # Technical details
    }
    
    ideal_ratio = ideal_ratios.get(summary_type, 0.15)
    ratio_difference = abs(compression_ratio - ideal_ratio)
    
    if ratio_difference < 0.05:
        score += 1.0
    elif ratio_difference < 0.10:
        score += 0.5
    else:
        score -= 0.5
    
    # Check for completeness (placeholder)
    if len(summary_text) < 50:
        score -= 1.0
    elif len(summary_text) < 100:
        score -= 0.5
    
    # Ensure score is within valid range
    score = max(1.0, min(5.0, score))
    
    return Decimal(str(round(score, 2)))


def _record_usage_sync(
    db_session: Session,
    user_id: int,
    operation_type: OperationType,
    resource_id: str,
    ai_provider: str,
    ai_model: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    cost: Decimal,
    processing_time_ms: int,
    correlation_id: str,
    task_id: str,
    quality_score: Optional[Decimal] = None,
) -> None:
    """Record usage in sync context for Celery tasks."""
    from ..usage.models import UsageRecord, UserQuota
    from datetime import datetime
    
    try:
        # Create usage record
        usage_record = UsageRecord(
            user_id=user_id,
            operation_type=operation_type.value,
            resource_id=resource_id,
            ai_provider=ai_provider,
            ai_model=ai_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
            processing_time_ms=processing_time_ms,
            request_timestamp=datetime.utcnow(),
            response_timestamp=datetime.utcnow(),
            correlation_id=correlation_id,
            task_id=task_id,
            status=UsageStatus.SUCCESS.value,
            quality_score=quality_score,
        )
        db_session.add(usage_record)
        
        # Update user quota usage
        today = datetime.utcnow().date()
        quota_month = today.replace(day=1)
        
        # Try to get existing quota
        quota = db_session.query(UserQuota).filter(
            UserQuota.user_id == user_id,
            UserQuota.quota_month == quota_month
        ).first()
        
        if not quota:
            # Create new quota with default limits
            quota = UserQuota(
                user_id=user_id,
                quota_month=quota_month,
                token_limit=100000,  # Default free tier limits
                cost_limit=Decimal("50.00"),
                summary_limit=100,
                quiz_limit=50,
            )
            db_session.add(quota)
        
        # Update quota usage
        quota.tokens_used += total_tokens
        quota.cost_used += cost
        if operation_type == OperationType.SUMMARY:
            quota.summaries_used += 1
        elif operation_type == OperationType.QUIZ:
            quota.quizzes_used += 1
        
        db_session.commit()
        
        logger.info(
            f"Recorded usage for user {user_id}: {total_tokens} tokens, ${cost}, operation: {operation_type.value}"
        )
        
    except Exception as e:
        logger.error(f"Failed to record usage: {str(e)}")
        # Don't fail the main task if usage recording fails
        db_session.rollback()
