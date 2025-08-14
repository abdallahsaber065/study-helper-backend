"""
Service layer for usage tracking and quota management.
"""

import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import QuotaHistory, UsageRecord, UserQuota
from .schemas import (
    BillingPeriodResponse,
    OperationType,
    QuotaCheckResponse,
    QuotaHistoryResponse,
    QuotaResponse,
    UsageFilters,
    UsageListResponse,
    UsageRecordCreate,
    UsageResponse,
    UsageStatsResponse,
    UsageStatus,
)

logger = logging.getLogger(__name__)


class QuotaManager:
    """Service for managing user quotas and limits."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_quota(
        self, user_id: int, quota_month: Optional[date] = None
    ) -> UserQuota:
        """Get or create quota record for user and month."""
        if quota_month is None:
            quota_month = date.today().replace(day=1)

        # Try to get existing quota
        stmt = select(UserQuota).where(
            and_(
                UserQuota.user_id == user_id,
                UserQuota.quota_month == quota_month,
            )
        )
        result = await self.db.execute(stmt)
        quota = result.scalar_one_or_none()

        if not quota:
            # Create new quota with default limits
            quota = UserQuota(
                user_id=user_id,
                quota_month=quota_month,
                **self._get_default_limits(is_premium=False)
            )
            self.db.add(quota)
            await self.db.commit()
            await self.db.refresh(quota)

            logger.info(f"Created quota for user {user_id}, month {quota_month}")

        return quota

    async def check_quota_availability(
        self,
        user_id: int,
        operation_type: OperationType,
        estimated_tokens: int = 0,
        estimated_cost: Decimal = Decimal("0.00"),
    ) -> QuotaCheckResponse:
        """Check if user has quota available for an operation."""
        quota = await self.get_or_create_quota(user_id)

        # Check token availability
        tokens_available = quota.can_use_tokens(estimated_tokens)
        tokens_shortfall = None
        if not tokens_available:
            tokens_shortfall = (quota.tokens_used + estimated_tokens) - quota.token_limit

        # Check cost availability
        cost_available = quota.can_afford_cost(estimated_cost)
        cost_shortfall = None
        if not cost_available:
            cost_shortfall = (quota.cost_used + estimated_cost) - quota.cost_limit

        # Check operation-specific limits
        operation_available = True
        operations_remaining = 0

        if operation_type == OperationType.SUMMARY:
            operation_available = quota.can_create_summary()
            operations_remaining = quota.summaries_remaining
        elif operation_type == OperationType.QUIZ:
            operation_available = quota.can_create_quiz()
            operations_remaining = quota.quizzes_remaining

        # Overall availability
        can_proceed = tokens_available and cost_available and operation_available

        # Determine reason if cannot proceed
        reason = None
        if not can_proceed:
            reasons = []
            if not tokens_available:
                reasons.append(f"Token limit exceeded (need {estimated_tokens}, have {quota.tokens_remaining})")
            if not cost_available:
                reasons.append(f"Cost limit exceeded (need ${estimated_cost}, have ${quota.cost_remaining})")
            if not operation_available:
                reasons.append(f"Operation limit exceeded for {operation_type.value}")
            reason = "; ".join(reasons)

        return QuotaCheckResponse(
            can_proceed=can_proceed,
            reason=reason,
            tokens_available=tokens_available,
            cost_available=cost_available,
            operation_available=operation_available,
            tokens_remaining=quota.tokens_remaining,
            cost_remaining=quota.cost_remaining,
            operations_remaining=operations_remaining,
            tokens_required=estimated_tokens if estimated_tokens > 0 else None,
            cost_required=estimated_cost if estimated_cost > 0 else None,
            tokens_shortfall=tokens_shortfall,
            cost_shortfall=cost_shortfall,
        )

    async def update_quota_limits(
        self,
        user_id: int,
        token_limit: Optional[int] = None,
        cost_limit: Optional[Decimal] = None,
        summary_limit: Optional[int] = None,
        quiz_limit: Optional[int] = None,
        is_premium: Optional[bool] = None,
        changed_by: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> UserQuota:
        """Update quota limits for a user."""
        quota = await self.get_or_create_quota(user_id)

        # Track changes for audit
        changes = []

        if token_limit is not None and token_limit != quota.token_limit:
            changes.append(("token_limit", str(quota.token_limit), str(token_limit)))
            quota.token_limit = token_limit

        if cost_limit is not None and cost_limit != quota.cost_limit:
            changes.append(("cost_limit", str(quota.cost_limit), str(cost_limit)))
            quota.cost_limit = cost_limit

        if summary_limit is not None and summary_limit != quota.summary_limit:
            changes.append(("summary_limit", str(quota.summary_limit), str(summary_limit)))
            quota.summary_limit = summary_limit

        if quiz_limit is not None and quiz_limit != quota.quiz_limit:
            changes.append(("quiz_limit", str(quota.quiz_limit), str(quiz_limit)))
            quota.quiz_limit = quiz_limit

        if is_premium is not None and is_premium != quota.is_premium:
            changes.append(("is_premium", str(quota.is_premium), str(is_premium)))
            quota.is_premium = is_premium

        # Save changes
        if changes:
            await self.db.commit()
            await self.db.refresh(quota)

            # Record quota history
            for field, old_value, new_value in changes:
                history = QuotaHistory(
                    user_id=user_id,
                    quota_id=quota.id,
                    change_type="adjustment",
                    field_changed=field,
                    old_value=old_value,
                    new_value=new_value,
                    reason=reason,
                    changed_by=changed_by,
                )
                self.db.add(history)

            await self.db.commit()

            logger.info(
                f"Updated quota limits for user {user_id}: {len(changes)} changes"
            )

        return quota

    async def reset_monthly_quota(self, user_id: int, quota_month: date) -> UserQuota:
        """Reset usage counters for a new billing period."""
        quota = await self.get_or_create_quota(user_id, quota_month)

        # Reset usage counters
        quota.tokens_used = 0
        quota.cost_used = Decimal("0.00")
        quota.summaries_used = 0
        quota.quizzes_used = 0

        await self.db.commit()
        await self.db.refresh(quota)

        # Record reset in history
        history = QuotaHistory(
            user_id=user_id,
            quota_id=quota.id,
            change_type="reset",
            field_changed="usage_counters",
            old_value="non-zero",
            new_value="zero",
            reason="Monthly quota reset",
        )
        self.db.add(history)
        await self.db.commit()

        logger.info(f"Reset monthly quota for user {user_id}, month {quota_month}")
        return quota

    async def get_quota_history(
        self, user_id: int, limit: int = 50
    ) -> List[QuotaHistoryResponse]:
        """Get quota change history for a user."""
        stmt = (
            select(QuotaHistory)
            .where(QuotaHistory.user_id == user_id)
            .order_by(desc(QuotaHistory.created_at))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        history_records = result.scalars().all()

        return [QuotaHistoryResponse.from_orm(record) for record in history_records]

    async def get_billing_period_info(self, user_id: int) -> BillingPeriodResponse:
        """Get current billing period information."""
        today = date.today()
        current_period = today.replace(day=1)

        # Calculate period end
        last_day = monthrange(current_period.year, current_period.month)[1]
        period_end = current_period.replace(day=last_day)

        # Calculate next reset date
        next_month = current_period.replace(day=28) + timedelta(days=4)
        next_reset_date = next_month.replace(day=1)

        # Days remaining in current period
        days_remaining = (period_end - today).days + 1

        return BillingPeriodResponse(
            current_period=current_period,
            period_start=current_period,
            period_end=period_end,
            days_remaining=days_remaining,
            next_reset_date=next_reset_date,
            auto_reset=True,
        )

    def _get_default_limits(self, is_premium: bool = False) -> Dict:
        """Get default quota limits based on user type."""
        if is_premium:
            return {
                "token_limit": 1000000,
                "cost_limit": Decimal("500.00"),
                "summary_limit": 1000,
                "quiz_limit": 500,
            }
        else:
            return {
                "token_limit": 100000,
                "cost_limit": Decimal("50.00"),
                "summary_limit": 100,
                "quiz_limit": 50,
            }


class UsageTracker:
    """Service for tracking AI usage and costs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_usage(
        self, user_id: int, usage_data: UsageRecordCreate
    ) -> UsageRecord:
        """Record a new usage entry and update quotas."""
        
        # Create usage record
        usage_record = UsageRecord(
            user_id=user_id,
            **usage_data.dict()
        )
        self.db.add(usage_record)

        # Update quota usage
        quota_manager = QuotaManager(self.db)
        quota = await quota_manager.get_or_create_quota(user_id)

        # Add usage to quota
        operation_count = 1 if usage_data.status == UsageStatus.SUCCESS else 0
        summaries_used = operation_count if usage_data.operation_type == OperationType.SUMMARY else 0
        quizzes_used = operation_count if usage_data.operation_type == OperationType.QUIZ else 0

        quota.add_usage(
            tokens=usage_data.total_tokens,
            cost=usage_data.cost,
            summaries=summaries_used,
            quizzes=quizzes_used,
        )

        await self.db.commit()
        await self.db.refresh(usage_record)

        logger.info(
            f"Recorded usage for user {user_id}: {usage_data.total_tokens} tokens, ${usage_data.cost}"
        )

        return usage_record

    async def get_usage_records(
        self, user_id: int, filters: UsageFilters
    ) -> UsageListResponse:
        """Get paginated usage records with filters."""
        
        # Base query
        query = select(UsageRecord).where(UsageRecord.user_id == user_id)

        # Apply filters
        if filters.operation_types:
            query = query.where(UsageRecord.operation_type.in_([op.value for op in filters.operation_types]))
        
        if filters.ai_providers:
            query = query.where(UsageRecord.ai_provider.in_(filters.ai_providers))
        
        if filters.statuses:
            query = query.where(UsageRecord.status.in_([status.value for status in filters.statuses]))
        
        if filters.date_from:
            query = query.where(UsageRecord.created_at >= filters.date_from)
        
        if filters.date_to:
            # Include full day
            query = query.where(UsageRecord.created_at <= filters.date_to + timedelta(days=1))
        
        if filters.min_cost:
            query = query.where(UsageRecord.cost >= filters.min_cost)
        
        if filters.max_cost:
            query = query.where(UsageRecord.cost <= filters.max_cost)
        
        if filters.min_tokens:
            query = query.where(UsageRecord.total_tokens >= filters.min_tokens)
        
        if filters.max_tokens:
            query = query.where(UsageRecord.total_tokens <= filters.max_tokens)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Apply sorting
        if filters.sort_by == "created_at":
            sort_column = UsageRecord.created_at
        elif filters.sort_by == "cost":
            sort_column = UsageRecord.cost
        elif filters.sort_by == "tokens":
            sort_column = UsageRecord.total_tokens
        else:
            sort_column = UsageRecord.created_at

        if filters.sort_order == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(sort_column)

        # Apply pagination
        offset = (filters.page - 1) * filters.page_size
        query = query.offset(offset).limit(filters.page_size)

        # Execute query
        result = await self.db.execute(query)
        usage_records = result.scalars().all()

        # Calculate total pages
        total_pages = (total + filters.page_size - 1) // filters.page_size

        return UsageListResponse(
            usage_records=[UsageResponse.from_orm(record) for record in usage_records],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
        )

    async def get_usage_statistics(
        self,
        user_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> UsageStatsResponse:
        """Get usage statistics for a user and time period."""
        
        if date_from is None:
            date_from = date.today().replace(day=1)  # Start of current month
        
        if date_to is None:
            date_to = date.today()

        # Base query
        query = select(UsageRecord).where(
            and_(
                UsageRecord.user_id == user_id,
                UsageRecord.created_at >= date_from,
                UsageRecord.created_at <= date_to + timedelta(days=1),
            )
        )

        result = await self.db.execute(query)
        records = result.scalars().all()

        # Calculate statistics
        total_operations = len(records)
        total_tokens = sum(record.total_tokens for record in records)
        total_cost = sum(record.cost for record in records)

        # Group by operation type
        operations_by_type = {}
        tokens_by_type = {}
        cost_by_type = {}

        for record in records:
            op_type = record.operation_type
            operations_by_type[op_type] = operations_by_type.get(op_type, 0) + 1
            tokens_by_type[op_type] = tokens_by_type.get(op_type, 0) + record.total_tokens
            cost_by_type[op_type] = cost_by_type.get(op_type, Decimal("0.00")) + record.cost

        # Group by provider
        operations_by_provider = {}
        tokens_by_provider = {}
        cost_by_provider = {}

        for record in records:
            provider = record.ai_provider
            operations_by_provider[provider] = operations_by_provider.get(provider, 0) + 1
            tokens_by_provider[provider] = tokens_by_provider.get(provider, 0) + record.total_tokens
            cost_by_provider[provider] = cost_by_provider.get(provider, Decimal("0.00")) + record.cost

        # Calculate averages
        successful_records = [r for r in records if r.status == "success"]
        
        processing_times = [r.processing_time_ms for r in successful_records if r.processing_time_ms]
        average_processing_time_ms = sum(processing_times) / len(processing_times) if processing_times else None

        success_rate = len(successful_records) / total_operations if total_operations > 0 else 0

        quality_scores = [r.quality_score for r in successful_records if r.quality_score]
        average_quality_score = float(sum(quality_scores) / len(quality_scores)) if quality_scores else None

        user_ratings = [r.user_rating for r in successful_records if r.user_rating]
        average_user_rating = sum(user_ratings) / len(user_ratings) if user_ratings else None

        return UsageStatsResponse(
            period_start=date_from,
            period_end=date_to,
            total_operations=total_operations,
            total_tokens=total_tokens,
            total_cost=total_cost,
            operations_by_type=operations_by_type,
            tokens_by_type=tokens_by_type,
            cost_by_type=cost_by_type,
            operations_by_provider=operations_by_provider,
            tokens_by_provider=tokens_by_provider,
            cost_by_provider=cost_by_provider,
            average_processing_time_ms=average_processing_time_ms,
            success_rate=success_rate,
            average_quality_score=average_quality_score,
            average_user_rating=average_user_rating,
        )
