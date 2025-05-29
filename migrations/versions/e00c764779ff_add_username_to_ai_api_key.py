"""add username to ai_api_key

Revision ID: e00c764779ff
Revises: 7a9021e1b986
Create Date: 2025-05-30 01:27:44.833667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e00c764779ff'
down_revision: Union[str, None] = '7a9021e1b986'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

def downgrade() -> None:
    """Downgrade schema."""
   