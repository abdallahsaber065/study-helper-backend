-- Study Helper Backend API - Database Initialization Script
-- This script sets up the database for development/production environments

-- =============================================================================
-- Extensions
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- =============================================================================
-- Custom Functions
-- =============================================================================

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- ENUM Types
-- =============================================================================

-- User role enumeration
CREATE TYPE user_role_enum AS ENUM ('user', 'admin', 'moderator');

-- Difficulty level enumeration
CREATE TYPE difficulty_level_enum AS ENUM ('Easy', 'Medium', 'Hard');

-- AI provider enumeration
CREATE TYPE ai_provider_enum AS ENUM ('OpenAI', 'Google', 'Other');

-- Content type enumeration
CREATE TYPE content_type_enum AS ENUM ('file', 'summary', 'quiz');

-- Community role enumeration
CREATE TYPE community_role_enum AS ENUM ('admin', 'member', 'moderator');

-- Community file category enumeration
CREATE TYPE community_file_category_enum AS ENUM (
    'lecture', 'section', 'exam', 'summary_material', 'general_resource', 'other'
);

-- Notification type enumeration
CREATE TYPE notification_type_enum AS ENUM (
    'new_content', 'comment_reply', 'quiz_result', 'community_invite', 'mention'
);

-- Rating value enumeration
CREATE TYPE rating_value_enum AS ENUM ('1', '2', '3', '4', '5');

-- =============================================================================
-- Development Data (Only for non-production environments)
-- =============================================================================

-- Insert default admin user (only if not exists)
-- Note: Password hash for 'admin123' - change this in production!
-- This will be created by the application if needed

-- =============================================================================
-- Performance Optimizations
-- =============================================================================

-- Increase shared_buffers for better performance (adjust based on available memory)
-- ALTER SYSTEM SET shared_buffers = '256MB';

-- Increase work_mem for complex queries
-- ALTER SYSTEM SET work_mem = '64MB';

-- Enable query planning improvements
-- ALTER SYSTEM SET random_page_cost = 1.1;

-- =============================================================================
-- Security Settings
-- =============================================================================

-- Set password encryption method
ALTER SYSTEM SET password_encryption = 'scram-sha-256';

-- Configure connection limits
ALTER SYSTEM SET max_connections = 100;

-- Configure logging for security auditing
ALTER SYSTEM SET log_statement = 'all';
ALTER SYSTEM SET log_duration = on;
ALTER SYSTEM SET log_min_duration_statement = 1000;

-- =============================================================================
-- Maintenance Settings
-- =============================================================================

-- Configure autovacuum for better performance
ALTER SYSTEM SET autovacuum = on;
ALTER SYSTEM SET autovacuum_max_workers = 3;

-- Configure checkpoint settings
ALTER SYSTEM SET checkpoint_timeout = '15min';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;

-- =============================================================================
-- Application-Specific Indexes (will be created by Alembic migrations)
-- =============================================================================

-- Note: The following indexes will be created by Alembic migrations:
-- - User table indexes (username, email)
-- - Content indexes (content_type, content_id)
-- - Performance indexes for analytics
-- - Full-text search indexes where needed

COMMIT; 