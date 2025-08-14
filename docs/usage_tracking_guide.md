# Usage Tracking & Quota Management Guide

## Overview

The Study Assistant backend includes comprehensive usage tracking and quota management to monitor AI API costs, enforce usage limits, and provide detailed analytics for both users and administrators.

## Features

- **Real-time Usage Tracking**: Monitor every AI operation with detailed metrics
- **Flexible Quota Management**: Monthly limits for tokens, costs, and operations
- **Cost Tracking**: Accurate billing and cost estimation for AI providers
- **Analytics Dashboard**: Comprehensive usage statistics and trends
- **Premium Tiers**: Support for different subscription plans
- **Admin Controls**: Administrative tools for quota management

## Architecture

### Database Models

#### UserQuota

Tracks monthly quotas and usage for each user:

```python
class UserQuota(Base):
    user_id: int
    quota_month: date  # YYYY-MM-01 format
    
    # Limits
    token_limit: int = 100000  # Default free tier
    cost_limit: Decimal = 50.00  # USD
    summary_limit: int = 100
    quiz_limit: int = 50
    
    # Usage counters
    tokens_used: int = 0
    cost_used: Decimal = 0.00
    summaries_used: int = 0
    quizzes_used: int = 0
    
    # Premium status
    is_premium: bool = False
```

#### UsageRecord

Detailed tracking of individual AI operations:

```python
class UsageRecord(Base):
    user_id: int
    operation_type: str  # summary, quiz, analysis
    resource_id: str     # summary_id, quiz_id
    
    # AI provider details
    ai_provider: str     # openai, gemini, anthropic
    ai_model: str        # gpt-4o, gemini-2.0-flash
    
    # Usage metrics
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: Decimal
    
    # Performance metrics
    processing_time_ms: int
    quality_score: Decimal
    user_rating: int
```

#### QuotaHistory

Audit trail for quota changes:

```python
class QuotaHistory(Base):
    user_id: int
    change_type: str     # upgrade, downgrade, reset
    field_changed: str   # token_limit, cost_limit
    old_value: str
    new_value: str
    reason: str
    changed_by: int      # Admin user ID
```

## API Endpoints

### Quota Management

#### Get Current Quota

```http
GET /usage/quota

Response:
{
    "id": "quota-uuid",
    "user_id": 123,
    "quota_month": "2025-01-01",
    "token_limit": 100000,
    "tokens_used": 25000,
    "tokens_remaining": 75000,
    "token_usage_percentage": 25.0,
    "cost_limit": "50.00",
    "cost_used": "12.50",
    "cost_remaining": "37.50",
    "is_premium": false
}
```

#### Check Quota Availability

```http
POST /usage/quota/check?operation_type=summary&estimated_tokens=4000&estimated_cost=0.10

Response:
{
    "can_proceed": true,
    "tokens_available": true,
    "cost_available": true,
    "operation_available": true,
    "tokens_remaining": 96000,
    "cost_remaining": "49.90"
}
```

### Usage Analytics

#### Get Usage Statistics

```http
GET /usage/statistics?date_from=2025-01-01&date_to=2025-01-31

Response:
{
    "period_start": "2025-01-01",
    "period_end": "2025-01-31",
    "total_operations": 45,
    "total_tokens": 125000,
    "total_cost": "25.75",
    "operations_by_type": {
        "summary": 30,
        "quiz": 15
    },
    "cost_by_provider": {
        "openai": "15.25",
        "gemini": "10.50"
    },
    "success_rate": 0.98,
    "average_quality_score": 4.2
}
```

#### Get Usage Records

```http
GET /usage/records?page=1&page_size=20&operation_types=summary&date_from=2025-01-01

Response:
{
    "usage_records": [
        {
            "id": "record-uuid",
            "operation_type": "summary",
            "ai_provider": "openai",
            "ai_model": "gpt-4o",
            "total_tokens": 3500,
            "cost": "0.09",
            "processing_time_ms": 2500,
            "status": "success",
            "quality_score": 4.5,
            "created_at": "2025-01-14T03:11:00Z"
        }
    ],
    "total": 30,
    "page": 1,
    "total_pages": 2
}
```

#### Get Usage Dashboard

```http
GET /usage/dashboard

Response:
{
    "quota": { /* Current quota info */ },
    "current_period_stats": { /* This month's stats */ },
    "weekly_stats": { /* Last 7 days stats */ },
    "billing_period": {
        "current_period": "2025-01-01",
        "days_remaining": 17,
        "next_reset_date": "2025-02-01"
    },
    "alerts": [
        {
            "type": "warning",
            "category": "tokens",
            "message": "Token usage at 85%",
            "details": "Used 85,000 of 100,000 tokens"
        }
    ]
}
```

## Usage Flow

### 1. Pre-Operation Check

Before any AI operation, check quota availability:

```python
from app.usage.services import QuotaManager
from app.usage.schemas import OperationType

quota_manager = QuotaManager(db)
check_result = await quota_manager.check_quota_availability(
    user_id=user.id,
    operation_type=OperationType.SUMMARY,
    estimated_tokens=4000,
    estimated_cost=Decimal("0.10")
)

if not check_result.can_proceed:
    raise HTTPException(402, f"Insufficient quota: {check_result.reason}")
```

### 2. Operation Execution

Perform the AI operation with monitoring.

### 3. Usage Recording

After completion, record the actual usage:

```python
from app.usage.services import UsageTracker
from app.usage.schemas import UsageRecordCreate, UsageStatus

usage_tracker = UsageTracker(db)
await usage_tracker.record_usage(
    user_id=user.id,
    usage_data=UsageRecordCreate(
        operation_type=OperationType.SUMMARY,
        resource_id=summary.id,
        ai_provider="openai",
        ai_model="gpt-4o",
        input_tokens=2500,
        output_tokens=1500,
        total_tokens=4000,
        cost=Decimal("0.12"),
        processing_time_ms=3200,
        request_timestamp=start_time,
        response_timestamp=end_time,
        status=UsageStatus.SUCCESS,
        quality_score=Decimal("4.2")
    )
)
```

## Quota Management (TODO)

### Default Limits (Free Tier)

- **Tokens**: 100,000 per month
- **Cost**: $50.00 per month  
- **Summaries**: 100 per month
- **Quizzes**: 50 per month

### Premium Limits

- **Tokens**: 1,000,000 per month
- **Cost**: $500.00 per month
- **Summaries**: 1,000 per month
- **Quizzes**: 500 per month

### Monthly Reset

Quotas automatically reset on the first day of each month:

```python
from datetime import date

quota_manager = QuotaManager(db)
current_month = date.today().replace(day=1)
await quota_manager.reset_monthly_quota(user_id, current_month)
```

## Cost Estimation

AI costs are estimated based on provider pricing:

```python
def _estimate_ai_cost(provider: str, model: str, tokens: int) -> Decimal:
    cost_per_1k_tokens = {
        "openai": {
            "gpt-4o": 0.015,
            "gpt-4o-mini": 0.0015,
        },
        "gemini": {
            "gemini-2.0-flash": 0.001,
        },
        "anthropic": {
            "claude-4-opus": 0.075,
        }
    }
    
    rate = cost_per_1k_tokens.get(provider, {}).get(model, 0.01)
    return Decimal(str((tokens / 1000) * rate))
```

## Analytics & Reporting

### Usage Trends

Track usage patterns over time:

```python
# Get monthly usage trends
usage_stats = await usage_tracker.get_usage_statistics(
    user_id=user.id,
    date_from=date(2025, 1, 1),
    date_to=date(2025, 1, 31)
)

print(f"Total cost: ${usage_stats.total_cost}")
print(f"Success rate: {usage_stats.success_rate * 100:.1f}%")
print(f"Average quality: {usage_stats.average_quality_score:.1f}/5.0")
```

### Provider Comparison

Compare performance across AI providers:

```python
# Get provider-specific metrics
for provider, cost in usage_stats.cost_by_provider.items():
    operations = usage_stats.operations_by_provider[provider]
    avg_cost_per_op = cost / operations if operations > 0 else 0
    print(f"{provider}: {operations} ops, ${avg_cost_per_op:.4f} per op")
```

## Alert System

The system generates alerts based on usage patterns:

### Alert Types

- **Info**: 75-89% of limit used
- **Warning**: 90-99% of limit used  
- **Error**: 100%+ of limit exceeded

### Alert Categories

- **Tokens**: Token usage alerts
- **Cost**: Cost limit alerts
- **Summaries**: Summary count alerts
- **Quizzes**: Quiz count alerts

## Integration Examples

### React Dashboard Component

```jsx
import { useEffect, useState } from 'react';

const UsageDashboard = () => {
    const [dashboardData, setDashboardData] = useState(null);
    
    useEffect(() => {
        fetch('/usage/dashboard', {
            headers: { 'Authorization': `Bearer ${token}` }
        })
        .then(res => res.json())
        .then(setDashboardData);
    }, []);
    
    if (!dashboardData) return <div>Loading...</div>;
    
    const { quota, alerts } = dashboardData;
    
    return (
        <div className="usage-dashboard">
            <div className="quota-overview">
                <h3>Monthly Usage</h3>
                <div className="usage-bar">
                    <div 
                        className="usage-fill"
                        style={{ width: `${quota.token_usage_percentage}%` }}
                    />
                    <span>{quota.tokens_used:,} / {quota.token_limit:,} tokens</span>
                </div>
                <div className="cost-usage">
                    ${quota.cost_used} / ${quota.cost_limit} ({quota.cost_usage_percentage.toFixed(1)}%)
                </div>
            </div>
            
            {alerts.length > 0 && (
                <div className="alerts">
                    <h4>Usage Alerts</h4>
                    {alerts.map((alert, i) => (
                        <div key={i} className={`alert alert-${alert.type}`}>
                            <strong>{alert.message}</strong>
                            <p>{alert.details}</p>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
```

### Usage Check Before Operation

```javascript
const checkQuotaBeforeOperation = async (operationType, estimatedTokens, estimatedCost) => {
    const response = await fetch('/usage/quota/check', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            operation_type: operationType,
            estimated_tokens: estimatedTokens,
            estimated_cost: estimatedCost
        })
    });
    
    const result = await response.json();
    
    if (!result.can_proceed) {
        alert(`Cannot proceed: ${result.reason}`);
        return false;
    }
    
    return true;
};

// Usage
const canGenerate = await checkQuotaBeforeOperation('summary', 4000, 0.10);
if (canGenerate) {
    // Proceed with summary generation
}
```

## Admin Tools

### Update User Quota

```python
# Admin endpoint to update user quotas
quota_manager = QuotaManager(db)
await quota_manager.update_quota_limits(
    user_id=123,
    token_limit=500000,  # Increase to 500K tokens
    cost_limit=Decimal("200.00"),  # Increase to $200
    is_premium=True,
    changed_by=admin_user.id,
    reason="Premium upgrade"
)
```

### Bulk Quota Operations

```python
# Reset quotas for all users (monthly job)
from app.usage.models import UserQuota

async def reset_all_quotas_for_month(db: AsyncSession, target_month: date):
    quotas = await db.execute(
        select(UserQuota).where(UserQuota.quota_month == target_month)
    )
    
    for quota in quotas.scalars():
        quota.tokens_used = 0
        quota.cost_used = Decimal("0.00")
        quota.summaries_used = 0
        quota.quizzes_used = 0
    
    await db.commit()
```

## Monitoring & Alerting

### System-wide Usage Monitoring

```python
# Monitor overall system usage
async def get_system_usage_stats(db: AsyncSession) -> Dict:
    total_users = await db.scalar(select(func.count(User.id)))
    
    current_month = date.today().replace(day=1)
    monthly_usage = await db.execute(
        select(
            func.sum(UsageRecord.total_tokens),
            func.sum(UsageRecord.cost),
            func.count(UsageRecord.id)
        ).where(
            extract('month', UsageRecord.created_at) == current_month.month,
            extract('year', UsageRecord.created_at) == current_month.year
        )
    )
    
    total_tokens, total_cost, total_operations = monthly_usage.first()
    
    return {
        "total_users": total_users,
        "monthly_tokens": total_tokens or 0,
        "monthly_cost": float(total_cost or 0),
        "monthly_operations": total_operations or 0,
        "avg_cost_per_user": float(total_cost or 0) / max(total_users, 1)
    }
```

## Security Considerations

- **User Isolation**: Users can only access their own usage data
- **Rate Limiting**: API endpoints have rate limits to prevent abuse
- **Input Validation**: All inputs are validated using Pydantic models
- **Audit Trail**: All quota changes are logged with admin attribution
- **Cost Protection**: Hard limits prevent runaway costs

## Performance Optimizations

- **Database Indexes**: Optimized queries for usage lookups
- **Caching**: Redis caching for frequently accessed quota data
- **Batch Processing**: Efficient bulk operations for admin tasks
- **Pagination**: All list endpoints support pagination
- **Aggregation**: Pre-calculated statistics for faster dashboards

## Testing

### Unit Tests

```python
async def test_quota_check():
    quota_manager = QuotaManager(db)
    
    # Test with sufficient quota
    result = await quota_manager.check_quota_availability(
        user_id=1,
        operation_type=OperationType.SUMMARY,
        estimated_tokens=1000,
        estimated_cost=Decimal("0.05")
    )
    
    assert result.can_proceed == True
    assert result.tokens_remaining > 1000

# Test quota exceeded
async def test_quota_exceeded():
    # Set up user with minimal quota
    quota = UserQuota(
        user_id=1,
        quota_month=date.today().replace(day=1),
        token_limit=100,
        tokens_used=90
    )
    
    result = await quota_manager.check_quota_availability(
        user_id=1,
        operation_type=OperationType.SUMMARY,
        estimated_tokens=50  # Would exceed limit
    )
    
    assert result.can_proceed == False
    assert "Token limit exceeded" in result.reason
```

## Troubleshooting

### Common Issues

1. **Usage Not Recorded**: Check if task completed successfully and database transactions committed
2. **Incorrect Costs**: Verify AI provider pricing and token calculation
3. **Quota Exceeded**: Check current usage and monthly limits
4. **Performance Issues**: Review database indexes and query performance

### Debug Commands

```python
# Check user's current quota
quota = await quota_manager.get_or_create_quota(user_id)
print(f"Tokens: {quota.tokens_used}/{quota.token_limit}")
print(f"Cost: ${quota.cost_used}/${quota.cost_limit}")

# Get recent usage records
recent_usage = await usage_tracker.get_usage_records(
    user_id, 
    UsageFilters(page=1, page_size=10, sort_order="desc")
)
for record in recent_usage.usage_records:
    print(f"{record.created_at}: {record.operation_type} - {record.total_tokens} tokens, ${record.cost}")
```

This usage tracking system provides comprehensive monitoring and control over AI operations, ensuring cost management and fair resource allocation across all users.
