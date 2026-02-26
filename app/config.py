"""Configuration management using Pydantic Settings."""

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application
    app_name: str = Field(default="Study Assistant API", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")
    version: str = Field(default="0.1.0", description="Application version")
    environment: str = Field(default="development", description="Environment")

    # Server
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8000, description="Server port")
    frontend_url: str = Field(default="http://localhost:3000", description="Frontend URL")
    # Security
    secret_key: str = Field(
        default="changeme-development-key-please-set-in-production-32chars",
        description="Secret key for JWT tokens",
    )
    access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration time in minutes"
    )
    refresh_token_expire_days: int = Field(
        default=7, description="Refresh token expiration time in days"
    )
    password_reset_token_expire_hours: int = Field(
        default=1, description="Password reset token expiration in hours"
    )

    # Database
    database_url: str = Field(
        default="sqlite:///./study_assistant.db",
        description="Database URL (PostgreSQL for production, SQLite for development/testing)",
    )
    database_async_url: str = Field(
        default="sqlite+aiosqlite:///./study_assistant.db",
        description="Async database URL",
    )
    database_echo: bool = Field(
        default=False, description="SQLAlchemy echo SQL queries"
    )
    database_pool_size: int = Field(default=5, description="Database connection pool size")
    database_max_overflow: int = Field(
        default=10, description="Database max overflow connections"
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", description="Redis URL")
    redis_db: int = Field(default=0, description="Redis database number")

    # Celery
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1", description="Celery broker URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1", description="Celery result backend URL"
    )

    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins",
    )
    cors_allow_credentials: bool = Field(
        default=True, description="Allow CORS credentials"
    )
    cors_allow_methods: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        description="Allowed CORS methods",
    )
    cors_allow_headers: List[str] = Field(
        default=["*"], description="Allowed CORS headers"
    )

    # File Upload
    upload_dir: str = Field(default="uploads", description="Upload directory")
    max_file_size: int = Field(
        default=10 * 1024 * 1024, description="Maximum file size in bytes (10MB)"
    )
    allowed_file_types: List[str] = Field(
        default=["application/pdf", "text/plain", "text/markdown"],
        description="Allowed file MIME types",
    )

    # Rate Limiting
    rate_limit_requests: int = Field(
        default=100, description="Rate limit requests per minute"
    )
    rate_limit_per: str = Field(default="minute", description="Rate limit time period")

    # AI Services
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    gemini_api_key: Optional[str] = Field(default=None, description="Gemini API key")
    ai_request_timeout: int = Field(
        default=120, description="AI request timeout in seconds"
    )
    ai_max_retries: int = Field(default=3, description="Maximum AI request retries")

    # Email Configuration
    smtp_server: Optional[str] = Field(default=None, description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP port (587 for STARTTLS, 465 for SSL)")
    smtp_username: Optional[str] = Field(default=None, description="SMTP authentication username")
    smtp_password: Optional[str] = Field(default=None, description="SMTP authentication password")
    smtp_sender_email: Optional[str] = Field(default=None, description="Default sender email address")
    smtp_sender_name: str = Field(default="Study Assistant", description="Default sender name")
    smtp_use_tls: bool = Field(default=True, description="Use STARTTLS encryption")
    smtp_use_ssl: bool = Field(default=False, description="Use SSL/TLS encryption")
    smtp_timeout: int = Field(default=30, description="SMTP connection timeout in seconds")
    
    # Email Templates
    email_templates_dir: str = Field(default="templates/emails", description="Email templates directory")
    
    # Email Verification
    email_verification_expire_hours: int = Field(
        default=24, description="Email verification token expiration in hours"
    )
    password_reset_expire_hours: int = Field(
        default=1, description="Password reset token expiration in hours"
    )
    
    # Email Features
    enable_email_verification: bool = Field(
        default=True, description="Enable email verification for new users"
    )
    enable_password_reset: bool = Field(
        default=True, description="Enable password reset via email"
    )
    
    # Legacy compatibility (deprecated - use smtp_* fields above)
    mail_username: Optional[str] = Field(default=None, description="[DEPRECATED] Use smtp_username")
    mail_password: Optional[str] = Field(default=None, description="[DEPRECATED] Use smtp_password") 
    mail_from: Optional[str] = Field(default=None, description="[DEPRECATED] Use smtp_sender_email")
    mail_port: int = Field(default=587, description="[DEPRECATED] Use smtp_port")
    mail_server: Optional[str] = Field(default=None, description="[DEPRECATED] Use smtp_server")
    mail_starttls: bool = Field(default=True, description="[DEPRECATED] Use smtp_use_tls")
    mail_ssl_tls: bool = Field(default=False, description="[DEPRECATED] Use smtp_use_ssl")

    # Monitoring
    enable_metrics: bool = Field(
        default=True, description="Enable Prometheus metrics"
    )
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="json", description="Logging format (json or console)"
    )

    @validator("secret_key")
    def validate_secret_key(cls, v: str) -> str:
        """Ensure secret key is sufficiently long."""
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    @validator("database_url")
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v.startswith(("postgresql", "sqlite")):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL or SQLite connection string"
            )
        return v

    @validator("environment")
    def validate_environment(cls, v: str) -> str:
        """Ensure environment is valid."""
        if v not in ["development", "testing", "staging", "production"]:
            raise ValueError(
                "ENVIRONMENT must be one of: development, testing, staging, production"
            )
        return v

    @validator("log_level")
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        if v.upper() not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            raise ValueError(
                "LOG_LEVEL must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        return v.upper()

    @validator("log_format")
    def validate_log_format(cls, v: str) -> str:
        """Ensure log format is valid."""
        if v not in ["json", "console"]:
            raise ValueError("LOG_FORMAT must be either 'json' or 'console'")
        return v

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience function for getting settings
def get_config() -> Settings:
    """Get application settings."""
    return get_settings()
