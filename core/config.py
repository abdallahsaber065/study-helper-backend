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
    
    # File upload settings
    max_file_size_mb: int = 50
    allowed_file_types: list[str] = [".pdf", ".txt", ".docx", ".doc"]
    upload_directory: str = "file_uploads"
    
    # Application settings
    app_name: str = "Study Helper Backend API"
    app_version: str = "0.1.0"
    debug: bool = False
    
    @property
    def database_url(self) -> str:
        """Construct database URL from individual components."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
