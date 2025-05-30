"""
Application configuration using Pydantic settings.
"""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database settings
    db_host: str = "localhost"
    db_port: str = "5432"
    db_user: str = "user"
    db_password: str = "password"
    db_name: str = "dbname"
    
    # JWT settings
    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    
    # AI settings
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    # Free tier limits
    free_tier_gemini_limit: int = 10  # Max number of free Gemini API calls per user
    free_tier_openai_limit: int = 5   # Max number of free OpenAI API calls per user
    
    # File upload settings
    max_file_size_mb: int = 50
    allowed_file_types: list[str] = [".pdf", ".txt", ".docx", ".doc"]
    upload_directory: str = "cache/file_uploads"
    
    # Community settings
    max_communities_per_user: int = 3
    max_community_memberships_per_user: int = 10
    community_code_length: int = 8
    
    # Default user settings
    default_admin_username: Optional[str] = None
    default_admin_email: Optional[str] = None
    default_admin_password: Optional[str] = None
    force_reset_password_admin: bool = False
    
    default_free_user_username: Optional[str] = None
    default_free_user_email: Optional[str] = None
    default_free_user_password: Optional[str] = None
    force_reset_password_free: bool = False
    
    # Application settings
    app_name: str = "Study Helper Backend API"
    app_version: str = "0.1.0"
    debug: bool = False
    
    # Logging settings
    log_level: str = "INFO"
    log_format: str = "json"  # json or text
    enable_request_logging: bool = True
    enable_sql_logging: bool = False
    
    # Security settings
    enable_security_headers: bool = True
    enable_rate_limiting: bool = True
    enable_request_size_limit: bool = True
    max_request_size_bytes: int = 50 * 1024 * 1024  # 50MB
    request_timeout_seconds: int = 300  # 5 minutes
    
    # Monitoring settings
    enable_health_checks: bool = True
    enable_metrics: bool = True
    health_check_timeout: int = 30
    
    # Background task settings
    enable_background_tasks: bool = True
    task_cleanup_interval_minutes: int = 60
    task_retention_days: int = 7
    
    @property
    def database_url(self) -> str:
        """Construct database URL from individual components."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


# Gemini settings
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_MAX_TOKENS = 2048
GEMINI_TEMPERATURE = 0.3
