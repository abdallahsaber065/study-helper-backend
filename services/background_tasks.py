"""
Background task service for handling long-running operations.
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Optional
from sqlalchemy.orm import Session
from fastapi import BackgroundTasks
import logging
from enum import Enum

from db_config import get_db
from models.models import User, ContentTypeEnum
from services.analytics_service import ContentAnalyticsService
from services.versioning_service import ContentVersioningService
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(Enum):
    AI_PROCESSING = "ai_processing"
    ANALYTICS_SYNC = "analytics_sync"
    VERSION_CLEANUP = "version_cleanup"
    NOTIFICATION_BATCH = "notification_batch"
    CONTENT_ANALYSIS = "content_analysis"


class BackgroundTaskManager:
    """Manager for background tasks with status tracking."""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.task_counter = 0
    
    def _generate_task_id(self) -> str:
        """Generate a unique task ID."""
        self.task_counter += 1
        return f"task_{self.task_counter}_{int(datetime.now().timestamp())}"
    
    def submit_task(
        self,
        task_type: TaskType,
        task_func: Callable,
        task_args: Dict[str, Any],
        user_id: Optional[int] = None,
        description: str = ""
    ) -> str:
        """Submit a background task."""
        task_id = self._generate_task_id()
        
        self.tasks[task_id] = {
            "id": task_id,
            "type": task_type.value,
            "status": TaskStatus.PENDING.value,
            "user_id": user_id,
            "description": description,
            "created_at": datetime.now(timezone.utc),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "progress": 0
        }
        
        # Execute the task
        asyncio.create_task(self._execute_task(task_id, task_func, task_args))
        
        return task_id
    
    async def _execute_task(
        self,
        task_id: str,
        task_func: Callable,
        task_args: Dict[str, Any]
    ):
        """Execute a background task."""
        try:
            # Update status to running
            self.tasks[task_id]["status"] = TaskStatus.RUNNING.value
            self.tasks[task_id]["started_at"] = datetime.now(timezone.utc)
            
            logger.info(f"Starting background task {task_id}")
            
            # Execute the task function
            if asyncio.iscoroutinefunction(task_func):
                result = await task_func(**task_args)
            else:
                result = task_func(**task_args)
            
            # Update status to completed
            self.tasks[task_id]["status"] = TaskStatus.COMPLETED.value
            self.tasks[task_id]["completed_at"] = datetime.now(timezone.utc)
            self.tasks[task_id]["result"] = result
            self.tasks[task_id]["progress"] = 100
            
            logger.info(f"Background task {task_id} completed successfully")
            
        except Exception as e:
            # Update status to failed
            self.tasks[task_id]["status"] = TaskStatus.FAILED.value
            self.tasks[task_id]["completed_at"] = datetime.now(timezone.utc)
            self.tasks[task_id]["error"] = str(e)
            
            logger.error(f"Background task {task_id} failed: {str(e)}")
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a background task."""
        return self.tasks.get(task_id)
    
    def get_user_tasks(self, user_id: int) -> list[Dict[str, Any]]:
        """Get all tasks for a specific user."""
        return [
            task for task in self.tasks.values()
            if task.get("user_id") == user_id
        ]
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Clean up old completed/failed tasks."""
        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        
        to_remove = []
        for task_id, task in self.tasks.items():
            if task["status"] in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value]:
                task_time = task["created_at"].timestamp()
                if task_time < cutoff_time:
                    to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.tasks[task_id]
        
        return len(to_remove)


# Global task manager instance
task_manager = BackgroundTaskManager()


# Background task functions
def sync_all_analytics():
    """Synchronize all analytics data."""
    try:
        with next(get_db()) as db:
            analytics_service = ContentAnalyticsService(db)
            analytics_service.sync_comment_counts()
            orphaned_count = analytics_service.cleanup_orphaned_analytics()
            
            return {
                "message": "Analytics synchronized successfully",
                "orphaned_cleaned": orphaned_count
            }
    except Exception as e:
        logger.error(f"Analytics sync failed: {str(e)}")
        raise


def cleanup_content_versions(content_type: ContentTypeEnum, content_id: int, keep_latest: int = 10):
    """Clean up old content versions."""
    try:
        with next(get_db()) as db:
            versioning_service = ContentVersioningService(db)
            deleted_count = versioning_service.delete_old_versions(
                content_type=content_type,
                content_id=content_id,
                keep_latest=keep_latest
            )
            
            return {
                "message": f"Cleaned up {deleted_count} old versions",
                "deleted_count": deleted_count
            }
    except Exception as e:
        logger.error(f"Version cleanup failed: {str(e)}")
        raise


def batch_send_notifications(user_ids: list[int], notification_data: Dict[str, Any]):
    """Send notifications to multiple users."""
    try:
        with next(get_db()) as db:
            notification_service = NotificationService(db)
            sent_count = 0
            
            for user_id in user_ids:
                try:
                    notification_service.create_notification(
                        user_id=user_id,
                        **notification_data
                    )
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send notification to user {user_id}: {str(e)}")
            
            return {
                "message": f"Sent {sent_count} notifications",
                "sent_count": sent_count,
                "target_count": len(user_ids)
            }
    except Exception as e:
        logger.error(f"Batch notification failed: {str(e)}")
        raise


async def analyze_content_engagement(content_type: ContentTypeEnum, content_id: int):
    """Analyze content engagement patterns."""
    try:
        with next(get_db()) as db:
            analytics_service = ContentAnalyticsService(db)
            
            # Get engagement metrics
            metrics = analytics_service.get_content_engagement_metrics(
                content_type=content_type,
                content_id=content_id
            )
            
            # Perform analysis (simplified)
            analysis = {
                "engagement_level": "high" if metrics.engagement_rate > 15 else "medium" if metrics.engagement_rate > 5 else "low",
                "interaction_quality": "high" if metrics.view_to_comment_ratio > 0.1 else "medium" if metrics.view_to_comment_ratio > 0.05 else "low",
                "popularity_trend": metrics.trend_direction,
                "recommendations": []
            }
            
            # Generate recommendations
            if metrics.engagement_rate < 5:
                analysis["recommendations"].append("Consider improving content quality or relevance")
            if metrics.view_to_comment_ratio < 0.02:
                analysis["recommendations"].append("Encourage more user interaction and discussion")
            if metrics.views < 10:
                analysis["recommendations"].append("Increase content visibility and promotion")
            
            return {
                "metrics": metrics.dict(),
                "analysis": analysis
            }
    except Exception as e:
        logger.error(f"Content analysis failed: {str(e)}")
        raise


# Helper functions for FastAPI integration
def submit_analytics_sync_task(user_id: Optional[int] = None) -> str:
    """Submit analytics synchronization task."""
    return task_manager.submit_task(
        task_type=TaskType.ANALYTICS_SYNC,
        task_func=sync_all_analytics,
        task_args={},
        user_id=user_id,
        description="Synchronize analytics data"
    )


def submit_version_cleanup_task(
    content_type: ContentTypeEnum,
    content_id: int,
    keep_latest: int = 10,
    user_id: Optional[int] = None
) -> str:
    """Submit version cleanup task."""
    return task_manager.submit_task(
        task_type=TaskType.VERSION_CLEANUP,
        task_func=cleanup_content_versions,
        task_args={
            "content_type": content_type,
            "content_id": content_id,
            "keep_latest": keep_latest
        },
        user_id=user_id,
        description=f"Clean up versions for {content_type.value} {content_id}"
    )


def submit_content_analysis_task(
    content_type: ContentTypeEnum,
    content_id: int,
    user_id: Optional[int] = None
) -> str:
    """Submit content analysis task."""
    return task_manager.submit_task(
        task_type=TaskType.CONTENT_ANALYSIS,
        task_func=analyze_content_engagement,
        task_args={
            "content_type": content_type,
            "content_id": content_id
        },
        user_id=user_id,
        description=f"Analyze engagement for {content_type.value} {content_id}"
    ) 