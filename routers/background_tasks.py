"""
Router for Background Tasks and System Operations.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from db_config import get_db
from core.security import get_current_user
from models.models import User, ContentTypeEnum
from services.background_tasks import (
    task_manager, submit_analytics_sync_task, submit_version_cleanup_task,
    submit_content_analysis_task
)

router = APIRouter(prefix="/background-tasks", tags=["Background Tasks"])


@router.post("/analytics/sync")
async def submit_analytics_sync(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit analytics synchronization task (admin only)."""
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    task_id = submit_analytics_sync_task(user_id=current_user.id)
    
    return {
        "message": "Analytics sync task submitted",
        "task_id": task_id,
        "status": "pending"
    }


@router.post("/version-cleanup/{content_type}/{content_id}")
async def submit_version_cleanup(
    content_type: ContentTypeEnum,
    content_id: int,
    keep_latest: int = Query(10, ge=1, le=50, description="Number of latest versions to keep"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit version cleanup task."""
    # TODO: Add permission check - user should own the content or be admin
    
    task_id = submit_version_cleanup_task(
        content_type=content_type,
        content_id=content_id,
        keep_latest=keep_latest,
        user_id=current_user.id
    )
    
    return {
        "message": "Version cleanup task submitted",
        "task_id": task_id,
        "content_type": content_type.value,
        "content_id": content_id,
        "keep_latest": keep_latest,
        "status": "pending"
    }


@router.post("/content-analysis/{content_type}/{content_id}")
async def submit_content_analysis(
    content_type: ContentTypeEnum,
    content_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit content engagement analysis task."""
    task_id = submit_content_analysis_task(
        content_type=content_type,
        content_id=content_id,
        user_id=current_user.id
    )
    
    return {
        "message": "Content analysis task submitted",
        "task_id": task_id,
        "content_type": content_type.value,
        "content_id": content_id,
        "status": "pending"
    }


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get the status of a background task."""
    task_status = task_manager.get_task_status(task_id)
    
    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Check if user can access this task
    if (task_status.get("user_id") != current_user.id and 
        current_user.role.value != "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this task"
        )
    
    return task_status


@router.get("/tasks")
async def get_user_tasks(
    current_user: User = Depends(get_current_user)
):
    """Get all tasks for the current user."""
    if current_user.role.value == "admin":
        # Admins can see all tasks
        tasks = list(task_manager.tasks.values())
    else:
        # Regular users only see their own tasks
        tasks = task_manager.get_user_tasks(current_user.id)
    
    # Sort by creation time (newest first)
    tasks.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {
        "tasks": tasks,
        "total_count": len(tasks)
    }


@router.delete("/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Cancel a background task (if possible)."""
    task_status = task_manager.get_task_status(task_id)
    
    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    # Check if user can cancel this task
    if (task_status.get("user_id") != current_user.id and 
        current_user.role.value != "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this task"
        )
    
    # Can only cancel pending or running tasks
    if task_status["status"] in ["completed", "failed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel task with status: {task_status['status']}"
        )
    
    # For now, just mark as failed (actual cancellation would need more complex implementation)
    if task_id in task_manager.tasks:
        task_manager.tasks[task_id]["status"] = "failed"
        task_manager.tasks[task_id]["error"] = "Cancelled by user"
        task_manager.tasks[task_id]["completed_at"] = task_status["created_at"].__class__.now()
    
    return {
        "message": "Task cancelled",
        "task_id": task_id
    }


@router.post("/cleanup/old-tasks")
async def cleanup_old_tasks(
    max_age_hours: int = Query(24, ge=1, le=168, description="Maximum age in hours"),
    current_user: User = Depends(get_current_user)
):
    """Clean up old completed/failed tasks (admin only)."""
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    cleaned_count = task_manager.cleanup_old_tasks(max_age_hours)
    
    return {
        "message": f"Cleaned up {cleaned_count} old tasks",
        "cleaned_count": cleaned_count,
        "max_age_hours": max_age_hours
    }


@router.get("/system/stats")
async def get_system_stats(
    current_user: User = Depends(get_current_user)
):
    """Get system statistics (admin only)."""
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    all_tasks = list(task_manager.tasks.values())
    
    # Calculate task statistics
    status_counts = {}
    type_counts = {}
    
    for task in all_tasks:
        status = task["status"]
        task_type = task["type"]
        
        status_counts[status] = status_counts.get(status, 0) + 1
        type_counts[task_type] = type_counts.get(task_type, 0) + 1
    
    return {
        "total_tasks": len(all_tasks),
        "task_status_breakdown": status_counts,
        "task_type_breakdown": type_counts,
        "memory_usage": {
            "active_tasks": len([t for t in all_tasks if t["status"] in ["pending", "running"]]),
            "completed_tasks": len([t for t in all_tasks if t["status"] == "completed"]),
            "failed_tasks": len([t for t in all_tasks if t["status"] == "failed"])
        }
    } 