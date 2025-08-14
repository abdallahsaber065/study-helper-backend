"""
WebSocket connection manager for real-time updates.
"""

import logging
import json
from datetime import datetime
from typing import Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
import structlog

from ..summaries.schemas import TaskProgressUpdate
from ..quizzes.schemas import QuizAttemptUpdate

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        # Store connections by user_id -> set of websockets
        self.user_connections: Dict[int, Set[WebSocket]] = {}
        # Store connections by task_id -> set of websockets
        self.task_connections: Dict[str, Set[WebSocket]] = {}
        # Store user_id for each websocket
        self.websocket_users: Dict[WebSocket, int] = {}
        # Store task_ids for each websocket
        self.websocket_tasks: Dict[WebSocket, Set[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        """Accept a WebSocket connection for a user."""
        await websocket.accept()
        
        # Add to user connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(websocket)
        
        # Store user for this websocket
        self.websocket_users[websocket] = user_id
        self.websocket_tasks[websocket] = set()
        
        logger.info(
            "WebSocket connected",
            user_id=user_id,
            total_connections=len(self.websocket_users)
        )

    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection."""
        user_id = self.websocket_users.get(websocket)
        
        if user_id:
            # Remove from user connections
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(websocket)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
            
            # Remove from task connections
            task_ids = self.websocket_tasks.get(websocket, set())
            for task_id in task_ids:
                if task_id in self.task_connections:
                    self.task_connections[task_id].discard(websocket)
                    if not self.task_connections[task_id]:
                        del self.task_connections[task_id]
            
            # Clean up websocket mappings
            del self.websocket_users[websocket]
            del self.websocket_tasks[websocket]
            
            logger.info(
                "WebSocket disconnected",
                user_id=user_id,
                total_connections=len(self.websocket_users)
            )

    async def subscribe_to_task(self, websocket: WebSocket, task_id: str):
        """Subscribe a WebSocket connection to task progress updates."""
        if task_id not in self.task_connections:
            self.task_connections[task_id] = set()
        
        self.task_connections[task_id].add(websocket)
        self.websocket_tasks[websocket].add(task_id)
        
        user_id = self.websocket_users.get(websocket)
        logger.info(
            "WebSocket subscribed to task",
            user_id=user_id,
            task_id=task_id
        )

    async def unsubscribe_from_task(self, websocket: WebSocket, task_id: str):
        """Unsubscribe a WebSocket connection from task progress updates."""
        if task_id in self.task_connections:
            self.task_connections[task_id].discard(websocket)
            if not self.task_connections[task_id]:
                del self.task_connections[task_id]
        
        if websocket in self.websocket_tasks:
            self.websocket_tasks[websocket].discard(task_id)
        
        user_id = self.websocket_users.get(websocket)
        logger.info(
            "WebSocket unsubscribed from task",
            user_id=user_id,
            task_id=task_id
        )

    async def send_task_progress(
        self,
        task_id: str,
        progress_update: TaskProgressUpdate
    ):
        """Send progress update to all connections subscribed to a task."""
        if task_id not in self.task_connections:
            return

        message = {
            "type": "task_progress",
            "data": progress_update.dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to all connections subscribed to this task
        disconnected = []
        for websocket in self.task_connections[task_id].copy():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(
                    "Failed to send progress update",
                    task_id=task_id,
                    error=str(e)
                )
                disconnected.append(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.disconnect(websocket)

        if disconnected:
            logger.info(
                "Cleaned up disconnected WebSockets",
                task_id=task_id,
                cleaned_count=len(disconnected)
            )

    async def send_user_notification(
        self,
        user_id: int,
        notification_type: str,
        message: str,
        data: Optional[Dict] = None
    ):
        """Send notification to all connections for a user."""
        if user_id not in self.user_connections:
            return

        notification = {
            "type": "notification",
            "notification_type": notification_type,
            "message": message,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        # Send to all user connections
        disconnected = []
        for websocket in self.user_connections[user_id].copy():
            try:
                await websocket.send_json(notification)
            except Exception as e:
                logger.warning(
                    "Failed to send user notification",
                    user_id=user_id,
                    error=str(e)
                )
                disconnected.append(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.disconnect(websocket)

    async def broadcast_system_message(self, message: str, data: Optional[Dict] = None):
        """Broadcast a system message to all connected users."""
        system_message = {
            "type": "system_message",
            "message": message,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        disconnected = []
        for websocket in list(self.websocket_users.keys()):
            try:
                await websocket.send_json(system_message)
            except Exception as e:
                logger.warning(
                    "Failed to send system message",
                    error=str(e)
                )
                disconnected.append(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.disconnect(websocket)

        logger.info(
            "Broadcasted system message",
            message=message,
            sent_to=len(self.websocket_users) - len(disconnected),
            cleaned_up=len(disconnected)
        )

    async def handle_client_message(self, websocket: WebSocket, data: dict):
        """Handle incoming messages from WebSocket clients."""
        message_type = data.get("type")
        user_id = self.websocket_users.get(websocket)

        if message_type == "subscribe_task":
            task_id = data.get("task_id")
            if task_id:
                await self.subscribe_to_task(websocket, task_id)
                await websocket.send_json({
                    "type": "subscription_confirmed",
                    "task_id": task_id,
                    "timestamp": datetime.utcnow().isoformat()
                })

        elif message_type == "unsubscribe_task":
            task_id = data.get("task_id")
            if task_id:
                await self.unsubscribe_from_task(websocket, task_id)
                await websocket.send_json({
                    "type": "unsubscription_confirmed",
                    "task_id": task_id,
                    "timestamp": datetime.utcnow().isoformat()
                })

        elif message_type == "ping":
            await websocket.send_json({
                "type": "pong",
                "timestamp": datetime.utcnow().isoformat()
            })

        else:
            logger.warning(
                "Unknown WebSocket message type",
                user_id=user_id,
                message_type=message_type
            )

    async def send_quiz_progress_update(
        self,
        task_id: str,
        quiz_id: str,
        progress_update: Dict
    ):
        """Send quiz generation progress update to subscribed connections."""
        if task_id not in self.task_connections:
            return

        message = {
            "type": "quiz_progress",
            "quiz_id": quiz_id,
            "task_id": task_id,
            "data": progress_update,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to all connections subscribed to this task
        disconnected = []
        for websocket in self.task_connections[task_id].copy():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(
                    "Failed to send quiz progress update",
                    task_id=task_id,
                    quiz_id=quiz_id,
                    error=str(e)
                )
                disconnected.append(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.disconnect(websocket)

    async def send_quiz_attempt_update(
        self,
        user_id: int,
        attempt_update: QuizAttemptUpdate
    ):
        """Send quiz attempt progress update to user connections."""
        if user_id not in self.user_connections:
            return

        message = {
            "type": "quiz_attempt_update",
            "data": attempt_update.dict(),
            "timestamp": datetime.utcnow().isoformat()
        }

        # Send to all user connections
        disconnected = []
        for websocket in self.user_connections[user_id].copy():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(
                    "Failed to send quiz attempt update",
                    user_id=user_id,
                    error=str(e)
                )
                disconnected.append(websocket)

        # Clean up disconnected websockets
        for websocket in disconnected:
            await self.disconnect(websocket)

    async def notify_quiz_completion(
        self,
        user_id: int,
        quiz_id: str,
        quiz_title: str,
        final_score: Optional[float] = None
    ):
        """Send quiz completion notification to user."""
        notification_data = {
            "quiz_id": quiz_id,
            "quiz_title": quiz_title,
            "final_score": final_score
        }

        await self.send_user_notification(
            user_id=user_id,
            notification_type="quiz_completed",
            message=f"Quiz '{quiz_title}' has been completed successfully!",
            data=notification_data
        )

    async def notify_quiz_generation_complete(
        self,
        user_id: int,
        quiz_id: str,
        quiz_title: str,
        question_count: int
    ):
        """Send quiz generation completion notification to user."""
        notification_data = {
            "quiz_id": quiz_id,
            "quiz_title": quiz_title,
            "question_count": question_count
        }

        await self.send_user_notification(
            user_id=user_id,
            notification_type="quiz_generated",
            message=f"Your quiz '{quiz_title}' with {question_count} questions is ready!",
            data=notification_data
        )

    def get_connection_stats(self) -> Dict:
        """Get statistics about current connections."""
        return {
            "total_connections": len(self.websocket_users),
            "users_connected": len(self.user_connections),
            "active_task_subscriptions": len(self.task_connections),
            "connections_by_user": {
                user_id: len(connections)
                for user_id, connections in self.user_connections.items()
            },
            "subscriptions_by_task": {
                task_id: len(connections)
                for task_id, connections in self.task_connections.items()
            }
        }


# Global connection manager instance
websocket_manager = ConnectionManager()
