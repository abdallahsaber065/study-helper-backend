"""merge multiple heads

Revision ID: 7a9021e1b986
Revises: dafbc7590770, manual_add_userfreeapiusage
Create Date: 2025-05-30 01:26:12.658708

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a9021e1b986'
down_revision: Union[str, None] = ('dafbc7590770', 'manual_add_userfreeapiusage')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
