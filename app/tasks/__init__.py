"""
Background task processing module using Celery and Redis.
"""

from .celery_app import celery_app
from .summary_tasks import generate_summary_task

__all__ = ["celery_app", "generate_summary_task"]