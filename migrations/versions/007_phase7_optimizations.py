"""Phase 7 optimizations - Add indexes for performance

Revision ID: 007_phase7_optimizations
Revises: 006_phase6_interactions
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_phase7_optimizations'
down_revision = '006_phase6_interactions'
branch_labels = None
depends_on = None


def upgrade():
    # Add indexes for ContentComment performance
    op.create_index(
        'ix_content_comment_content_lookup',
        'content_comment',
        ['content_type', 'content_id']
    )
    op.create_index(
        'ix_content_comment_author_created',
        'content_comment',
        ['author_id', 'created_at']
    )
    op.create_index(
        'ix_content_comment_parent_thread',
        'content_comment',
        ['parent_comment_id'],
        postgresql_where=sa.text('parent_comment_id IS NOT NULL')
    )
    
    # Add indexes for ContentRating performance  
    op.create_index(
        'ix_content_rating_content_lookup',
        'content_rating',
        ['content_type', 'content_id']
    )
    op.create_index(
        'ix_content_rating_user_content',
        'content_rating',
        ['user_id', 'content_type', 'content_id'],
        unique=True
    )
    
    # Add indexes for Notification performance
    op.create_index(
        'ix_notification_user_status',
        'notification',
        ['user_id', 'is_read', 'created_at']
    )
    op.create_index(
        'ix_notification_content_lookup',
        'notification',
        ['related_content_type', 'related_content_id'],
        postgresql_where=sa.text('related_content_type IS NOT NULL AND related_content_id IS NOT NULL')
    )
    
    # Add indexes for ContentVersion performance
    op.create_index(
        'ix_content_version_content_version',
        'content_version',
        ['content_type', 'content_id', 'version_number']
    )
    op.create_index(
        'ix_content_version_user_created',
        'content_version',
        ['user_id', 'created_at']
    )
    
    # Add indexes for ContentAnalytics performance
    op.create_index(
        'ix_content_analytics_content_lookup',
        'content_analytics',
        ['content_type', 'content_id'],
        unique=True
    )
    op.create_index(
        'ix_content_analytics_view_count',
        'content_analytics',
        ['view_count']
    )
    op.create_index(
        'ix_content_analytics_updated',
        'content_analytics',
        ['updated_at']
    )
    
    # Add indexes for Quiz Session performance (if not already exists)
    try:
        op.create_index(
            'ix_quiz_session_user_quiz',
            'quiz_session',
            ['user_id', 'quiz_id']
        )
    except:
        pass  # Index might already exist
    
    try:
        op.create_index(
            'ix_quiz_session_completed',
            'quiz_session',
            ['completed_at'],
            postgresql_where=sa.text('completed_at IS NOT NULL')
        )
    except:
        pass  # Index might already exist
    
    # Add indexes for Summary performance
    try:
        op.create_index(
            'ix_summary_user_created',
            'summary',
            ['user_id', 'created_at']
        )
    except:
        pass  # Index might already exist
    
    try:
        op.create_index(
            'ix_summary_community_created',
            'summary',
            ['community_id', 'created_at'],
            postgresql_where=sa.text('community_id IS NOT NULL')
        )
    except:
        pass  # Index might already exist
    
    # Add indexes for MCQ Quiz performance
    try:
        op.create_index(
            'ix_mcq_quiz_user_public',
            'mcq_quiz',
            ['user_id', 'is_public', 'is_active']
        )
    except:
        pass  # Index might already exist
    
    try:
        op.create_index(
            'ix_mcq_quiz_community_active',
            'mcq_quiz',
            ['community_id', 'is_active'],
            postgresql_where=sa.text('community_id IS NOT NULL')
        )
    except:
        pass  # Index might already exist
    
    # Add indexes for Physical File performance
    try:
        op.create_index(
            'ix_physical_file_hash',
            'physical_file',
            ['file_hash']
        )
    except:
        pass  # Index might already exist
    
    try:
        op.create_index(
            'ix_physical_file_type_size',
            'physical_file',
            ['file_type', 'file_size']
        )
    except:
        pass  # Index might already exist
    
    # Add indexes for Community Member performance
    try:
        op.create_index(
            'ix_community_member_user_role',
            'community_member',
            ['user_id', 'role']
        )
    except:
        pass  # Index might already exist
    
    try:
        op.create_index(
            'ix_community_member_community_role',
            'community_member',
            ['community_id', 'role']
        )
    except:
        pass  # Index might already exist


def downgrade():
    # Remove all the indexes in reverse order
    
    # ContentComment indexes
    op.drop_index('ix_content_comment_content_lookup')
    op.drop_index('ix_content_comment_author_created')
    op.drop_index('ix_content_comment_parent_thread')
    
    # ContentRating indexes
    op.drop_index('ix_content_rating_content_lookup')
    op.drop_index('ix_content_rating_user_content')
    
    # Notification indexes
    op.drop_index('ix_notification_user_status')
    op.drop_index('ix_notification_content_lookup')
    
    # ContentVersion indexes
    op.drop_index('ix_content_version_content_version')
    op.drop_index('ix_content_version_user_created')
    
    # ContentAnalytics indexes
    op.drop_index('ix_content_analytics_content_lookup')
    op.drop_index('ix_content_analytics_view_count')
    op.drop_index('ix_content_analytics_updated')
    
    # Optional indexes (try to drop, ignore if not exist)
    try:
        op.drop_index('ix_quiz_session_user_quiz')
    except:
        pass
    
    try:
        op.drop_index('ix_quiz_session_completed')
    except:
        pass
    
    try:
        op.drop_index('ix_summary_user_created')
    except:
        pass
    
    try:
        op.drop_index('ix_summary_community_created')
    except:
        pass
    
    try:
        op.drop_index('ix_mcq_quiz_user_public')
    except:
        pass
    
    try:
        op.drop_index('ix_mcq_quiz_community_active')
    except:
        pass
    
    try:
        op.drop_index('ix_physical_file_hash')
    except:
        pass
    
    try:
        op.drop_index('ix_physical_file_type_size')
    except:
        pass
    
    try:
        op.drop_index('ix_community_member_user_role')
    except:
        pass
    
    try:
        op.drop_index('ix_community_member_community_role')
    except:
        pass 