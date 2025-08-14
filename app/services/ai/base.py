"""
Base AI provider interface with comprehensive error handling and monitoring.
"""

import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import magic
import structlog
from circuitbreaker import circuit
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .errors import AIProviderError
from .types import AIProviderConfig, AIResponse, ErrorType, RequestValidation, ToolSpec

logger = structlog.get_logger(__name__)


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
