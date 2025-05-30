"""
Notification service for managing user notifications.
"""
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from models.models import (
    User, Notification, Community, ContentTypeEnum, 
    NotificationTypeEnum, Summary, McqQuiz
)
from schemas.notification import NotificationCreate, NotificationRead


class NotificationService:
    """Service for managing user notifications."""

    def __init__(self, db: Session):
        self.db = db

    def create_notification(
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
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def notify_new_community_content(
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
        members = self.db.query(CommunityMember).filter(
            CommunityMember.community_id == community_id,
            CommunityMember.user_id != actor_id
        ).all()
        
        # Get community name
        community = self.db.query(Community).filter(Community.id == community_id).first()
        community_name = community.name if community else "Unknown Community"
        
        content_type_str = content_type.value
        message = f"New {content_type_str} '{content_title}' was added to {community_name}"
        
        for member in members:
            self.create_notification(
                user_id=member.user_id,
                notification_type=NotificationTypeEnum.new_content,
                message=message,
                actor_id=actor_id,
                related_content_type=content_type,
                related_content_id=content_id,
                related_community_id=community_id,
            )

    def notify_comment_reply(
        self,
        original_comment_author_id: int,
        reply_author_id: int,
        content_type: ContentTypeEnum,
        content_id: int,
        reply_text: str
    ):
        """Notify user when someone replies to their comment."""
        reply_author = self.db.query(User).filter(User.id == reply_author_id).first()
        actor_name = f"{reply_author.first_name} {reply_author.last_name}" if reply_author else "Someone"
        
        preview_text = reply_text[:50] + "..." if len(reply_text) > 50 else reply_text
        message = f"{actor_name} replied to your comment: {preview_text}"
        
        self.create_notification(
            user_id=original_comment_author_id,
            notification_type=NotificationTypeEnum.comment_reply,
            message=message,
            actor_id=reply_author_id,
            related_content_type=content_type,
            related_content_id=content_id,
        )

    def notify_quiz_result(
        self,
        user_id: int,
        quiz_id: int,
        score: int,
        total_questions: int
    ):
        """Notify user about quiz completion results."""
        quiz = self.db.query(McqQuiz).filter(McqQuiz.id == quiz_id).first()
        quiz_title = quiz.title if quiz else "Quiz"
        
        percentage = round((score / total_questions) * 100) if total_questions > 0 else 0
        message = f"Quiz '{quiz_title}' completed! Score: {score}/{total_questions} ({percentage}%)"
        
        self.create_notification(
            user_id=user_id,
            notification_type=NotificationTypeEnum.quiz_result,
            message=message,
            related_content_type=ContentTypeEnum.quiz,
            related_content_id=quiz_id,
        )

    def notify_community_invite(
        self,
        user_id: int,
        community_id: int,
        inviter_id: int
    ):
        """Notify user about community invitation."""
        community = self.db.query(Community).filter(Community.id == community_id).first()
        inviter = self.db.query(User).filter(User.id == inviter_id).first()
        
        community_name = community.name if community else "Unknown Community"
        inviter_name = f"{inviter.first_name} {inviter.last_name}" if inviter else "Someone"
        
        message = f"{inviter_name} invited you to join '{community_name}'"
        
        self.create_notification(
            user_id=user_id,
            notification_type=NotificationTypeEnum.community_invite,
            message=message,
            actor_id=inviter_id,
            related_community_id=community_id,
        )

    def get_user_notifications(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
        unread_only: bool = False
    ) -> tuple[List[NotificationRead], int, int]:
        """Get user notifications with pagination."""
        query = self.db.query(Notification).options(
            joinedload(Notification.actor_user),
            joinedload(Notification.related_community)
        ).filter(Notification.user_id == user_id)
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        # Get total count
        total_count = query.count()
        
        # Get unread count
        unread_count = self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).count()
        
        # Get paginated results
        notifications = query.order_by(
            Notification.created_at.desc()
        ).offset(skip).limit(limit).all()
        
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

    def mark_notifications_read(
        self,
        user_id: int,
        notification_ids: Optional[List[int]] = None
    ) -> int:
        """Mark notifications as read. If no IDs provided, marks all user's notifications as read."""
        query = self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        )
        
        if notification_ids:
            query = query.filter(Notification.id.in_(notification_ids))
        
        updated_count = query.update(
            {Notification.is_read: True, Notification.updated_at: datetime.now(timezone.utc)},
            synchronize_session=False
        )
        
        self.db.commit()
        return updated_count

    def delete_notification(self, notification_id: int, user_id: int) -> bool:
        """Delete a notification (only by the recipient)."""
        notification = self.db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id
        ).first()
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        self.db.delete(notification)
        self.db.commit()
        return True 