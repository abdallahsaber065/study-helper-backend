"""
Celery application configuration for background task processing.
"""

import os
from celery import Celery
from kombu import Queue

from ..config import get_settings

settings = get_settings()

# Create Celery instance
celery_app = Celery("study_assistant")

# Configure Celery
celery_app.conf.update(
    # Broker and result backend configuration
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    
    # Task routing
    task_routes={
        "app.tasks.summary_tasks.generate_summary_task": {"queue": "summaries"},
        "app.tasks.quiz_tasks.generate_quiz_task": {"queue": "quizzes"},
    },
    
    # Queue configuration
    task_default_queue="default",
    task_queues=(
        Queue("default", routing_key="default"),
        Queue("summaries", routing_key="summaries"),
        Queue("quizzes", routing_key="quizzes"),
        Queue("high_priority", routing_key="high_priority"),
    ),
    
    # Task execution settings
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    
    # Task result settings
    result_expires=3600,  # 1 hour
    task_track_started=True,
    task_send_sent_event=True,
    
    # Worker configuration
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,
    
    # Task retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_events=True,
    
    # Security
    worker_hijack_root_logger=False,
    worker_log_color=False,
    
    # Task time limits
    task_soft_time_limit=600,  # 10 minutes
    task_time_limit=900,       # 15 minutes
    
    # Redis connection settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=5,
    
    # Rate limiting
    task_annotations={
        "app.tasks.summary_tasks.generate_summary_task": {
            "rate_limit": "10/m",  # 10 per minute
            "routing_key": "summaries",
        },
        "app.tasks.quiz_tasks.generate_quiz_task": {
            "rate_limit": "5/m",   # 5 per minute
            "routing_key": "quizzes",
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])

# Health check task
@celery_app.task(name="health_check")
def health_check():
    """Simple health check task for monitoring."""
    return {"status": "healthy", "message": "Celery worker is running"}


# Configure Celery to work with FastAPI dependency injection
class CeleryTasksSettings:
    """Settings for Celery task configuration."""
    
    SUMMARY_TASK_TIMEOUT = 600  # 10 minutes
    QUIZ_TASK_TIMEOUT = 900     # 15 minutes
    
    # AI provider rate limits (requests per minute)
    OPENAI_RATE_LIMIT = 50
    GEMINI_RATE_LIMIT = 60
    ANTHROPIC_RATE_LIMIT = 40
    
    # Task priorities
    HIGH_PRIORITY = 9
    NORMAL_PRIORITY = 5
    LOW_PRIORITY = 1
    
    # Maximum retries for different error types
    MAX_RETRIES_API_ERROR = 3
    MAX_RETRIES_RATE_LIMIT = 5
    MAX_RETRIES_NETWORK_ERROR = 2
    MAX_RETRIES_VALIDATION_ERROR = 0  # Don't retry validation errors


celery_tasks_settings = CeleryTasksSettings()
