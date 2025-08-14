"""
Notification service for comprehensive user communication management.

This service handles:
- Notification creation and delivery
- Real-time notification distribution via WebSocket and SSE
- Push notification integration
- Email notification sending
- Notification preferences management
- Analytics and reporting
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload

import structlog

from ..database import get_db_session
from ..users.models import User
from ..websocket.manager import websocket_manager
from .models import (
    Notification,
    NotificationPreference,
    PushSubscription,
    NotificationTemplate,
    NotificationType,
    NotificationPriority,
    NotificationStatus,
    DeliveryChannel
)
from .schemas import (
    NotificationCreate,
    NotificationUpdate,
    NotificationResponse,
    NotificationStats,
    NotificationPreferenceCreate,
    NotificationPreferenceUpdate,
    PushSubscriptionCreate,
    SSEMessage
)

logger = structlog.get_logger(__name__)


class NotificationService:
    """Comprehensive notification management service."""
    
    def __init__(self):
        self.logger = logger.bind(service="notification_service")
    
    async def create_notification(
        self,
        user_id: int,
        notification_data: NotificationCreate,
        session: Optional[AsyncSession] = None
    ) -> NotificationResponse:
        """Create a new notification for a user."""
        
        if not session:
            async with get_db_session() as session:
                return await self._create_notification_impl(user_id, notification_data, session)
        else:
            return await self._create_notification_impl(user_id, notification_data, session)
    
    async def _create_notification_impl(
        self,
        user_id: int,
        notification_data: NotificationCreate,
        session: AsyncSession
    ) -> NotificationResponse:
        """Internal implementation of notification creation."""
        
        # Check user preferences to filter delivery channels
        preferences = await self._get_user_preferences_for_type(
            user_id, notification_data.type, session
        )
        
        # Filter channels based on user preferences
        enabled_channels = self._filter_channels_by_preferences(
            notification_data.channels, preferences
        )
        
        if not enabled_channels:
            self.logger.info(
                "Notification skipped due to user preferences",
                user_id=user_id,
                notification_type=notification_data.type
            )
            # Still create the notification but mark as dismissed
            enabled_channels = [DeliveryChannel.IN_APP]
            status = NotificationStatus.DISMISSED
        else:
            status = NotificationStatus.PENDING
        
        # Create notification record
        notification = Notification(
            user_id=user_id,
            type=notification_data.type,
            priority=notification_data.priority,
            title=notification_data.title,
            message=notification_data.message,
            data=notification_data.data,
            action_url=notification_data.action_url,
            action_text=notification_data.action_text,
            image_url=notification_data.image_url,
            channels=enabled_channels,
            schedule_for=notification_data.schedule_for,
            expires_at=notification_data.expires_at,
            source_id=notification_data.source_id,
            source_type=notification_data.source_type,
            correlation_id=notification_data.correlation_id,
            status=status
        )
        
        session.add(notification)
        await session.commit()
        await session.refresh(notification)
        
        self.logger.info(
            "Notification created",
            notification_id=notification.id,
            user_id=user_id,
            type=notification_data.type,
            channels=enabled_channels
        )
        
        # Schedule delivery if not scheduled for later
        if not notification_data.schedule_for or notification_data.schedule_for <= datetime.utcnow():
            await self._deliver_notification(notification, session)
        
        return NotificationResponse.from_orm(notification)
    
    async def _deliver_notification(
        self,
        notification: Notification,
        session: AsyncSession
    ) -> None:
        """Deliver a notification through all specified channels."""
        
        delivery_results = []
        
        for channel in notification.channels:
            try:
                success = False
                
                if channel == DeliveryChannel.IN_APP:
                    success = await self._deliver_in_app(notification)
                elif channel == DeliveryChannel.EMAIL:
                    success = await self._deliver_email(notification, session)
                elif channel == DeliveryChannel.PUSH:
                    success = await self._deliver_push(notification, session)
                
                delivery_results.append(success)
                
            except Exception as e:
                self.logger.error(
                    "Notification delivery failed",
                    notification_id=notification.id,
                    channel=channel,
                    error=str(e)
                )
                delivery_results.append(False)
        
        # Update notification status based on delivery results
        if any(delivery_results):
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.utcnow()
            if all(delivery_results):
                notification.status = NotificationStatus.DELIVERED
                notification.delivered_at = datetime.utcnow()
        else:
            notification.status = NotificationStatus.FAILED
            notification.retry_count += 1
            notification.error_message = "Failed to deliver through any channel"
        
        await session.commit()
    
    async def _deliver_in_app(self, notification: Notification) -> bool:
        """Deliver notification via WebSocket (in-app)."""
        
        try:
            # Send via WebSocket to all user connections
            await websocket_manager.send_user_notification(
                user_id=notification.user_id,
                notification_type=notification.type.value,
                message=notification.message,
                data={
                    "id": notification.id,
                    "title": notification.title,
                    "priority": notification.priority.value,
                    "action_url": notification.action_url,
                    "action_text": notification.action_text,
                    "image_url": notification.image_url,
                    "data": notification.data,
                    "created_at": notification.created_at.isoformat(),
                    "source_id": notification.source_id,
                    "source_type": notification.source_type
                }
            )
            
            self.logger.info(
                "In-app notification delivered",
                notification_id=notification.id,
                user_id=notification.user_id
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "In-app notification delivery failed",
                notification_id=notification.id,
                error=str(e)
            )
            return False
    
    async def _deliver_email(
        self, 
        notification: Notification, 
        session: AsyncSession
    ) -> bool:
        """Deliver notification via email."""
        
        try:
            # Get user email
            user_result = await session.execute(
                select(User).where(User.id == notification.user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user or not user.email:
                return False
            
            # Get email template for this notification type
            template = await self._get_email_template(notification.type, session)
            
            if not template:
                self.logger.warning(
                    "No email template found for notification type",
                    notification_type=notification.type,
                    notification_id=notification.id
                )
                return False
            
            # Render email content
            email_data = {
                "user_name": user.email.split("@")[0],  # Simple name extraction
                "notification_title": notification.title,
                "notification_message": notification.message,
                "action_url": notification.action_url or "",
                "action_text": notification.action_text or "View Details",
                **(notification.data or {})
            }
            
            subject = template.render_email_subject(email_data) or notification.title
            html_content = template.email_html_template
            text_content = template.email_text_template
            
            if html_content:
                html_content = html_content.format(**email_data)
            if text_content:
                text_content = text_content.format(**email_data)
            else:
                text_content = notification.message
            
            # TODO: Integrate with actual email service (FastAPI-Mail, AWS SES, etc.)
            # For now, log the email content
            self.logger.info(
                "Email notification would be sent",
                notification_id=notification.id,
                to=user.email,
                subject=subject,
                preview=text_content[:100] + "..." if len(text_content) > 100 else text_content
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Email notification delivery failed",
                notification_id=notification.id,
                error=str(e)
            )
            return False
    
    async def _deliver_push(
        self, 
        notification: Notification, 
        session: AsyncSession
    ) -> bool:
        """Deliver notification via web push."""
        
        try:
            # Get user's push subscriptions
            subscriptions_result = await session.execute(
                select(PushSubscription).where(
                    and_(
                        PushSubscription.user_id == notification.user_id,
                        PushSubscription.is_active == True
                    )
                )
            )
            subscriptions = subscriptions_result.scalars().all()
            
            if not subscriptions:
                return False
            
            # Prepare push payload
            push_data = {
                "title": notification.title,
                "body": notification.message,
                "icon": notification.image_url or "/icon-192x192.png",
                "badge": "/badge-72x72.png",
                "tag": f"notification_{notification.id}",
                "data": {
                    "notificationId": notification.id,
                    "actionUrl": notification.action_url,
                    "timestamp": notification.created_at.isoformat(),
                    **(notification.data or {})
                }
            }
            
            # TODO: Integrate with web push service (pywebpush)
            # For now, log the push notification
            for subscription in subscriptions:
                self.logger.info(
                    "Push notification would be sent",
                    notification_id=notification.id,
                    user_id=notification.user_id,
                    endpoint=subscription.endpoint[:50] + "...",
                    title=notification.title
                )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Push notification delivery failed",
                notification_id=notification.id,
                error=str(e)
            )
            return False
    
    async def get_user_notifications(
        self,
        user_id: int,
        status_filter: Optional[NotificationStatus] = None,
        type_filter: Optional[NotificationType] = None,
        limit: int = 50,
        offset: int = 0,
        include_read: bool = True,
        session: Optional[AsyncSession] = None
    ) -> Tuple[List[NotificationResponse], int]:
        """Get notifications for a user with filtering and pagination."""
        
        if not session:
            async with get_db_session() as session:
                return await self._get_user_notifications_impl(
                    user_id, status_filter, type_filter, limit, offset, include_read, session
                )
        else:
            return await self._get_user_notifications_impl(
                user_id, status_filter, type_filter, limit, offset, include_read, session
            )
    
    async def _get_user_notifications_impl(
        self,
        user_id: int,
        status_filter: Optional[NotificationStatus],
        type_filter: Optional[NotificationType],
        limit: int,
        offset: int,
        include_read: bool,
        session: AsyncSession
    ) -> Tuple[List[NotificationResponse], int]:
        """Internal implementation of get_user_notifications."""
        
        # Build query conditions
        conditions = [Notification.user_id == user_id]
        
        if status_filter:
            conditions.append(Notification.status == status_filter)
        
        if type_filter:
            conditions.append(Notification.type == type_filter)
        
        if not include_read:
            conditions.append(Notification.status != NotificationStatus.READ)
        
        # Check for expired notifications
        conditions.append(
            or_(
                Notification.expires_at.is_(None),
                Notification.expires_at > datetime.utcnow()
            )
        )
        
        # Get total count
        count_query = select(func.count()).select_from(Notification).where(and_(*conditions))
        count_result = await session.execute(count_query)
        total = count_result.scalar()
        
        # Get notifications
        query = (
            select(Notification)
            .where(and_(*conditions))
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await session.execute(query)
        notifications = result.scalars().all()
        
        return [NotificationResponse.from_orm(n) for n in notifications], total
    
    async def mark_notifications_read(
        self,
        user_id: int,
        notification_ids: List[str],
        session: Optional[AsyncSession] = None
    ) -> int:
        """Mark notifications as read for a user."""
        
        if not session:
            async with get_db_session() as session:
                return await self._mark_notifications_read_impl(user_id, notification_ids, session)
        else:
            return await self._mark_notifications_read_impl(user_id, notification_ids, session)
    
    async def _mark_notifications_read_impl(
        self,
        user_id: int,
        notification_ids: List[str],
        session: AsyncSession
    ) -> int:
        """Internal implementation of mark_notifications_read."""
        
        query = (
            update(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.id.in_(notification_ids),
                    Notification.status != NotificationStatus.READ
                )
            )
            .values(
                status=NotificationStatus.READ,
                read_at=datetime.utcnow()
            )
        )
        
        result = await session.execute(query)
        await session.commit()
        
        updated_count = result.rowcount
        
        self.logger.info(
            "Notifications marked as read",
            user_id=user_id,
            updated_count=updated_count,
            requested_count=len(notification_ids)
        )
        
        return updated_count
    
    async def dismiss_notifications(
        self,
        user_id: int,
        notification_ids: List[str],
        session: Optional[AsyncSession] = None
    ) -> int:
        """Dismiss notifications for a user."""
        
        if not session:
            async with get_db_session() as session:
                return await self._dismiss_notifications_impl(user_id, notification_ids, session)
        else:
            return await self._dismiss_notifications_impl(user_id, notification_ids, session)
    
    async def _dismiss_notifications_impl(
        self,
        user_id: int,
        notification_ids: List[str],
        session: AsyncSession
    ) -> int:
        """Internal implementation of dismiss_notifications."""
        
        query = (
            update(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.id.in_(notification_ids)
                )
            )
            .values(
                status=NotificationStatus.DISMISSED,
                dismissed_at=datetime.utcnow()
            )
        )
        
        result = await session.execute(query)
        await session.commit()
        
        updated_count = result.rowcount
        
        self.logger.info(
            "Notifications dismissed",
            user_id=user_id,
            updated_count=updated_count
        )
        
        return updated_count
    
    async def get_notification_stats(
        self,
        user_id: int,
        days: int = 30,
        session: Optional[AsyncSession] = None
    ) -> NotificationStats:
        """Get notification statistics for a user."""
        
        if not session:
            async with get_db_session() as session:
                return await self._get_notification_stats_impl(user_id, days, session)
        else:
            return await self._get_notification_stats_impl(user_id, days, session)
    
    async def _get_notification_stats_impl(
        self,
        user_id: int,
        days: int,
        session: AsyncSession
    ) -> NotificationStats:
        """Internal implementation of get_notification_stats."""
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get basic counts
        base_query = select(Notification).where(
            and_(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff_date
            )
        )
        
        result = await session.execute(base_query)
        notifications = result.scalars().all()
        
        total_notifications = len(notifications)
        unread_count = sum(1 for n in notifications if n.status != NotificationStatus.READ)
        pending_count = sum(1 for n in notifications if n.status == NotificationStatus.PENDING)
        failed_count = sum(1 for n in notifications if n.status == NotificationStatus.FAILED)
        
        # Group by type and status
        notifications_by_type = {}
        notifications_by_status = {}
        
        for notification in notifications:
            # By type
            type_key = notification.type
            notifications_by_type[type_key] = notifications_by_type.get(type_key, 0) + 1
            
            # By status
            status_key = notification.status
            notifications_by_status[status_key] = notifications_by_status.get(status_key, 0) + 1
        
        # Calculate delivery rate
        delivered_count = sum(
            1 for n in notifications 
            if n.status in [NotificationStatus.SENT, NotificationStatus.DELIVERED, NotificationStatus.READ]
        )
        delivery_rate = delivered_count / total_notifications if total_notifications > 0 else 0.0
        
        # Calculate average read time
        read_notifications = [
            n for n in notifications 
            if n.read_at and n.sent_at and n.read_at > n.sent_at
        ]
        
        average_read_time_minutes = None
        if read_notifications:
            total_read_time = sum(
                (n.read_at - n.sent_at).total_seconds() 
                for n in read_notifications
            )
            average_read_time_minutes = (total_read_time / len(read_notifications)) / 60
        
        return NotificationStats(
            total_notifications=total_notifications,
            unread_count=unread_count,
            pending_count=pending_count,
            failed_count=failed_count,
            notifications_by_type=notifications_by_type,
            notifications_by_status=notifications_by_status,
            delivery_rate=delivery_rate,
            average_read_time_minutes=average_read_time_minutes
        )
    
    async def _get_user_preferences_for_type(
        self,
        user_id: int,
        notification_type: NotificationType,
        session: AsyncSession
    ) -> Optional[NotificationPreference]:
        """Get user preferences for a specific notification type."""
        
        query = select(NotificationPreference).where(
            and_(
                NotificationPreference.user_id == user_id,
                NotificationPreference.notification_type == notification_type
            )
        )
        
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    def _filter_channels_by_preferences(
        self,
        requested_channels: List[DeliveryChannel],
        preferences: Optional[NotificationPreference]
    ) -> List[DeliveryChannel]:
        """Filter delivery channels based on user preferences."""
        
        if not preferences:
            return requested_channels
        
        enabled_channels = []
        
        for channel in requested_channels:
            if channel == DeliveryChannel.IN_APP and preferences.in_app_enabled:
                enabled_channels.append(channel)
            elif channel == DeliveryChannel.EMAIL and preferences.email_enabled:
                enabled_channels.append(channel)
            elif channel == DeliveryChannel.PUSH and preferences.push_enabled:
                enabled_channels.append(channel)
            elif channel == DeliveryChannel.SMS and preferences.sms_enabled:
                enabled_channels.append(channel)
        
        return enabled_channels
    
    async def _get_email_template(
        self,
        notification_type: NotificationType,
        session: AsyncSession
    ) -> Optional[NotificationTemplate]:
        """Get email template for a notification type."""
        
        query = select(NotificationTemplate).where(
            and_(
                NotificationTemplate.notification_type == notification_type,
                NotificationTemplate.is_active == True
            )
        )
        
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    async def process_scheduled_notifications(
        self,
        session: Optional[AsyncSession] = None
    ) -> int:
        """Process notifications scheduled for delivery."""
        
        if not session:
            async with get_db_session() as session:
                return await self._process_scheduled_notifications_impl(session)
        else:
            return await self._process_scheduled_notifications_impl(session)
    
    async def _process_scheduled_notifications_impl(
        self,
        session: AsyncSession
    ) -> int:
        """Internal implementation of process_scheduled_notifications."""
        
        # Get notifications scheduled for now or earlier
        query = select(Notification).where(
            and_(
                Notification.status == NotificationStatus.PENDING,
                Notification.schedule_for <= datetime.utcnow()
            )
        )
        
        result = await session.execute(query)
        notifications = result.scalars().all()
        
        processed_count = 0
        
        for notification in notifications:
            try:
                await self._deliver_notification(notification, session)
                processed_count += 1
            except Exception as e:
                self.logger.error(
                    "Failed to process scheduled notification",
                    notification_id=notification.id,
                    error=str(e)
                )
        
        return processed_count
    
    async def cleanup_expired_notifications(
        self,
        session: Optional[AsyncSession] = None
    ) -> int:
        """Clean up expired notifications."""
        
        if not session:
            async with get_db_session() as session:
                return await self._cleanup_expired_notifications_impl(session)
        else:
            return await self._cleanup_expired_notifications_impl(session)
    
    async def _cleanup_expired_notifications_impl(
        self,
        session: AsyncSession
    ) -> int:
        """Internal implementation of cleanup_expired_notifications."""
        
        # Mark expired notifications as expired
        query = (
            update(Notification)
            .where(
                and_(
                    Notification.expires_at < datetime.utcnow(),
                    Notification.status != NotificationStatus.EXPIRED
                )
            )
            .values(status=NotificationStatus.EXPIRED)
        )
        
        result = await session.execute(query)
        await session.commit()
        
        expired_count = result.rowcount
        
        self.logger.info("Expired notifications cleaned up", count=expired_count)
        
        return expired_count


async def get_user_notification_preferences(
    user_id: int,
    session: AsyncSession
) -> List[NotificationPreference]:
    """
    Get user's notification preferences, creating defaults if none exist.
    
    Args:
        user_id: User ID
        session: Database session
        
    Returns:
        List of notification preferences
    """
    # Query existing preferences
    stmt = (
        select(NotificationPreference)
        .where(NotificationPreference.user_id == user_id)
    )
    result = await session.execute(stmt)
    preferences = result.scalars().all()
    
    # If no preferences exist, create defaults for all notification types
    if not preferences:
        preferences = []
        for notification_type in NotificationType:
            # Default preferences based on notification type
            default_email = True
            default_push = True
            default_in_app = True
            
            # System notifications are usually less intrusive by default
            if notification_type in [
                NotificationType.SYSTEM_MAINTENANCE,
                NotificationType.SYSTEM_UPDATE
            ]:
                default_push = False
            
            preference = NotificationPreference(
                user_id=user_id,
                notification_type=notification_type,
                email_enabled=default_email,
                push_enabled=default_push,
                in_app_enabled=default_in_app,
                frequency="immediate"
            )
            session.add(preference)
            preferences.append(preference)
        
        await session.commit()
    
    return preferences


async def update_user_notification_preferences(
    user_id: int,
    preference_updates: List[NotificationPreferenceUpdate],
    session: AsyncSession
) -> List[NotificationPreference]:
    """
    Update user's notification preferences.
    
    Args:
        user_id: User ID
        preference_updates: List of preference updates
        session: Database session
        
    Returns:
        Updated list of notification preferences
    """
    # Get existing preferences
    preferences = await get_user_notification_preferences(user_id, session)
    preference_map = {pref.notification_type: pref for pref in preferences}
    
    # Update preferences
    for update in preference_updates:
        if update.notification_type in preference_map:
            preference = preference_map[update.notification_type]
            
            if update.email_enabled is not None:
                preference.email_enabled = update.email_enabled
            if update.push_enabled is not None:
                preference.push_enabled = update.push_enabled
            if update.in_app_enabled is not None:
                preference.in_app_enabled = update.in_app_enabled
            if update.frequency is not None:
                preference.frequency = update.frequency
            
            preference.updated_at = datetime.utcnow()
    
    await session.commit()
    
    # Return updated preferences
    return await get_user_notification_preferences(user_id, session)


async def create_user_notification_preference(
    user_id: int,
    preference_data: NotificationPreferenceCreate,
    session: AsyncSession
) -> NotificationPreference:
    """
    Create a new notification preference for a user.
    
    Args:
        user_id: User ID
        preference_data: Preference creation data
        session: Database session
        
    Returns:
        Created notification preference
    """
    # Check if preference already exists
    stmt = (
        select(NotificationPreference)
        .where(
            and_(
                NotificationPreference.user_id == user_id,
                NotificationPreference.notification_type == preference_data.notification_type
            )
        )
    )
    result = await session.execute(stmt)
    existing_preference = result.scalar_one_or_none()
    
    if existing_preference:
        # Update existing preference
        existing_preference.email_enabled = preference_data.email_enabled
        existing_preference.push_enabled = preference_data.push_enabled
        existing_preference.in_app_enabled = preference_data.in_app_enabled
        existing_preference.frequency = preference_data.frequency
        existing_preference.updated_at = datetime.utcnow()
        
        await session.commit()
        return existing_preference
    
    # Create new preference
    preference = NotificationPreference(
        user_id=user_id,
        notification_type=preference_data.notification_type,
        email_enabled=preference_data.email_enabled,
        push_enabled=preference_data.push_enabled,
        in_app_enabled=preference_data.in_app_enabled,
        frequency=preference_data.frequency
    )
    
    session.add(preference)
    await session.commit()
    await session.refresh(preference)
    
    return preference


# Global notification service instance
notification_service = NotificationService()
