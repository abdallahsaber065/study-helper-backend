"""
Utility functions for AI providers.
"""

import asyncio
import base64
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple, Type

import aiofiles
import magic
import orjson
import structlog
from pydantic import BaseModel

from .errors import AIProviderError
from .types import ErrorType

logger = structlog.get_logger(__name__)


def pydantic_to_json_schema(model: Type[BaseModel]) -> dict[str, Any]:
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


def safe_parse_json(text: Optional[str]) -> Optional[Any]:
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
