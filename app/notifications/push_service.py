"""
Push notification service for web push notifications.

This module provides integration with the Web Push Protocol to send
push notifications to user devices and browsers.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, update, and_

import structlog

from ..database import get_db_session
from .models import PushSubscription, Notification, NotificationStatus
from .schemas import PushSubscriptionCreate, PushSubscriptionResponse

logger = structlog.get_logger(__name__)


class WebPushConfig:
    """Configuration for Web Push notifications."""
    
    def __init__(self):
        # TODO: Load from environment variables
        self.vapid_private_key: Optional[str] = None
        self.vapid_public_key: Optional[str] = None
        self.vapid_claims: Dict[str, str] = {
            "sub": "mailto:support@studyassistant.com"
        }
        self.gcm_api_key: Optional[str] = None  # For legacy Chrome support
        self.timeout: int = 30  # Request timeout in seconds
        self.retry_after_default: int = 86400  # Default retry after (24 hours)


class PushNotificationService:
    """Service for managing web push notifications."""
    
    def __init__(self):
        self.logger = logger.bind(service="push_notification_service")
        self.config = WebPushConfig()
        self._push_client = None
    
    @property
    def push_client(self):
        """Lazy-load the web push client."""
        if not self._push_client:
            try:
                # Import pywebpush only when needed
                from pywebpush import webpush, WebPushException
                self._push_client = webpush
                self._push_exception = WebPushException
            except ImportError:
                self.logger.warning(
                    "pywebpush not installed. Push notifications will not work. "
                    "Install with: pip install pywebpush"
                )
                return None
        return self._push_client
    
    async def create_subscription(
        self,
        user_id: int,
        subscription_data: PushSubscriptionCreate,
        session: Optional[AsyncSession] = None
    ) -> PushSubscriptionResponse:
        """Create a new push subscription for a user."""
        
        if not session:
            async with get_db_session() as session:
                return await self._create_subscription_impl(user_id, subscription_data, session)
        else:
            return await self._create_subscription_impl(user_id, subscription_data, session)
    
    async def _create_subscription_impl(
        self,
        user_id: int,
        subscription_data: PushSubscriptionCreate,
        session: AsyncSession
    ) -> PushSubscriptionResponse:
        """Internal implementation of create_subscription."""
        
        # Check if subscription already exists
        existing_query = select(PushSubscription).where(
            PushSubscription.endpoint == subscription_data.endpoint
        )
        
        existing_result = await session.execute(existing_query)
        existing_subscription = existing_result.scalar_one_or_none()
        
        if existing_subscription:
            # Update existing subscription
            existing_subscription.user_id = user_id
            existing_subscription.p256dh_key = subscription_data.p256dh_key
            existing_subscription.auth_key = subscription_data.auth_key
            existing_subscription.user_agent = subscription_data.user_agent
            existing_subscription.device_type = subscription_data.device_type
            existing_subscription.browser_name = subscription_data.browser_name
            existing_subscription.browser_version = subscription_data.browser_version
            existing_subscription.is_active = True
            existing_subscription.failure_count = 0
            
            await session.commit()
            await session.refresh(existing_subscription)
            
            subscription = existing_subscription
        else:
            # Create new subscription
            subscription = PushSubscription(
                user_id=user_id,
                endpoint=subscription_data.endpoint,
                p256dh_key=subscription_data.p256dh_key,
                auth_key=subscription_data.auth_key,
                user_agent=subscription_data.user_agent,
                device_type=subscription_data.device_type,
                browser_name=subscription_data.browser_name,
                browser_version=subscription_data.browser_version
            )
            
            session.add(subscription)
            await session.commit()
            await session.refresh(subscription)
        
        self.logger.info(
            "Push subscription created/updated",
            subscription_id=subscription.id,
            user_id=user_id,
            endpoint=subscription_data.endpoint[:50] + "..."
        )
        
        return PushSubscriptionResponse.from_orm(subscription)
    
    async def get_user_subscriptions(
        self,
        user_id: int,
        active_only: bool = True,
        session: Optional[AsyncSession] = None
    ) -> List[PushSubscriptionResponse]:
        """Get all push subscriptions for a user."""
        
        if not session:
            async with get_db_session() as session:
                return await self._get_user_subscriptions_impl(user_id, active_only, session)
        else:
            return await self._get_user_subscriptions_impl(user_id, active_only, session)
    
    async def _get_user_subscriptions_impl(
        self,
        user_id: int,
        active_only: bool,
        session: AsyncSession
    ) -> List[PushSubscriptionResponse]:
        """Internal implementation of get_user_subscriptions."""
        
        conditions = [PushSubscription.user_id == user_id]
        
        if active_only:
            conditions.append(PushSubscription.is_active == True)
        
        query = select(PushSubscription).where(and_(*conditions))
        result = await session.execute(query)
        subscriptions = result.scalars().all()
        
        return [PushSubscriptionResponse.from_orm(sub) for sub in subscriptions]
    
    async def delete_subscription(
        self,
        subscription_id: str,
        user_id: int,
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Delete a push subscription."""
        
        if not session:
            async with get_db_session() as session:
                return await self._delete_subscription_impl(subscription_id, user_id, session)
        else:
            return await self._delete_subscription_impl(subscription_id, user_id, session)
    
    async def _delete_subscription_impl(
        self,
        subscription_id: str,
        user_id: int,
        session: AsyncSession
    ) -> bool:
        """Internal implementation of delete_subscription."""
        
        query = select(PushSubscription).where(
            and_(
                PushSubscription.id == subscription_id,
                PushSubscription.user_id == user_id
            )
        )
        
        result = await session.execute(query)
        subscription = result.scalar_one_or_none()
        
        if not subscription:
            return False
        
        # Mark as inactive instead of deleting
        subscription.is_active = False
        await session.commit()
        
        self.logger.info(
            "Push subscription deactivated",
            subscription_id=subscription_id,
            user_id=user_id
        )
        
        return True
    
    async def send_push_notification(
        self,
        subscription: PushSubscription,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        icon: Optional[str] = None,
        badge: Optional[str] = None,
        action_url: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Send a push notification to a specific subscription."""
        
        if not self.push_client:
            self.logger.warning("Push client not available")
            return False
        
        if not subscription.is_active:
            self.logger.warning(
                "Attempted to send push to inactive subscription",
                subscription_id=subscription.id
            )
            return False
        
        try:
            # Prepare notification payload
            payload = {
                "title": title,
                "body": body,
                "icon": icon or "/icon-192x192.png",
                "badge": badge or "/badge-72x72.png",
                "tag": f"notification_{datetime.utcnow().timestamp()}",
                "requireInteraction": True,
                "data": {
                    "timestamp": datetime.utcnow().isoformat(),
                    "url": action_url,
                    **(data or {})
                },
                "actions": []
            }
            
            if action_url:
                payload["actions"].append({
                    "action": "view",
                    "title": "View",
                    "icon": "/action-view.png"
                })
            
            # Prepare subscription info for pywebpush
            subscription_info = {
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh_key,
                    "auth": subscription.auth_key
                }
            }
            
            # Send the push notification
            response = self.push_client(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=self.config.vapid_private_key,
                vapid_claims=self.config.vapid_claims,
                timeout=self.config.timeout
            )
            
            # Update subscription usage
            subscription.last_used_at = datetime.utcnow()
            subscription.failure_count = 0
            
            if session:
                await session.commit()
            
            self.logger.info(
                "Push notification sent successfully",
                subscription_id=subscription.id,
                user_id=subscription.user_id,
                title=title,
                status_code=response.status_code
            )
            
            return True
            
        except Exception as e:
            # Handle push notification errors
            error_message = str(e)
            
            # Update failure count
            subscription.failure_count += 1
            
            # Deactivate subscription after too many failures
            if subscription.failure_count >= 5:
                subscription.is_active = False
                self.logger.warning(
                    "Push subscription deactivated due to repeated failures",
                    subscription_id=subscription.id,
                    failure_count=subscription.failure_count
                )
            
            if session:
                await session.commit()
            
            self.logger.error(
                "Failed to send push notification",
                subscription_id=subscription.id,
                user_id=subscription.user_id,
                error=error_message,
                failure_count=subscription.failure_count
            )
            
            return False
    
    async def send_push_to_user(
        self,
        user_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        icon: Optional[str] = None,
        badge: Optional[str] = None,
        action_url: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> int:
        """Send push notification to all active subscriptions for a user."""
        
        if not session:
            async with get_db_session() as session:
                return await self._send_push_to_user_impl(
                    user_id, title, body, data, icon, badge, action_url, session
                )
        else:
            return await self._send_push_to_user_impl(
                user_id, title, body, data, icon, badge, action_url, session
            )
    
    async def _send_push_to_user_impl(
        self,
        user_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]],
        icon: Optional[str],
        badge: Optional[str],
        action_url: Optional[str],
        session: AsyncSession
    ) -> int:
        """Internal implementation of send_push_to_user."""
        
        # Get all active subscriptions for the user
        subscriptions = await self._get_user_subscriptions_impl(user_id, True, session)
        
        if not subscriptions:
            self.logger.info(
                "No active push subscriptions found for user",
                user_id=user_id
            )
            return 0
        
        # Convert to ORM objects for sending
        subscription_query = select(PushSubscription).where(
            and_(
                PushSubscription.user_id == user_id,
                PushSubscription.is_active == True
            )
        )
        
        result = await session.execute(subscription_query)
        subscription_objects = result.scalars().all()
        
        sent_count = 0
        
        for subscription in subscription_objects:
            success = await self.send_push_notification(
                subscription=subscription,
                title=title,
                body=body,
                data=data,
                icon=icon,
                badge=badge,
                action_url=action_url,
                session=session
            )
            
            if success:
                sent_count += 1
        
        self.logger.info(
            "Push notifications sent to user",
            user_id=user_id,
            sent_count=sent_count,
            total_subscriptions=len(subscription_objects)
        )
        
        return sent_count
    
    async def cleanup_inactive_subscriptions(
        self,
        days_inactive: int = 30,
        session: Optional[AsyncSession] = None
    ) -> int:
        """Clean up inactive push subscriptions."""
        
        if not session:
            async with get_db_session() as session:
                return await self._cleanup_inactive_subscriptions_impl(days_inactive, session)
        else:
            return await self._cleanup_inactive_subscriptions_impl(days_inactive, session)
    
    async def _cleanup_inactive_subscriptions_impl(
        self,
        days_inactive: int,
        session: AsyncSession
    ) -> int:
        """Internal implementation of cleanup_inactive_subscriptions."""
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_inactive)
        
        # Find subscriptions that haven't been used recently or have failed repeatedly
        query = select(PushSubscription).where(
            and_(
                PushSubscription.is_active == True,
                or_(
                    PushSubscription.last_used_at < cutoff_date,
                    PushSubscription.failure_count >= 5
                )
            )
        )
        
        result = await session.execute(query)
        inactive_subscriptions = result.scalars().all()
        
        cleaned_count = 0
        
        for subscription in inactive_subscriptions:
            subscription.is_active = False
            cleaned_count += 1
        
        await session.commit()
        
        self.logger.info(
            "Inactive push subscriptions cleaned up",
            cleaned_count=cleaned_count,
            days_inactive=days_inactive
        )
        
        return cleaned_count
    
    def get_vapid_public_key(self) -> Optional[str]:
        """Get the VAPID public key for client-side subscription."""
        return self.config.vapid_public_key
    
    async def test_subscription(
        self,
        subscription_id: str,
        user_id: int,
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Send a test push notification to verify the subscription works."""
        
        if not session:
            async with get_db_session() as session:
                return await self._test_subscription_impl(subscription_id, user_id, session)
        else:
            return await self._test_subscription_impl(subscription_id, user_id, session)
    
    async def _test_subscription_impl(
        self,
        subscription_id: str,
        user_id: int,
        session: AsyncSession
    ) -> bool:
        """Internal implementation of test_subscription."""
        
        query = select(PushSubscription).where(
            and_(
                PushSubscription.id == subscription_id,
                PushSubscription.user_id == user_id,
                PushSubscription.is_active == True
            )
        )
        
        result = await session.execute(query)
        subscription = result.scalar_one_or_none()
        
        if not subscription:
            return False
        
        return await self.send_push_notification(
            subscription=subscription,
            title="Test Notification",
            body="This is a test notification from Study Assistant",
            data={"test": True, "timestamp": datetime.utcnow().isoformat()},
            session=session
        )


# Global push notification service instance
push_notification_service = PushNotificationService()
