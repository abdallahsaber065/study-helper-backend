"""fix Gemini file cache

Revision ID: 8df9d10bb74e
Revises: 2681b0f222b4
Create Date: 2025-05-29 09:37:07.362522

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8df9d10bb74e'
down_revision: Union[str, None] = '2681b0f222b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # First add columns as nullable to avoid issues with existing data
    op.add_column('gemini_file_cache', sa.Column('api_key_id', sa.Integer(), nullable=True))
    op.add_column('gemini_file_cache', sa.Column('gemini_file_uri', sa.String(length=255), nullable=True))
    op.add_column('gemini_file_cache', sa.Column('gemini_display_name', sa.String(length=255), nullable=True))
    op.add_column('gemini_file_cache', sa.Column('gemini_file_unique_name', sa.String(length=255), nullable=True))
    op.add_column('gemini_file_cache', sa.Column('expiration_time', sa.DateTime(timezone=True), nullable=True))
    
    # Get a reference to the connection
    connection = op.get_bind()
    
    # Handle existing rows - either migrate data, set defaults, or delete old data
    # Option 1: Delete existing rows if they're not needed anymore
    connection.execute(sa.text("DELETE FROM gemini_file_cache"))
    
    # Option 2 (alternative): Update existing rows with valid values if needed
    # connection.execute(sa.text(
    #    "UPDATE gemini_file_cache SET api_key_id = (SELECT id FROM ai_api_key LIMIT 1), " +
    #    "gemini_file_uri = 'legacy_' || physical_file_id, " +
    #    "gemini_display_name = 'Legacy File', " +
    #    "gemini_file_unique_name = 'legacy_file_' || id"
    # ))
    
    # Now alter columns to be non-nullable
    op.alter_column('gemini_file_cache', 'api_key_id', nullable=False)
    op.alter_column('gemini_file_cache', 'gemini_file_uri', nullable=False)
    op.alter_column('gemini_file_cache', 'gemini_display_name', nullable=False)
    op.alter_column('gemini_file_cache', 'gemini_file_unique_name', nullable=False)
    
    # Continue with the rest of the operations
    op.drop_constraint('uq_gemini_file_cache_file_processing', 'gemini_file_cache', type_='unique')
    op.create_index('idx_gemini_file_cache_api_key_id', 'gemini_file_cache', ['api_key_id'], unique=False)
    op.create_index('idx_gemini_file_cache_physical_file_id', 'gemini_file_cache', ['physical_file_id'], unique=False)
    op.create_unique_constraint('uq_gemini_file_cache', 'gemini_file_cache', ['physical_file_id', 'api_key_id', 'gemini_file_uri'])
    op.create_unique_constraint(None, 'gemini_file_cache', ['gemini_file_unique_name'])
    op.create_unique_constraint(None, 'gemini_file_cache', ['gemini_file_uri'])
    op.create_foreign_key(None, 'gemini_file_cache', 'ai_api_key', ['api_key_id'], ['id'])
    op.drop_column('gemini_file_cache', 'gemini_response')
    op.drop_column('gemini_file_cache', 'processing_type')


def downgrade() -> None:
    """Downgrade schema."""
    # First add the old columns
    op.add_column('gemini_file_cache', sa.Column('processing_type', sa.VARCHAR(length=50), nullable=True))
    op.add_column('gemini_file_cache', sa.Column('gemini_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Get connection for data updates
    connection = op.get_bind()
    
    # Update existing records with default values for the old columns
    connection.execute(sa.text(
        "UPDATE gemini_file_cache SET processing_type = 'unknown', gemini_response = '{}'::jsonb"
    ))
    
    # Make old columns non-nullable
    op.alter_column('gemini_file_cache', 'processing_type', nullable=False)
    op.alter_column('gemini_file_cache', 'gemini_response', nullable=False)
    
    # Drop constraints and indexes
    op.drop_constraint(None, 'gemini_file_cache', type_='foreignkey')
    op.drop_constraint(None, 'gemini_file_cache', type_='unique')
    op.drop_constraint(None, 'gemini_file_cache', type_='unique')
    op.drop_constraint('uq_gemini_file_cache', 'gemini_file_cache', type_='unique')
    op.drop_index('idx_gemini_file_cache_physical_file_id', table_name='gemini_file_cache')
    op.drop_index('idx_gemini_file_cache_api_key_id', table_name='gemini_file_cache')
    op.create_unique_constraint('uq_gemini_file_cache_file_processing', 'gemini_file_cache', ['physical_file_id', 'processing_type'])
    
    # Drop new columns
    op.drop_column('gemini_file_cache', 'expiration_time')
    op.drop_column('gemini_file_cache', 'gemini_file_unique_name')
    op.drop_column('gemini_file_cache', 'gemini_display_name')
    op.drop_column('gemini_file_cache', 'gemini_file_uri')
    op.drop_column('gemini_file_cache', 'api_key_id')
