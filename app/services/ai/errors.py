"""
Error handling classes for AI providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .types import ErrorType


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
