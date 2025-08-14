"""
Dashboard and collaboration services for real-time features.

This service provides:
- Real-time activity tracking
- System metrics collection and monitoring
- Collaboration session management
- Live status dashboards
- Performance analytics
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_, desc
from sqlalchemy.orm import selectinload, joinedload

import structlog

from ..database import get_db_session
from ..users.models import User
from ..websocket.manager import websocket_manager
from .models import (
    UserActivity,
    SystemMetric,
    CollaborationSession,
    CollaborationParticipant,
    CollaborationActivity,
    LiveStatus,
    ActivityType,
    CollaborationAction
)

logger = structlog.get_logger(__name__)


class ActivityTracker:
    """Service for tracking user activities."""
    
    def __init__(self):
        self.logger = logger.bind(service="activity_tracker")
    
    async def log_activity(
        self,
        user_id: int,
        activity_type: ActivityType,
        description: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Log a user activity."""
        
        if not session:
            async with get_db_session() as session:
                return await self._log_activity_impl(
                    user_id, activity_type, description, resource_type,
                    resource_id, metadata, session_id, ip_address, user_agent, session
                )
        else:
            return await self._log_activity_impl(
                user_id, activity_type, description, resource_type,
                resource_id, metadata, session_id, ip_address, user_agent, session
            )
    
    async def _log_activity_impl(
        self,
        user_id: int,
        activity_type: ActivityType,
        description: Optional[str],
        resource_type: Optional[str],
        resource_id: Optional[str],
        metadata: Optional[Dict],
        session_id: Optional[str],
        ip_address: Optional[str],
        user_agent: Optional[str],
        session: AsyncSession
    ) -> str:
        """Internal implementation of log_activity."""
        
        activity = UserActivity(
            user_id=user_id,
            activity_type=activity_type,
            description=description,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        session.add(activity)
        await session.commit()
        await session.refresh(activity)
        
        self.logger.info(
            "Activity logged",
            activity_id=activity.id,
            user_id=user_id,
            activity_type=activity_type,
            resource_type=resource_type,
            resource_id=resource_id
        )
        
        # Send real-time update
        try:
            await websocket_manager.send_user_notification(
                user_id=user_id,
                notification_type="activity_logged",
                message=f"Activity recorded: {activity_type}",
                data={
                    "activity_id": activity.id,
                    "activity_type": activity_type,
                    "timestamp": activity.started_at.isoformat(),
                    "resource_type": resource_type,
                    "resource_id": resource_id
                }
            )
        except Exception as e:
            self.logger.warning(
                "Failed to send activity notification",
                activity_id=activity.id,
                error=str(e)
            )
        
        return activity.id
    
    async def complete_activity(
        self,
        activity_id: str,
        success: bool = True,
        error_message: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Mark an activity as completed."""
        
        if not session:
            async with get_db_session() as session:
                return await self._complete_activity_impl(activity_id, success, error_message, session)
        else:
            return await self._complete_activity_impl(activity_id, success, error_message, session)
    
    async def _complete_activity_impl(
        self,
        activity_id: str,
        success: bool,
        error_message: Optional[str],
        session: AsyncSession
    ) -> bool:
        """Internal implementation of complete_activity."""
        
        query = select(UserActivity).where(UserActivity.id == activity_id)
        result = await session.execute(query)
        activity = result.scalar_one_or_none()
        
        if not activity:
            return False
        
        activity.mark_completed(success, error_message)
        await session.commit()
        
        self.logger.info(
            "Activity completed",
            activity_id=activity_id,
            success=success,
            duration_ms=activity.duration_ms
        )
        
        return True
    
    async def get_recent_activities(
        self,
        user_id: Optional[int] = None,
        activity_types: Optional[List[ActivityType]] = None,
        resource_type: Optional[str] = None,
        limit: int = 100,
        hours: int = 24,
        session: Optional[AsyncSession] = None
    ) -> List[UserActivity]:
        """Get recent user activities."""
        
        if not session:
            async with get_db_session() as session:
                return await self._get_recent_activities_impl(
                    user_id, activity_types, resource_type, limit, hours, session
                )
        else:
            return await self._get_recent_activities_impl(
                user_id, activity_types, resource_type, limit, hours, session
            )
    
    async def _get_recent_activities_impl(
        self,
        user_id: Optional[int],
        activity_types: Optional[List[ActivityType]],
        resource_type: Optional[str],
        limit: int,
        hours: int,
        session: AsyncSession
    ) -> List[UserActivity]:
        """Internal implementation of get_recent_activities."""
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        conditions = [UserActivity.started_at >= cutoff_time]
        
        if user_id:
            conditions.append(UserActivity.user_id == user_id)
        
        if activity_types:
            conditions.append(UserActivity.activity_type.in_(activity_types))
        
        if resource_type:
            conditions.append(UserActivity.resource_type == resource_type)
        
        query = (
            select(UserActivity)
            .where(and_(*conditions))
            .options(selectinload(UserActivity.user))
            .order_by(desc(UserActivity.started_at))
            .limit(limit)
        )
        
        result = await session.execute(query)
        return result.scalars().all()


class SystemMetricsCollector:
    """Service for collecting and managing system metrics."""
    
    def __init__(self):
        self.logger = logger.bind(service="system_metrics_collector")
    
    async def record_metric(
        self,
        metric_name: str,
        value: float,
        metric_type: str = "gauge",
        unit: Optional[str] = None,
        category: str = "general",
        tags: Optional[Dict] = None,
        aggregation_period: Optional[str] = None,
        sample_count: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Record a system metric."""
        
        if not session:
            async with get_db_session() as session:
                return await self._record_metric_impl(
                    metric_name, value, metric_type, unit, category,
                    tags, aggregation_period, sample_count, session
                )
        else:
            return await self._record_metric_impl(
                metric_name, value, metric_type, unit, category,
                tags, aggregation_period, sample_count, session
            )
    
    async def _record_metric_impl(
        self,
        metric_name: str,
        value: float,
        metric_type: str,
        unit: Optional[str],
        category: str,
        tags: Optional[Dict],
        aggregation_period: Optional[str],
        sample_count: Optional[int],
        session: AsyncSession
    ) -> str:
        """Internal implementation of record_metric."""
        
        metric = SystemMetric(
            metric_name=metric_name,
            metric_type=metric_type,
            value=value,
            unit=unit,
            category=category,
            tags=tags or {},
            aggregation_period=aggregation_period,
            sample_count=sample_count
        )
        
        session.add(metric)
        await session.commit()
        await session.refresh(metric)
        
        self.logger.debug(
            "Metric recorded",
            metric_id=metric.id,
            metric_name=metric_name,
            value=value,
            category=category
        )
        
        return metric.id
    
    async def get_metrics(
        self,
        metric_names: Optional[List[str]] = None,
        category: Optional[str] = None,
        hours: int = 24,
        limit: int = 1000,
        session: Optional[AsyncSession] = None
    ) -> List[SystemMetric]:
        """Get system metrics."""
        
        if not session:
            async with get_db_session() as session:
                return await self._get_metrics_impl(metric_names, category, hours, limit, session)
        else:
            return await self._get_metrics_impl(metric_names, category, hours, limit, session)
    
    async def _get_metrics_impl(
        self,
        metric_names: Optional[List[str]],
        category: Optional[str],
        hours: int,
        limit: int,
        session: AsyncSession
    ) -> List[SystemMetric]:
        """Internal implementation of get_metrics."""
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        conditions = [SystemMetric.timestamp >= cutoff_time]
        
        if metric_names:
            conditions.append(SystemMetric.metric_name.in_(metric_names))
        
        if category:
            conditions.append(SystemMetric.category == category)
        
        query = (
            select(SystemMetric)
            .where(and_(*conditions))
            .order_by(desc(SystemMetric.timestamp))
            .limit(limit)
        )
        
        result = await session.execute(query)
        return result.scalars().all()


class CollaborationManager:
    """Service for managing real-time collaboration sessions."""
    
    def __init__(self):
        self.logger = logger.bind(service="collaboration_manager")
    
    async def create_session(
        self,
        owner_id: int,
        resource_type: str,
        resource_id: str,
        session_name: Optional[str] = None,
        is_public: bool = False,
        max_participants: Optional[int] = None,
        settings: Optional[Dict] = None,
        session: Optional[AsyncSession] = None
    ) -> CollaborationSession:
        """Create a new collaboration session."""
        
        if not session:
            async with get_db_session() as session:
                return await self._create_session_impl(
                    owner_id, resource_type, resource_id, session_name,
                    is_public, max_participants, settings, session
                )
        else:
            return await self._create_session_impl(
                owner_id, resource_type, resource_id, session_name,
                is_public, max_participants, settings, session
            )
    
    async def _create_session_impl(
        self,
        owner_id: int,
        resource_type: str,
        resource_id: str,
        session_name: Optional[str],
        is_public: bool,
        max_participants: Optional[int],
        settings: Optional[Dict],
        session: AsyncSession
    ) -> CollaborationSession:
        """Internal implementation of create_session."""
        
        collab_session = CollaborationSession(
            resource_type=resource_type,
            resource_id=resource_id,
            session_name=session_name,
            is_public=is_public,
            owner_id=owner_id,
            max_participants=max_participants,
            settings=settings or {}
        )
        
        session.add(collab_session)
        await session.commit()
        await session.refresh(collab_session)
        
        # Add owner as first participant
        await self._add_participant_impl(
            collab_session.id, owner_id, "owner", ["read", "write", "admin"], session
        )
        
        self.logger.info(
            "Collaboration session created",
            session_id=collab_session.id,
            owner_id=owner_id,
            resource_type=resource_type,
            resource_id=resource_id
        )
        
        return collab_session
    
    async def join_session(
        self,
        session_id: str,
        user_id: int,
        connection_id: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Join a collaboration session."""
        
        if not session:
            async with get_db_session() as session:
                return await self._join_session_impl(session_id, user_id, connection_id, session)
        else:
            return await self._join_session_impl(session_id, user_id, connection_id, session)
    
    async def _join_session_impl(
        self,
        session_id: str,
        user_id: int,
        connection_id: Optional[str],
        session: AsyncSession
    ) -> bool:
        """Internal implementation of join_session."""
        
        # Check if session exists and is active
        session_query = select(CollaborationSession).where(
            and_(
                CollaborationSession.id == session_id,
                CollaborationSession.is_active == True
            )
        )
        
        session_result = await session.execute(session_query)
        collab_session = session_result.scalar_one_or_none()
        
        if not collab_session:
            return False
        
        # Check if user is already a participant
        participant_query = select(CollaborationParticipant).where(
            and_(
                CollaborationParticipant.session_id == session_id,
                CollaborationParticipant.user_id == user_id
            )
        )
        
        participant_result = await session.execute(participant_query)
        participant = participant_result.scalar_one_or_none()
        
        if participant:
            # Update existing participant
            participant.is_online = True
            participant.connection_id = connection_id
            participant.last_activity = datetime.utcnow()
        else:
            # Add new participant
            await self._add_participant_impl(
                session_id, user_id, "viewer", ["read"], session
            )
        
        await session.commit()
        
        # Log activity
        await self._log_collaboration_activity(
            session_id, user_id, CollaborationAction.VIEW_JOIN,
            "User joined collaboration session", session
        )
        
        # Notify other participants
        await self._notify_session_participants(
            session_id, f"User joined the session", 
            {"user_id": user_id, "action": "joined"}, session
        )
        
        return True
    
    async def _add_participant_impl(
        self,
        session_id: str,
        user_id: int,
        role: str,
        permissions: List[str],
        session: AsyncSession
    ) -> CollaborationParticipant:
        """Internal helper to add a participant."""
        
        participant = CollaborationParticipant(
            session_id=session_id,
            user_id=user_id,
            role=role,
            permissions=permissions,
            is_online=True,
            last_activity=datetime.utcnow()
        )
        
        session.add(participant)
        return participant
    
    async def _log_collaboration_activity(
        self,
        session_id: str,
        user_id: int,
        action: CollaborationAction,
        description: str,
        session: AsyncSession,
        data: Optional[Dict] = None
    ) -> None:
        """Internal helper to log collaboration activity."""
        
        activity = CollaborationActivity(
            session_id=session_id,
            user_id=user_id,
            action=action,
            description=description,
            data=data or {}
        )
        
        session.add(activity)
    
    async def _notify_session_participants(
        self,
        session_id: str,
        message: str,
        data: Dict,
        session: AsyncSession
    ) -> None:
        """Internal helper to notify all session participants."""
        
        # Get all online participants
        participant_query = select(CollaborationParticipant).where(
            and_(
                CollaborationParticipant.session_id == session_id,
                CollaborationParticipant.is_online == True
            )
        ).options(selectinload(CollaborationParticipant.user))
        
        participant_result = await session.execute(participant_query)
        participants = participant_result.scalars().all()
        
        # Send WebSocket notifications
        for participant in participants:
            try:
                await websocket_manager.send_user_notification(
                    user_id=participant.user_id,
                    notification_type="collaboration_update",
                    message=message,
                    data={
                        "session_id": session_id,
                        "collaboration_data": data
                    }
                )
            except Exception as e:
                self.logger.warning(
                    "Failed to notify collaboration participant",
                    session_id=session_id,
                    user_id=participant.user_id,
                    error=str(e)
                )


class LiveStatusManager:
    """Service for managing live status information."""
    
    def __init__(self):
        self.logger = logger.bind(service="live_status_manager")
    
    async def update_status(
        self,
        status_type: str,
        scope: str,
        status: str,
        scope_id: Optional[str] = None,
        value: Optional[float] = None,
        message: Optional[str] = None,
        data: Optional[Dict] = None,
        expires_in_seconds: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> str:
        """Update live status information."""
        
        if not session:
            async with get_db_session() as session:
                return await self._update_status_impl(
                    status_type, scope, status, scope_id, value,
                    message, data, expires_in_seconds, session
                )
        else:
            return await self._update_status_impl(
                status_type, scope, status, scope_id, value,
                message, data, expires_in_seconds, session
            )
    
    async def _update_status_impl(
        self,
        status_type: str,
        scope: str,
        status: str,
        scope_id: Optional[str],
        value: Optional[float],
        message: Optional[str],
        data: Optional[Dict],
        expires_in_seconds: Optional[int],
        session: AsyncSession
    ) -> str:
        """Internal implementation of update_status."""
        
        expires_at = None
        if expires_in_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
        
        # Check if status already exists
        query = select(LiveStatus).where(
            and_(
                LiveStatus.status_type == status_type,
                LiveStatus.scope == scope,
                LiveStatus.scope_id == scope_id
            )
        )
        
        result = await session.execute(query)
        existing_status = result.scalar_one_or_none()
        
        if existing_status:
            existing_status.update_status(status, value, message, data)
            if expires_at:
                existing_status.expires_at = expires_at
            live_status = existing_status
        else:
            live_status = LiveStatus(
                status_type=status_type,
                scope=scope,
                scope_id=scope_id,
                status=status,
                value=value,
                message=message,
                data=data or {},
                expires_at=expires_at
            )
            session.add(live_status)
        
        await session.commit()
        await session.refresh(live_status)
        
        self.logger.debug(
            "Live status updated",
            status_id=live_status.id,
            status_type=status_type,
            scope=scope,
            status=status
        )
        
        return live_status.id


# Global service instances
activity_tracker = ActivityTracker()
metrics_collector = SystemMetricsCollector()
collaboration_manager = CollaborationManager()
status_manager = LiveStatusManager()
