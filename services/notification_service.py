"""
Notification service for managing user notifications.
"""
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, func
from fastapi import HTTPException, status

from models.models import (
    User, Notification, Community, ContentTypeEnum, 
    NotificationTypeEnum, Summary, McqQuiz
)
from schemas.notification import NotificationCreate, NotificationRead


class NotificationService:
    """Service for managing user notifications."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(
        self,
        user_id: int,
        notification_type: NotificationTypeEnum,
        message: str,
        actor_id: Optional[int] = None,
        related_content_type: Optional[ContentTypeEnum] = None,
        related_content_id: Optional[int] = None,
        related_community_id: Optional[int] = None,
    ) -> Notification:
        """Create a new notification."""
        
        # Don't create notifications for users notifying themselves
        if actor_id and user_id == actor_id:
            return None
            
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            message=message,
            actor_id=actor_id,
            related_content_type=related_content_type,
            related_content_id=related_content_id,
            related_community_id=related_community_id,
        )
        
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def notify_new_community_content(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        community_id: int,
        actor_id: int,
        content_title: str
    ):
        """Notify community members about new content."""
        from models.models import CommunityMember
        
        # Get all community members except the actor
        members_stmt = select(CommunityMember).where(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id != actor_id
        )
        members_result = await self.db.execute(members_stmt)
        members = members_result.scalars().all()
        
        # Get community name
        community_stmt = select(Community).where(Community.id == community_id)
        community_result = await self.db.execute(community_stmt)
        community = community_result.scalar_one_or_none()
        community_name = community.name if community else "Unknown Community"
        
        content_type_str = content_type.value
        message = f"New {content_type_str} '{content_title}' was added to {community_name}"
        
        for member in members:
            await self.create_notification(
                user_id=member.user_id,
                notification_type=NotificationTypeEnum.new_content,
                message=message,
                actor_id=actor_id,
                related_content_type=content_type,
                related_content_id=content_id,
                related_community_id=community_id,
            )

    async def notify_comment_reply(
        self,
        original_comment_author_id: int,
        reply_author_id: int,
        content_type: ContentTypeEnum,
        content_id: int,
        reply_text: str
    ):
        """Notify user when someone replies to their comment."""
        reply_author_stmt = select(User).where(User.id == reply_author_id)
        reply_author_result = await self.db.execute(reply_author_stmt)
        reply_author = reply_author_result.scalar_one_or_none()
        actor_name = f"{reply_author.first_name} {reply_author.last_name}" if reply_author else "Someone"
        
        preview_text = reply_text[:50] + "..." if len(reply_text) > 50 else reply_text
        message = f"{actor_name} replied to your comment: {preview_text}"
        
        await self.create_notification(
            user_id=original_comment_author_id,
            notification_type=NotificationTypeEnum.comment_reply,
            message=message,
            actor_id=reply_author_id,
            related_content_type=content_type,
            related_content_id=content_id,
        )

    async def notify_quiz_result(
        self,
        user_id: int,
        quiz_id: int,
        score: int,
        total_questions: int
    ):
        """Notify user about quiz completion results."""
        quiz_stmt = select(McqQuiz).where(McqQuiz.id == quiz_id)
        quiz_result = await self.db.execute(quiz_stmt)
        quiz = quiz_result.scalar_one_or_none()
        quiz_title = quiz.title if quiz else "Quiz"
        
        percentage = round((score / total_questions) * 100) if total_questions > 0 else 0
        message = f"Quiz '{quiz_title}' completed! Score: {score}/{total_questions} ({percentage}%)"
        
        await self.create_notification(
            user_id=user_id,
            notification_type=NotificationTypeEnum.quiz_result,
            message=message,
            related_content_type=ContentTypeEnum.quiz,
            related_content_id=quiz_id,
        )

    async def notify_community_invite(
        self,
        user_id: int,
        community_id: int,
        inviter_id: int
    ):
        """Notify user about community invitation."""
        community_stmt = select(Community).where(Community.id == community_id)
        community_result = await self.db.execute(community_stmt)
        community = community_result.scalar_one_or_none()
        
        inviter_stmt = select(User).where(User.id == inviter_id)
        inviter_result = await self.db.execute(inviter_stmt)
        inviter = inviter_result.scalar_one_or_none()
        
        community_name = community.name if community else "Unknown Community"
        inviter_name = f"{inviter.first_name} {inviter.last_name}" if inviter else "Someone"
        
        message = f"{inviter_name} invited you to join '{community_name}'"
        
        await self.create_notification(
            user_id=user_id,
            notification_type=NotificationTypeEnum.community_invite,
            message=message,
            actor_id=inviter_id,
            related_community_id=community_id,
        )

    async def get_user_notifications(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
        unread_only: bool = False
    ) -> tuple[List[NotificationRead], int, int]:
        """Get user notifications with pagination."""
        
        # Build base query
        base_stmt = select(Notification).options(
            selectinload(Notification.actor_user),
            selectinload(Notification.related_community)
        ).where(Notification.user_id == user_id)
        
        if unread_only:
            base_stmt = base_stmt.where(Notification.is_read == False)
        
        # Get total count
        count_stmt = select(func.count(Notification.id)).where(Notification.user_id == user_id)
        if unread_only:
            count_stmt = count_stmt.where(Notification.is_read == False)
        
        count_result = await self.db.execute(count_stmt)
        total_count = count_result.scalar()
        
        # Get unread count
        unread_count_stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.is_read == False
        )
        unread_count_result = await self.db.execute(unread_count_stmt)
        unread_count = unread_count_result.scalar()
        
        # Get paginated results
        notifications_stmt = base_stmt.order_by(
            Notification.created_at.desc()
        ).offset(skip).limit(limit)
        
        notifications_result = await self.db.execute(notifications_stmt)
        notifications = notifications_result.scalars().all()
        
        # Convert to read schemas
        notification_reads = []
        for notif in notifications:
            notification_read = NotificationRead.from_orm(notif)
            
            # Add actor details
            if notif.actor_user:
                notification_read.actor_username = notif.actor_user.username
                notification_read.actor_first_name = notif.actor_user.first_name
                notification_read.actor_last_name = notif.actor_user.last_name
            
            # Add community details
            if notif.related_community:
                notification_read.community_name = notif.related_community.name
            
            notification_reads.append(notification_read)
        
        return notification_reads, total_count, unread_count

    async def mark_notifications_read(
        self,
        user_id: int,
        notification_ids: Optional[List[int]] = None
    ) -> int:
        """Mark notifications as read."""
        if notification_ids:
            # Mark specific notifications as read
            stmt = update(Notification).where(
                Notification.user_id == user_id,
                Notification.id.in_(notification_ids)
            ).values(is_read=True, updated_at=datetime.now(timezone.utc))
        else:
            # Mark all user's notifications as read
            stmt = update(Notification).where(
                Notification.user_id == user_id
            ).values(is_read=True, updated_at=datetime.now(timezone.utc))
        
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def delete_notification(self, notification_id: int, user_id: int) -> bool:
        """Delete a notification."""
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id
        )
        result = await self.db.execute(stmt)
        notification = result.scalar_one_or_none()
        
        if not notification:
            return False
        
        await self.db.delete(notification)
        await self.db.commit()
        return True 