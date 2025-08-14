"""
Type definitions and enums for AI providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field, validator
from pathlib import Path


class AIProviderType(str, Enum):
    """Supported AI provider types."""

    OPENAI = "openai"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"


class TaskStatus(str, Enum):
    """Task processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorType(str, Enum):
    """AI provider error types."""

    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    TIMEOUT_ERROR = "timeout_error"
    API_ERROR = "api_error"
    NETWORK_ERROR = "network_error"
    QUOTA_EXCEEDED = "quota_exceeded"
    INVALID_REQUEST = "invalid_request"


@dataclass
class AIProviderConfig:
    """Configuration for AI provider instances."""

    provider_type: AIProviderType
    api_key: str
    model: str
    timeout: int = 300
    max_retries: int = 3
    max_tokens: int = 4096
    temperature: float = 0.7
    enable_logging: bool = True
    rate_limit_per_minute: int = 60


@dataclass
class ToolSpec:
    """Define a callable tool that models can ask to invoke with enhanced validation."""

    name: str
    description: str
    json_schema: Dict[str, Any]
    func: Callable[[Dict[str, Any]], Any]
    timeout: int = 30
    retry_on_failure: bool = True

    def __post_init__(self):
        """Validate tool specification."""
        if not self.name or not self.name.isidentifier():
            raise ValueError(f"Invalid tool name: {self.name}")
        if len(self.description) < 10:
            raise ValueError("Tool description must be at least 10 characters")


class FileValidationConfig(BaseModel):
    """Configuration for file validation."""

    max_file_size: int = Field(
        default=50 * 1024 * 1024, description="Maximum file size in bytes"
    )
    allowed_mime_types: List[str] = Field(
        default=[
            "application/pdf",
            "text/plain",
            "text/markdown",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
    )
    allowed_extensions: List[str] = Field(
        default=[".pdf", ".txt", ".md", ".doc", ".docx"]
    )
    require_virus_scan: bool = Field(default=True)


class RequestValidation(BaseModel):
    """Validation model for AI provider requests."""

    system_instruction: Optional[str] = Field(None, max_length=10000)
    user_text: Optional[str] = Field(None, max_length=50000)
    images: Optional[List[str]] = Field(None, max_items=10)
    files: Optional[List[str]] = Field(None, max_items=5)
    model: Optional[str] = Field(None, pattern=r"^[a-zA-Z0-9\-_.]+$")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)

    @validator("images", each_item=True)
    def validate_image_path(cls, v):
        if v and not Path(v).exists():
            raise ValueError(f"Image file not found: {v}")
        return v

    @validator("files", each_item=True)
    def validate_file_path(cls, v):
        if v and not Path(v).exists():
            raise ValueError(f"File not found: {v}")
        return v


class AIResponse(BaseModel):
    """Enhanced response from any provider with monitoring data."""

    text: Optional[str] = None
    structured: Optional[Any] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    raw: Any = None

    # Enhanced monitoring fields
    correlation_id: str
    provider: str
    model: str
    request_timestamp: datetime = Field(default_factory=datetime.utcnow)
    response_timestamp: datetime = Field(default_factory=datetime.utcnow)
    processing_time_ms: int = 0
    error_info: Optional[Dict[str, Any]] = None

    class Config:
        arbitrary_types_allowed = True
