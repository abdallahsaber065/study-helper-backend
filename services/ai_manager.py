"""
Central AI Manager service for handling interactions with AI providers.
"""

import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, TypeVar, Type, Generic, List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from models.models import (
    AiApiKey,
    GeminiFileCache,
    AiProviderEnum,
    PhysicalFile,
    UserFileAccess,
    UserFreeApiUsage,
    User,
)
from schemas.ai_cache import GeminiFileCacheCreate
from core.config import settings
from core.security import verify_password, get_password_hash, decrypt_api_key
from core.exceptions import AIServiceException
import structlog

T = TypeVar("T", bound=BaseModel)
logger = structlog.get_logger("ai_manager")


class AIRetryConfig:
    """Configuration for AI service retry logic."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
        timeout_seconds: float = 120.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.timeout_seconds = timeout_seconds


class AIManager(Generic[T]):
    """
    Central manager for AI provider interactions.

    This class handles:
    - Retrieving API keys
    - Managing file uploads to AI providers
    - Checking/updating the AI file cache
    - Constructing AI requests with appropriate configurations
    - Executing AI model calls with retry logic and error handling
    """

    def __init__(self, db: Session, retry_config: Optional[AIRetryConfig] = None):
        self.db = db
        self._gemini_client = None
        self._openai_client = None
        self.retry_config = retry_config or AIRetryConfig()

    async def get_api_key(
        self, user_id: int, provider: AiProviderEnum
    ) -> Optional[str]:
        """
        Get the API key for a user and provider.
        Falls back to free tier if user doesn't have their own key.
        """
        try:
            # First, try to get the user's own API key
            user_key = (
                self.db.query(AiApiKey)
                .filter(
                    AiApiKey.user_id == user_id,
                    AiApiKey.provider_name == provider,
                    AiApiKey.is_active == True,
                )
                .first()
            )

            if user_key:
                logger.info(
                    "Using user's own API key", user_id=user_id, provider=provider.value
                )
                return decrypt_api_key(user_key.encrypted_api_key)

            # Check free tier usage
            await self.check_free_tier_usage(user_id, provider)

            # Try to get the key from the free user
            free_username = os.getenv("DEFAULT_FREE_USER_USERNAME")
            logger.debug("Looking for free user", username=free_username)

            if free_username:
                free_user = (
                    self.db.query(User).filter(User.username == free_username).first()
                )
                if free_user:
                    free_user_key = (
                        self.db.query(AiApiKey)
                        .filter(
                            AiApiKey.user_id == free_user.id,
                            AiApiKey.provider_name == provider,
                            AiApiKey.is_active == True,
                        )
                        .first()
                    )

                    if free_user_key:
                        logger.info(
                            "Using free tier API key",
                            user_id=user_id,
                            provider=provider.value,
                        )
                        return decrypt_api_key(free_user_key.encrypted_api_key)
                    else:
                        logger.warning(
                            "Free user has no API key", provider=provider.value
                        )
                else:
                    logger.warning("Free user not found", username=free_username)

            # Fall back to system key if free user key not found
            logger.debug(
                "Falling back to system environment key", provider=provider.value
            )
            system_key = None

            if provider == AiProviderEnum.Google:
                system_key = settings.gemini_api_key
            elif provider == AiProviderEnum.OpenAI:
                system_key = settings.openai_api_key

            if system_key:
                logger.info("Using system API key", provider=provider.value)
                return system_key

            logger.error(
                "No API key available", user_id=user_id, provider=provider.value
            )
            raise AIServiceException(
                detail=f"No {provider.value} API key available. Please add your own API key.",
                provider=provider.value,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Error retrieving API key",
                error=str(e),
                user_id=user_id,
                provider=provider.value,
            )
            raise AIServiceException(
                detail=f"Failed to retrieve API key: {str(e)}", provider=provider.value
            )

    async def check_free_tier_usage(self, user_id: int, provider: AiProviderEnum):
        """
        Check if the user has exceeded their free tier usage limit.
        """
        try:
            free_tier_limit = (
                settings.free_tier_gemini_limit
                if provider == AiProviderEnum.Google
                else settings.free_tier_openai_limit
            )

            usage_record = (
                self.db.query(UserFreeApiUsage)
                .filter(
                    UserFreeApiUsage.user_id == user_id,
                    UserFreeApiUsage.api_provider == provider,
                )
                .first()
            )

            if not usage_record:
                return  # No usage record means they're within limits

            logger.debug(
                "Checking free tier usage",
                user_id=user_id,
                usage_count=usage_record.usage_count,
                limit=free_tier_limit,
            )

            if usage_record.usage_count >= free_tier_limit:
                logger.warning(
                    "User exceeded free tier limit",
                    user_id=user_id,
                    provider=provider.value,
                    usage=usage_record.usage_count,
                    limit=free_tier_limit,
                )
                raise AIServiceException(
                    detail=f"You have reached your free tier limit ({free_tier_limit}) for {provider.value}. Please add your own API key.",
                    provider=provider.value,
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                "Error checking free tier usage",
                error=str(e),
                user_id=user_id,
                provider=provider.value,
            )
            raise AIServiceException(
                detail=f"Failed to check usage limits: {str(e)}",
                provider=provider.value,
            )

    async def increment_free_tier_usage(self, user_id: int, provider: AiProviderEnum):
        """
        Increment the free tier usage count for a user.
        """
        try:
            usage_record = (
                self.db.query(UserFreeApiUsage)
                .filter(
                    UserFreeApiUsage.user_id == user_id,
                    UserFreeApiUsage.api_provider == provider,
                )
                .first()
            )

            if not usage_record:
                usage_record = UserFreeApiUsage(
                    user_id=user_id,
                    api_provider=provider,
                    usage_count=1,
                    last_used_at=datetime.now(timezone.utc),
                )
                self.db.add(usage_record)
            else:
                usage_record.usage_count += 1
                usage_record.last_used_at = datetime.now(timezone.utc)

            self.db.commit()
            logger.debug(
                "Incremented free tier usage",
                user_id=user_id,
                provider=provider.value,
                new_count=usage_record.usage_count,
            )

        except Exception as e:
            logger.error(
                "Error incrementing usage",
                error=str(e),
                user_id=user_id,
                provider=provider.value,
            )
            self.db.rollback()

    async def initialize_gemini_client(self, user_id: int) -> bool:
        """
        Initialize the Google Gemini client for the user.
        """
        try:
            from google import genai
        except ImportError:
            logger.error("Google Generative AI library not installed")
            raise AIServiceException(
                detail="Google Generative AI library not installed", provider="Google"
            )

        api_key = await self.get_api_key(user_id, AiProviderEnum.Google)
        if not api_key:
            raise AIServiceException(
                detail="No Google Gemini API key available", provider="Google"
            )

        self._gemini_client = genai.Client(api_key=api_key)
        logger.info("Gemini client initialized", user_id=user_id)
        return True

    async def initialize_openai_client(self, user_id: int) -> bool:
        """
        Initialize the OpenAI client for the user.
        """
        try:
            import openai
        except ImportError:
            logger.error("OpenAI library not installed")
            raise AIServiceException(
                detail="OpenAI library not installed", provider="OpenAI"
            )

        api_key = await self.get_api_key(user_id, AiProviderEnum.OpenAI)
        if not api_key:
            raise AIServiceException(
                detail="No OpenAI API key available", provider="OpenAI"
            )

        self._openai_client = openai.OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized", user_id=user_id)
        return True

    async def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Execute a function with exponential backoff retry logic.
        """
        last_exception = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await asyncio.wait_for(
                        func(*args, **kwargs), timeout=self.retry_config.timeout_seconds
                    )
                else:
                    return func(*args, **kwargs)

            except asyncio.TimeoutError as e:
                last_exception = e
                logger.warning(
                    "AI request timeout",
                    attempt=attempt + 1,
                    timeout=self.retry_config.timeout_seconds,
                )

            except Exception as e:
                last_exception = e
                logger.warning("AI request failed", attempt=attempt + 1, error=str(e))

            # Don't retry on the last attempt
            if attempt < self.retry_config.max_retries:
                delay = min(
                    self.retry_config.base_delay
                    * (self.retry_config.backoff_multiplier**attempt),
                    self.retry_config.max_delay,
                )
                logger.info(
                    "Retrying AI request", delay_seconds=delay, attempt=attempt + 1
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        logger.error("All AI request retries exhausted", error=str(last_exception))
        if isinstance(last_exception, asyncio.TimeoutError):
            raise AIServiceException(
                detail=f"AI request timeout after {self.retry_config.timeout_seconds} seconds"
            )
        else:
            raise AIServiceException(
                detail=f"AI request failed after {self.retry_config.max_retries} retries: {str(last_exception)}"
            )

    async def upload_file_to_gemini(
        self, physical_file: PhysicalFile, user_id: int
    ) -> GeminiFileCache:
        """
        Upload a file to Gemini API, checking the cache first.

        Args:
            physical_file: The physical file record
            user_id: The ID of the user

        Returns:
            GeminiFileCache: The cache record for the uploaded file
        """
        # Initialize Gemini client if not already done
        if not self._gemini_client:
            await self.initialize_gemini_client(user_id)

        # Get the API key ID
        api_key_record = (
            self.db.query(AiApiKey)
            .filter(
                AiApiKey.user_id == user_id,
                AiApiKey.provider_name == AiProviderEnum.Google,
                AiApiKey.is_active == True,
            )
            .first()
        )

        # If no user-specific key, try to get the free user's key
        if not api_key_record:
            # First get the free user by username
            free_user = (
                self.db.query(User)
                .filter(User.username == settings.default_free_user_username)
                .first()
            )

            if free_user:
                # Get the free user's API key
                api_key_record = (
                    self.db.query(AiApiKey)
                    .filter(
                        AiApiKey.user_id == free_user.id,
                        AiApiKey.provider_name == AiProviderEnum.Google,
                        AiApiKey.is_active == True,
                    )
                    .first()
                )

        # If still no API key found, raise an error
        if not api_key_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No API key available for Google Gemini",
            )

        # Check if the file is already in the cache and not expired
        cache_entry = (
            self.db.query(GeminiFileCache)
            .filter(
                GeminiFileCache.physical_file_id == physical_file.id,
                GeminiFileCache.api_key_id == api_key_record.id,
                (GeminiFileCache.expiration_time > datetime.now(timezone.utc))
                | (GeminiFileCache.expiration_time.is_(None)),
            )
            .first()
        )

        # If valid cache entry exists, return it
        if cache_entry:
            return cache_entry

        # Otherwise, upload the file to Gemini
        try:
            # Get file MIME type
            mime_type = physical_file.mime_type
            display_name = physical_file.file_name

            # Upload the file
            gemini_file = self._gemini_client.files.upload(
                file=physical_file.file_path,
                config=dict(mime_type=mime_type, display_name=display_name),
            )

            # Get file info including expiration
            file_info = self._gemini_client.files.get(name=gemini_file.name)

            # Create or update cache entry
            cache_data = GeminiFileCacheCreate(
                physical_file_id=physical_file.id,
                api_key_id=api_key_record.id,
                gemini_file_uri=file_info.uri,
                gemini_display_name=file_info.display_name,
                gemini_file_unique_name=file_info.name,
                expiration_time=file_info.expiration_time,
            )

            # Check if there's an expired entry to update
            expired_entry = (
                self.db.query(GeminiFileCache)
                .filter(
                    GeminiFileCache.physical_file_id == physical_file.id,
                    GeminiFileCache.api_key_id == api_key_record.id,
                )
                .first()
            )

            if expired_entry:
                # Update the expired entry
                for field, value in cache_data.dict().items():
                    setattr(expired_entry, field, value)
                expired_entry.updated_at = datetime.now(timezone.utc)
                self.db.commit()
                self.db.refresh(expired_entry)
                return expired_entry
            else:
                # Create a new cache entry
                new_cache_entry = GeminiFileCache(**cache_data.dict())
                self.db.add(new_cache_entry)
                self.db.commit()
                self.db.refresh(new_cache_entry)
                return new_cache_entry

        except Exception as e:
            # Log the error
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file to Gemini: {str(e)}",
            )

    async def generate_content_parts(
        self,
        user_id: int,
        prompt: str,
        physical_file_ids: Optional[List[int]] = None,
    ) -> List[Any]:
        """
        Prepare content parts for the AI model, including multiple files if provided.

        Args:
            user_id: The ID of the user
            prompt: The text prompt
            physical_file_ids: Optional list of file IDs to include

        Returns:
            List: The content parts ready for the AI model
        """
        # Initialize Gemini client if not already done
        if not self._gemini_client:
            await self.initialize_gemini_client(user_id)

        # Prepare contents list
        contents = []

        # Add files if provided
        if physical_file_ids and len(physical_file_ids) > 0:
            for file_id in physical_file_ids:
                physical_file = (
                    self.db.query(PhysicalFile)
                    .filter(PhysicalFile.id == file_id)
                    .first()
                )
                if not physical_file:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"File with ID {file_id} not found",
                    )

                # Check if user has access to the file
                user_file_access = (
                    self.db.query(UserFileAccess)
                    .filter(
                        UserFileAccess.physical_file_id == file_id,
                        UserFileAccess.user_id == user_id,
                    )
                    .first()
                )

                # If not explicitly granted access, check if user is the uploader
                if not user_file_access and physical_file.user_id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"You don't have access to file with ID {file_id}",
                    )

                # Upload file to Gemini and get cache entry
                cache_entry = await self.upload_file_to_gemini(physical_file, user_id)

                # Add file to contents
                contents.append(cache_entry.gemini_file_uri)

        # Add prompt to contents
        contents.append(prompt)

        return contents

    async def generate_content_with_gemini(
        self,
        user_id: int,
        prompt: str,
        physical_file_ids: Optional[List[int]] = None,
        model: str = "gemini-2.5-flash-preview-05-20",
        response_schema: Optional[Type[T]] = None,
        system_instruction: Optional[str] = None,
    ) -> Any:
        """
        Generate content using Google Gemini with enhanced error handling and retry logic.
        """
        if not self._gemini_client:
            await self.initialize_gemini_client(user_id)

        async def _generate():
            contents = []
            generation_config = {}

            # Add files to contents if provided
            if physical_file_ids:
                for file_id in physical_file_ids:
                    physical_file = (
                        self.db.query(PhysicalFile)
                        .filter(PhysicalFile.id == file_id)
                        .first()
                    )
                    if physical_file:
                        cache_entry = await self.upload_file_to_gemini(
                            physical_file, user_id
                        )
                        # Use the correct file reference format for Gemini
                        file_ref = cache_entry.gemini_file_uri
                        contents.append(file_ref)

            # Add prompt after files
            contents.append(prompt)

            # Configure generation parameters
            if response_schema:
                generation_config["response_mime_type"] = "application/json"
                generation_config["response_schema"] = (
                    response_schema.model_json_schema()
                )

            if system_instruction:
                generation_config["system_instruction"] = system_instruction

            if model.startswith("gemini-2.5"):
                generation_config["max_output_tokens"] = 65000
            else:
                generation_config["max_output_tokens"] = 65000

            # Generate content
            if generation_config:
                from google.genai import types

                response = self._gemini_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(**generation_config),
                )
            else:
                response = self._gemini_client.models.generate_content(
                    model=model, contents=contents
                )

            return response

        try:
            logger.info(
                "Starting Gemini content generation",
                user_id=user_id,
                model=model,
                has_files=bool(physical_file_ids),
                has_schema=bool(response_schema),
            )

            response = await self._retry_with_backoff(_generate)

            # Increment free tier usage
            await self.increment_free_tier_usage(user_id, AiProviderEnum.Google)

            # Update last_used_at for the API key
            api_key_record = (
                self.db.query(AiApiKey)
                .filter(
                    AiApiKey.user_id == user_id,
                    AiApiKey.provider_name == AiProviderEnum.Google,
                    AiApiKey.is_active == True,
                )
                .first()
            )

            if api_key_record:
                api_key_record.last_used_at = datetime.now(timezone.utc)
                self.db.commit()

            # Parse response
            if response_schema:
                try:
                    json_response = json.loads(response.text)
                    return response_schema.model_validate(json_response)
                except Exception as e:
                    logger.warning("Failed to parse structured response", error=str(e))
                    return response.text
            else:
                return response.text

        except AIServiceException:
            raise
        except Exception as e:
            logger.error(
                "Gemini content generation failed", error=str(e), user_id=user_id
            )
            raise AIServiceException(
                detail=f"Failed to generate content with Gemini: {str(e)}",
                provider="Google",
            )
