"""
Factory for creating AI providers with configuration.
"""

import os
import uuid

from .base import AIProvider
from .errors import AIProviderError
from .providers import AnthropicProvider, GeminiProvider, OpenAIProvider
from .types import AIProviderConfig, AIProviderType, ErrorType


class AIProviderFactory:
    """Factory for creating AI providers with configuration."""

    @staticmethod
    def create_provider(provider_type: AIProviderType, **config_kwargs) -> AIProvider:
        """Create an AI provider instance with configuration."""
        config = AIProviderConfig(provider_type=provider_type, **config_kwargs)

        if provider_type == AIProviderType.OPENAI:
            return OpenAIProvider(config)
        elif provider_type == AIProviderType.GEMINI:
            return GeminiProvider(config)
        elif provider_type == AIProviderType.ANTHROPIC:
            return AnthropicProvider(config)
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    @staticmethod
    def create_from_env(provider_type: AIProviderType) -> AIProvider:
        """Create provider using environment variables."""
        env_configs = {
            AIProviderType.OPENAI: {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
            },
            AIProviderType.GEMINI: {
                "api_key": os.getenv("GEMINI_API_KEY"),
                "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            },
            AIProviderType.ANTHROPIC: {
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "model": os.getenv("ANTHROPIC_MODEL", "claude-4-opus-20250805"),
            },
        }

        config_data = env_configs.get(provider_type)
        if not config_data or not config_data["api_key"]:
            raise AIProviderError(
                error_type=ErrorType.AUTHENTICATION_ERROR,
                message=f"API key not found for {provider_type.value}",
                provider=provider_type.value,
                correlation_id=str(uuid.uuid4()),
            )

        return AIProviderFactory.create_provider(provider_type, **config_data)
