"""
Content analytics service for tracking engagement metrics.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, Integer as SQLInteger
from fastapi import HTTPException, status

from models.models import (
    ContentAnalytics, ContentTypeEnum, ContentComment, ContentRating, Summary, McqQuiz, PhysicalFile
)
from schemas.analytics import (
    ContentAnalyticsRead, AnalyticsIncrement, ContentAnalyticsSummary,
    AnalyticsDashboard, ContentEngagementMetrics
)


class ContentAnalyticsService:
    """Service for managing content analytics and engagement metrics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _ensure_analytics_record(self, content_type: ContentTypeEnum, content_id: int) -> ContentAnalytics:
        """Ensure analytics record exists for content."""
        stmt = select(ContentAnalytics).where(
            ContentAnalytics.content_type == content_type,
            ContentAnalytics.content_id == content_id
        )
        result = await self.db.execute(stmt)
        analytics = result.scalar_one_or_none()

        if not analytics:
            analytics = ContentAnalytics(
                content_type=content_type,
                content_id=content_id,
                view_count=0,
                like_count=0,
                share_count=0,
                comment_count=0
            )
            self.db.add(analytics)
            await self.db.commit()
            await self.db.refresh(analytics)

        return analytics

    async def _verify_content_exists(self, content_type: ContentTypeEnum, content_id: int) -> bool:
        """Verify that content exists."""
        if content_type == ContentTypeEnum.summary:
            stmt = select(Summary).where(Summary.id == content_id)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none() is not None
        elif content_type == ContentTypeEnum.quiz:
            stmt = select(McqQuiz).where(McqQuiz.id == content_id)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none() is not None
        elif content_type == ContentTypeEnum.file:
            stmt = select(PhysicalFile).where(PhysicalFile.id == content_id)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none() is not None
        return False

    async def increment_metric(
        self,
        content_type: ContentTypeEnum,
        content_id: int,
        metric: str,
        increment: int = 1
    ) -> ContentAnalyticsRead:
        """Increment a specific metric for content."""
        # Verify content exists
        if not await self._verify_content_exists(content_type, content_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{content_type.value.title()} not found"
            )

        # Ensure analytics record exists
        analytics = await self._ensure_analytics_record(content_type, content_id)

        # Increment the specified metric
        if metric == "view":
            analytics.view_count += increment
        elif metric == "like":
            analytics.like_count += increment
        elif metric == "share":
            analytics.share_count += increment
        elif metric == "comment":
            analytics.comment_count += increment
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid metric: {metric}"
            )

        analytics.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(analytics)

        return ContentAnalyticsRead.from_orm(analytics)

    async def get_analytics(
        self,
        content_type: ContentTypeEnum,
        content_id: int
    ) -> ContentAnalyticsRead:
        """Get analytics for specific content."""
        if not await self._verify_content_exists(content_type, content_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{content_type.value.title()} not found"
            )

        analytics = await self._ensure_analytics_record(content_type, content_id)
        return ContentAnalyticsRead.from_orm(analytics)

    def calculate_engagement_score(self, analytics: ContentAnalytics) -> float:
        """Calculate engagement score based on all metrics."""
        # Weighted scoring system
        weights = {
            "view": 1.0,
            "like": 2.0,
            "comment": 3.0,
            "share": 5.0
        }

        score = (
            analytics.view_count * weights["view"] +
            analytics.like_count * weights["like"] +
            analytics.comment_count * weights["comment"] +
            analytics.share_count * weights["share"]
        )

        # Normalize score (could be adjusted based on domain knowledge)
        if analytics.view_count > 0:
            engagement_rate = score / (analytics.view_count * sum(weights.values()))
            return min(engagement_rate * 100, 100.0)  # Cap at 100%
        
        return 0.0

    async def get_content_engagement_metrics(
        self,
        content_type: ContentTypeEnum,
        content_id: int
    ) -> ContentEngagementMetrics:
        """Get detailed engagement metrics for content."""
        if not await self._verify_content_exists(content_type, content_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{content_type.value.title()} not found"
            )

        analytics = await self._ensure_analytics_record(content_type, content_id)

        # Calculate derived metrics
        engagement_rate = self.calculate_engagement_score(analytics)
        view_to_comment_ratio = (
            analytics.comment_count / analytics.view_count
            if analytics.view_count > 0 else 0.0
        )

        # Get average rating if available
        rating_stmt = select(ContentRating.rating).where(
            ContentRating.content_type == content_type,
            ContentRating.content_id == content_id
        )
        rating_result = await self.db.execute(rating_stmt)
        rating_values = rating_result.scalars().all()
        
        average_rating = None
        if rating_values:
            # Calculate average manually from enum values
            total = sum(int(rating.value) for rating in rating_values)
            average_rating = total / len(rating_values)

        # Calculate time-based metrics (simplified for now)
        now = datetime.now(timezone.utc)
        views_last_24h = analytics.view_count  # Simplified - would need view tracking table
        views_last_7d = analytics.view_count   # Simplified
        views_last_30d = analytics.view_count  # Simplified

        # Calculate trend (simplified)
        trend_direction = "stable"
        trend_percentage = 0.0

        return ContentEngagementMetrics(
            content_type=content_type,
            content_id=content_id,
            views=analytics.view_count,
            likes=analytics.like_count,
            comments=analytics.comment_count,
            shares=analytics.share_count,
            engagement_rate=engagement_rate,
            view_to_comment_ratio=view_to_comment_ratio,
            average_rating=float(average_rating) if average_rating else None,
            views_last_24h=views_last_24h,
            views_last_7d=views_last_7d,
            views_last_30d=views_last_30d,
            trend_direction=trend_direction,
            trend_percentage=trend_percentage
        )

    async def get_top_content(
        self,
        content_type: Optional[ContentTypeEnum] = None,
        limit: int = 10,
        metric: str = "engagement"
    ) -> List[ContentAnalyticsSummary]:
        """Get top performing content based on specified metric."""
        stmt = select(ContentAnalytics)
        
        if content_type:
            stmt = stmt.where(ContentAnalytics.content_type == content_type)

        # Order by specified metric
        if metric == "views":
            stmt = stmt.order_by(desc(ContentAnalytics.view_count))
        elif metric == "likes":
            stmt = stmt.order_by(desc(ContentAnalytics.like_count))
        elif metric == "comments":
            stmt = stmt.order_by(desc(ContentAnalytics.comment_count))
        elif metric == "shares":
            stmt = stmt.order_by(desc(ContentAnalytics.share_count))
        else:  # engagement (default)
            # Order by calculated engagement score
            stmt = stmt.order_by(
                desc(
                    ContentAnalytics.view_count +
                    ContentAnalytics.like_count * 2 +
                    ContentAnalytics.comment_count * 3 +
                    ContentAnalytics.share_count * 5
                )
            )

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        analytics_list = result.scalars().all()
        
        # Convert to summary format
        summaries = []
        for i, analytics in enumerate(analytics_list, 1):
            engagement_score = self.calculate_engagement_score(analytics)
            
            summary = ContentAnalyticsSummary(
                content_type=analytics.content_type,
                content_id=analytics.content_id,
                analytics=ContentAnalyticsRead.from_orm(analytics),
                engagement_score=engagement_score,
                popularity_rank=i
            )
            summaries.append(summary)

        return summaries

    async def get_dashboard_analytics(self, user_id: Optional[int] = None) -> AnalyticsDashboard:
        """Get dashboard analytics with aggregated metrics."""
        # If user_id provided, filter by user's content
        if user_id:
            # This would require joining with content tables to filter by user
            # For now, return all analytics
            pass

        # Calculate totals
        totals_stmt = select(
            func.count(ContentAnalytics.content_type).label('total_content'),
            func.sum(ContentAnalytics.view_count).label('total_views'),
            func.sum(ContentAnalytics.like_count).label('total_likes'),
            func.sum(ContentAnalytics.comment_count).label('total_comments'),
            func.sum(ContentAnalytics.share_count).label('total_shares')
        )
        totals_result = await self.db.execute(totals_stmt)
        totals = totals_result.first()

        # Get top content
        top_content = await self.get_top_content(limit=5)

        # Get recent activity (simplified)
        recent_stmt = select(ContentAnalytics).order_by(desc(ContentAnalytics.updated_at)).limit(10)
        recent_result = await self.db.execute(recent_stmt)
        recent_analytics = recent_result.scalars().all()
        
        recent_activity = [
            {
                "content_type": a.content_type.value,
                "content_id": a.content_id,
                "metric_updated": "general",
                "timestamp": a.updated_at.isoformat(),
                "engagement_score": self.calculate_engagement_score(a)
            }
            for a in recent_analytics
        ]

        return AnalyticsDashboard(
            total_content=totals.total_content or 0,
            total_views=totals.total_views or 0,
            total_likes=totals.total_likes or 0,
            total_comments=totals.total_comments or 0,
            total_shares=totals.total_shares or 0,
            top_content=top_content,
            recent_activity=recent_activity,
            period_comparison={}  # Would implement with historical data
        )

    async def sync_comment_counts(self):
        """Synchronize comment counts with actual comment data."""
        # Get all content with comments
        comment_counts_stmt = select(
            ContentComment.content_type,
            ContentComment.content_id,
            func.count(ContentComment.id).label('count')
        ).where(
            ContentComment.is_deleted == False
        ).group_by(
            ContentComment.content_type,
            ContentComment.content_id
        )
        
        comment_counts_result = await self.db.execute(comment_counts_stmt)
        comment_counts = comment_counts_result.all()

        for content_type, content_id, count in comment_counts:
            analytics = await self._ensure_analytics_record(content_type, content_id)
            analytics.comment_count = count
            analytics.updated_at = datetime.now(timezone.utc)

        await self.db.commit()

    async def cleanup_orphaned_analytics(self):
        """Remove analytics records for content that no longer exists."""
        orphaned_count = 0
        
        # Check each analytics record
        analytics_stmt = select(ContentAnalytics)
        analytics_result = await self.db.execute(analytics_stmt)
        analytics_records = analytics_result.scalars().all()
        
        for analytics in analytics_records:
            if not await self._verify_content_exists(analytics.content_type, analytics.content_id):
                await self.db.delete(analytics)
                orphaned_count += 1
        
        await self.db.commit()
        return orphaned_count 