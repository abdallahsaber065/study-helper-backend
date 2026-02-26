from __future__ import annotations

import asyncio
import base64
import orjson
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type
from urllib.parse import urlparse

import aiofiles
import magic
import structlog
from circuitbreaker import circuit
from pydantic import BaseModel, Field, ValidationError, validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
import dotenv 
dotenv.load_dotenv()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# -----------------------------
# Enhanced Configuration & Types
# -----------------------------


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
class AIProviderError(Exception):
    """Enhanced error class for AI provider operations."""

    error_type: ErrorType
    message: str
    provider: str
    correlation_id: str
    details: Optional[Dict[str, Any]] = None
    original_exception: Optional[Exception] = None

    def __str__(self) -> str:
        return f"[{self.provider}] {self.error_type.value}: {self.message} (ID: {self.correlation_id})"


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


# -----------------------------
# Enhanced Core Types
# -----------------------------


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


class AIResponse(BaseModel):
    """Enhanced response from any provider with monitoring data."""

    text: Optional[str] = None
    structured: Optional[Any] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    raw: Any = None

    # Enhanced monitoring fields
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider: str
    model: str
    request_timestamp: datetime = Field(default_factory=datetime.utcnow)
    response_timestamp: datetime = Field(default_factory=datetime.utcnow)
    processing_time_ms: int = 0
    error_info: Optional[Dict[str, Any]] = None

    class Config:
        arbitrary_types_allowed = True


class AIProvider(ABC):
    """Enhanced central interface with comprehensive error handling and monitoring."""

    def __init__(self, config: AIProviderConfig):
        """Initialize provider with configuration."""
        self.config = config
        self.correlation_id = str(uuid.uuid4())
        self.logger = logger.bind(
            provider=config.provider_type.value, correlation_id=self.correlation_id
        )
        self._request_count = 0
        self._circuit_breaker = self._setup_circuit_breaker()

    def _setup_circuit_breaker(self):
        """Setup circuit breaker for resilience."""
        return circuit(
            failure_threshold=5, recovery_timeout=60, expected_exception=AIProviderError
        )

    async def generate_with_monitoring(
        self,
        request_data: RequestValidation,
        tools: Optional[List[ToolSpec]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        **kwargs,
    ) -> AIResponse:
        """Generate with full monitoring and error handling."""
        correlation_id = str(uuid.uuid4())
        start_time = time.time()

        self.logger.info(
            "ai_request_started",
            correlation_id=correlation_id,
            model=request_data.model or self.config.model,
            has_tools=bool(tools),
            has_response_model=bool(response_model),
        )

        try:
            # Validate request
            self._validate_request(request_data)

            # Execute with circuit breaker
            response = await self._circuit_breaker(self._generate_with_retry)(
                request_data=request_data,
                tools=tools,
                response_model=response_model,
                correlation_id=correlation_id,
                **kwargs,
            )

            # Calculate processing time
            processing_time = int((time.time() - start_time) * 1000)
            response.processing_time_ms = processing_time
            response.correlation_id = correlation_id

            self.logger.info(
                "ai_request_completed",
                correlation_id=correlation_id,
                processing_time_ms=processing_time,
            )

            return response

        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)

            self.logger.error(
                "ai_request_failed",
                correlation_id=correlation_id,
                processing_time_ms=processing_time,
                error=str(e),
                error_type=type(e).__name__,
            )

            # Convert to standardized error
            if isinstance(e, AIProviderError):
                raise e
            else:
                raise AIProviderError(
                    error_type=ErrorType.API_ERROR,
                    message=str(e),
                    provider=self.config.provider_type.value,
                    correlation_id=correlation_id,
                    original_exception=e,
                )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, AIProviderError)),
    )
    async def _generate_with_retry(
        self,
        request_data: RequestValidation,
        tools: Optional[List[ToolSpec]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        correlation_id: str = None,
        **kwargs,
    ) -> AIResponse:
        """Generate with retry logic."""
        return await self.generate(
            system_instruction=request_data.system_instruction,
            user_text=request_data.user_text,
            images=request_data.images,
            files=request_data.files,
            model=request_data.model,
            tools=tools,
            response_model=response_model,
            extra=kwargs,
        )

    def _validate_request(self, request_data: RequestValidation) -> None:
        """Validate request data."""
        if not request_data.system_instruction and not request_data.user_text:
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message="Either system_instruction or user_text must be provided",
                provider=self.config.provider_type.value,
                correlation_id=self.correlation_id,
            )

        # Validate files if provided
        if request_data.files:
            for file_path in request_data.files:
                self._validate_file(file_path)

    def _validate_file(self, file_path: str) -> None:
        """Validate file for security and size constraints."""
        path = Path(file_path)

        if not path.exists():
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message=f"File not found: {file_path}",
                provider=self.config.provider_type.value,
                correlation_id=self.correlation_id,
            )

        # Check file size
        file_size = path.stat().st_size
        if file_size > 50 * 1024 * 1024:  # 50MB limit
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message=f"File too large: {file_size} bytes (max: 50MB)",
                provider=self.config.provider_type.value,
                correlation_id=self.correlation_id,
            )

        # Check MIME type
        try:
            mime_type = magic.from_file(file_path, mime=True)
            allowed_types = [
                "application/pdf",
                "text/plain",
                "text/markdown",
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ]
            if mime_type not in allowed_types:
                raise AIProviderError(
                    error_type=ErrorType.VALIDATION_ERROR,
                    message=f"Unsupported file type: {mime_type}",
                    provider=self.config.provider_type.value,
                    correlation_id=self.correlation_id,
                )
        except Exception as e:
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message=f"Error validating file: {str(e)}",
                provider=self.config.provider_type.value,
                correlation_id=self.correlation_id,
                original_exception=e,
            )

    @abstractmethod
    async def generate(
        self,
        *,
        system_instruction: Optional[str],
        user_text: Optional[str],
        images: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        model: Optional[str] = None,
        tools: Optional[List[ToolSpec]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> AIResponse:
        """Run one request with optional tools, schema, and media."""
        pass

    def get_metrics(self) -> Dict[str, Any]:
        """Get provider metrics."""
        return {
            "provider": self.config.provider_type.value,
            "request_count": self._request_count,
            "correlation_id": self.correlation_id,
        }


# -----------------------------
# Enhanced Utility Functions
# -----------------------------


def pydantic_to_json_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Convert Pydantic model to JSON schema with validation."""
    try:
        schema = model.model_json_schema()
        schema.setdefault("title", model.__name__)
        return schema
    except Exception as e:
        logger.error("Failed to convert Pydantic model to JSON schema", error=str(e))
        raise AIProviderError(
            error_type=ErrorType.VALIDATION_ERROR,
            message=f"Invalid Pydantic model: {str(e)}",
            provider="utility",
            correlation_id=str(uuid.uuid4()),
            original_exception=e,
        )


def encode_image_base64(img_bytes: bytes) -> str:
    """Encode image bytes to base64 with size validation."""
    if len(img_bytes) > 20 * 1024 * 1024:  # 20MB limit
        raise AIProviderError(
            error_type=ErrorType.VALIDATION_ERROR,
            message=f"Image too large: {len(img_bytes)} bytes (max: 20MB)",
            provider="utility",
            correlation_id=str(uuid.uuid4()),
        )
    return base64.b64encode(img_bytes).decode("ascii")


async def load_file_data_from_path_async(file_path: str) -> Tuple[bytes, str]:
    """Asynchronously load file data with validation and MIME type detection."""
    try:
        async with aiofiles.open(file_path, "rb") as f:
            file_bytes = await f.read()

        # Validate file size
        if len(file_bytes) > 50 * 1024 * 1024:  # 50MB limit
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message=f"File too large: {len(file_bytes)} bytes (max: 50MB)",
                provider="utility",
                correlation_id=str(uuid.uuid4()),
            )

        # Detect MIME type
        mime_type = magic.from_buffer(file_bytes, mime=True)

        # Validate MIME type
        allowed_types = [
            "application/pdf",
            "text/plain",
            "text/markdown",
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]

        if mime_type not in allowed_types:
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message=f"Unsupported file type: {mime_type}",
                provider="utility",
                correlation_id=str(uuid.uuid4()),
            )

        return file_bytes, mime_type

    except Exception as e:
        if isinstance(e, AIProviderError):
            raise e
        raise AIProviderError(
            error_type=ErrorType.VALIDATION_ERROR,
            message=f"Error loading file {file_path}: {str(e)}",
            provider="utility",
            correlation_id=str(uuid.uuid4()),
            original_exception=e,
        )


def load_file_data_from_path(file_path: str) -> Tuple[bytes, str]:
    """Synchronous wrapper for file loading."""
    return asyncio.run(load_file_data_from_path_async(file_path))


def _safe_parse_json(text: Optional[str]) -> Optional[Any]:
    """Safely parse JSON with enhanced error handling."""
    if not text:
        return None
    try:
        return orjson.loads(text)
    except orjson.JSONDecodeError as e:
        logger.warning(
            "Failed to parse JSON response", error=str(e), text_preview=text[:100]
        )
        return None
    except Exception as e:
        logger.error("Unexpected error parsing JSON", error=str(e))
        return None


class GeminiProvider(AIProvider):
    """Production-ready Gemini provider with comprehensive error handling."""

    def __init__(self, config: AIProviderConfig):
        super().__init__(config)
        try:
            from google import genai

            if not config.api_key:
                raise ValueError("GEMINI_API_KEY not provided")

            self.client = genai.Client(api_key=config.api_key)
            self.genai = genai
        except ImportError:
            raise AIProviderError(
                error_type=ErrorType.VALIDATION_ERROR,
                message="Google GenAI package not installed. Run: pip install google-genai",
                provider="gemini",
                correlation_id=self.correlation_id,
            )
        except Exception as e:
            raise AIProviderError(
                error_type=ErrorType.AUTHENTICATION_ERROR,
                message=f"Failed to initialize Gemini client: {str(e)}",
                provider="gemini",
                correlation_id=self.correlation_id,
                original_exception=e,
            )

    async def _files_to_parts(self, files: Optional[List[str]]):
        """Convert files to Gemini-compatible parts."""
        from google.genai import types

        parts = []
        if files:
            for file_path in files:
                try:
                    file_bytes, mime_type = await load_file_data_from_path_async(
                        file_path
                    )
                    if mime_type == "application/pdf":
                        # For PDFs, use Files API for better handling
                        try:
                            uploaded_file = self.client.files.upload(
                                file=file_path, config=dict(mime_type=mime_type)
                            )
                            parts.append(uploaded_file)
                        except Exception as e:
                            self.logger.warning(
                                "PDF upload failed, using direct bytes", error=str(e)
                            )
                            parts.append(
                                types.Part.from_bytes(
                                    data=file_bytes, mime_type=mime_type
                                )
                            )
                    else:
                        # For other files, use direct bytes
                        parts.append(
                            types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
                        )
                except Exception as e:
                    self.logger.error(
                        "Failed to process file", file_path=file_path, error=str(e)
                    )
                    raise AIProviderError(
                        error_type=ErrorType.VALIDATION_ERROR,
                        message=f"Error processing file {file_path}: {str(e)}",
                        provider="gemini",
                        correlation_id=self.correlation_id,
                        original_exception=e,
                    )
        return parts

    async def _images_to_parts(self, images: Optional[List[str]]):
        """Convert images to Gemini-compatible parts."""
        from google.genai import types

        parts = []
        if images:
            for image_path in images:
                try:
                    image_bytes, mime_type = await load_file_data_from_path_async(
                        image_path
                    )
                    if not mime_type.startswith("image/"):
                        raise ValueError(f"File is not an image: {mime_type}")

                    parts.append(
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                    )
                except Exception as e:
                    self.logger.error(
                        "Failed to process image", image_path=image_path, error=str(e)
                    )
                    raise AIProviderError(
                        error_type=ErrorType.VALIDATION_ERROR,
                        message=f"Error processing image {image_path}: {str(e)}",
                        provider="gemini",
                        correlation_id=self.correlation_id,
                        original_exception=e,
                    )
        return parts

    async def generate(
        self,
        *,
        system_instruction: Optional[str],
        user_text: Optional[str],
        images: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        model: Optional[str] = None,
        tools: Optional[List[ToolSpec]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> AIResponse:
        """Generate response using Gemini API with comprehensive error handling."""
        from google.genai import types

        model = model or self.config.model
        start_time = time.time()

        # Tools and structured output are mutually exclusive in Gemini
        if tools and response_model:
            self.logger.warning(
                "Tools and structured output are mutually exclusive, disabling structured output"
            )
            response_model = None

        try:
            # Build tools
            tool_defs = None
            if tools:
                function_declarations = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.json_schema,
                    }
                    for t in tools
                ]
                tool_defs = [types.Tool(function_declarations=function_declarations)]

            # Build config
            config = types.GenerateContentConfig()
            if tool_defs:
                config.tools = tool_defs

            if response_model is not None:
                config.response_mime_type = "application/json"
                config.response_schema = pydantic_to_json_schema(response_model)

            # Apply extra configurations
            if extra:
                for key, value in extra.items():
                    if hasattr(config, key):
                        setattr(config, key, value)

            # Build contents
            contents = []
            if system_instruction:
                config.system_instruction = system_instruction

            user_parts = []
            if user_text:
                user_parts.append(types.Part(text=user_text))

            user_parts.extend(await self._images_to_parts(images))
            user_parts.extend(await self._files_to_parts(files))

            if user_parts:
                contents.append(types.Content(role="user", parts=user_parts))

            self.logger.info(
                "gemini_request_starting", model=model, has_tools=bool(tools)
            )

            # Make API call with error handling
            try:
                resp = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                error_type = self._classify_gemini_error(e)
                raise AIProviderError(
                    error_type=error_type,
                    message=f"Gemini API error: {str(e)}",
                    provider="gemini",
                    correlation_id=self.correlation_id,
                    original_exception=e,
                )

            tool_calls: List[Dict[str, Any]] = []

            # Handle function calls
            if hasattr(resp, "candidates") and resp.candidates:
                for candidate in resp.candidates:
                    if hasattr(candidate, "content") and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                fc = part.function_call
                                fn_name = fc.name
                                args = dict(fc.args or {})
                                tool_calls.append({"name": fn_name, "arguments": args})

                                # Dispatch function
                                spec = next(
                                    (t for t in (tools or []) if t.name == fn_name),
                                    None,
                                )
                                if spec:
                                    try:
                                        result = spec.func(args)
                                        # Send function response back
                                        function_response = (
                                            types.Part.from_function_response(
                                                name=fn_name,
                                                response={"result": result},
                                            )
                                        )
                                        contents.append(
                                            candidate.content
                                        )  # Add model's response
                                        contents.append(
                                            types.Content(
                                                role="user", parts=[function_response]
                                            )
                                        )

                                        # Get final response
                                        resp = self.client.models.generate_content(
                                            model=model,
                                            contents=contents,
                                            config=config,
                                        )
                                    except Exception as e:
                                        self.logger.error(
                                            "Tool execution failed",
                                            function=fn_name,
                                            error=str(e),
                                        )
                                        # Continue without failing the entire request

            text = None
            try:
                text = resp.text
            except Exception as e:
                self.logger.warning(
                    "Failed to extract text from response", error=str(e)
                )

            # Calculate estimated cost (Gemini doesn't provide token usage in response)
            self._request_count += 1
            processing_time = int((time.time() - start_time) * 1000)

            return AIResponse(
                text=text,
                structured=_safe_parse_json(text),
                tool_calls=tool_calls,
                raw=resp,
                provider="gemini",
                model=model,
                processing_time_ms=processing_time,
            )

        except AIProviderError:
            raise
        except Exception as e:
            raise AIProviderError(
                error_type=ErrorType.API_ERROR,
                message=f"Unexpected Gemini error: {str(e)}",
                provider="gemini",
                correlation_id=self.correlation_id,
                original_exception=e,
            )

    def _classify_gemini_error(self, error: Exception) -> ErrorType:
        """Classify Gemini errors into standard error types."""
        error_str = str(error).lower()

        if "unauthorized" in error_str or "authentication" in error_str:
            return ErrorType.AUTHENTICATION_ERROR
        elif "quota" in error_str or "limit" in error_str:
            return ErrorType.QUOTA_EXCEEDED
        elif "timeout" in error_str:
            return ErrorType.TIMEOUT_ERROR
        elif "invalid" in error_str or "bad request" in error_str:
            return ErrorType.INVALID_REQUEST
        else:
            return ErrorType.API_ERROR

