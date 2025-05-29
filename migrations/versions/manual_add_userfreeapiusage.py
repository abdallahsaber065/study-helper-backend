"""Add UserFreeApiUsage table

Revision ID: manual_add_userfreeapiusage
Revises: 8df9d10bb74e
Create Date: 2025-05-29 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'manual_add_userfreeapiusage'
down_revision: Union[str, None] = '8df9d10bb74e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create user_free_api_usage table manually
    op.execute("""
    CREATE TABLE user_free_api_usage (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES "user"(id),
        api_provider ai_provider_enum NOT NULL,
        usage_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(user_id)
    )
    """)
    
    op.execute("""
    CREATE INDEX ix_user_free_api_usage_id ON user_free_api_usage (id)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_user_free_api_usage_id', table_name='user_free_api_usage')
    op.drop_table('user_free_api_usage') 