"""
Central AI Manager service for handling interactions with AI providers.
"""
import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, TypeVar, Type, Generic, List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from models.models import AiApiKey, GeminiFileCache, AiProviderEnum, PhysicalFile, UserFileAccess
from schemas.ai_cache import GeminiFileCacheCreate
from core.config import settings
from core.security import verify_password, get_password_hash

T = TypeVar('T', bound=BaseModel)


class AIManager(Generic[T]):
    """
    Central manager for AI provider interactions.
    
    This class handles:
    - Retrieving API keys
    - Managing file uploads to AI providers
    - Checking/updating the AI file cache
    - Constructing AI requests with appropriate configurations
    - Executing AI model calls
    """
    
    def __init__(self, db: Session):
        self.db = db
        self._gemini_client = None
        self._openai_client = None
    
    async def get_api_key(self, user_id: int, provider: AiProviderEnum) -> Optional[str]:
        """
        Get an API key for the specified provider and user.
        
        Args:
            user_id: The ID of the user
            provider: The AI provider to get the key for
            
        Returns:
            str: The decrypted API key or None if not found
        """
        # Try to get a user-specific key first
        api_key_record = self.db.query(AiApiKey).filter(
            AiApiKey.user_id == user_id,
            AiApiKey.provider_name == provider,
            AiApiKey.is_active == True
        ).first()
        
        if api_key_record:
            # Decrypt the API key - for now we'll just return the encrypted version
            # In a real implementation, you'd decrypt this
            return api_key_record.encrypted_api_key
        
        # Fall back to system-wide key from settings
        if provider == AiProviderEnum.Google:
            return settings.gemini_api_key
        elif provider == AiProviderEnum.OpenAI:
            return settings.openai_api_key
        
        return None
    
    async def initialize_gemini_client(self, user_id: int) -> bool:
        """
        Initialize the Google Gemini client for the user.
        
        Args:
            user_id: The ID of the user
            
        Returns:
            bool: True if initialization was successful
        """
        try:
            from google import genai
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google Generative AI library not installed"
            )
        
        api_key = await self.get_api_key(user_id, AiProviderEnum.Google)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No Google Gemini API key available"
            )
        
        self._gemini_client = genai.Client(api_key=api_key)
        return True
    
    async def initialize_openai_client(self, user_id: int) -> bool:
        """
        Initialize the OpenAI client for the user.
        
        Args:
            user_id: The ID of the user
            
        Returns:
            bool: True if initialization was successful
        """
        try:
            import openai
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OpenAI library not installed"
            )
        
        api_key = await self.get_api_key(user_id, AiProviderEnum.OpenAI)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No OpenAI API key available"
            )
        
        self._openai_client = openai.OpenAI(api_key=api_key)
        return True
    
    async def upload_file_to_gemini(
        self, 
        physical_file: PhysicalFile,
        user_id: int
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
        api_key_record = self.db.query(AiApiKey).filter(
            AiApiKey.user_id == user_id,
            AiApiKey.provider_name == AiProviderEnum.Google,
            AiApiKey.is_active == True
        ).first()
        
        # If no user-specific key, create a temporary record for the system key
        if not api_key_record:
            api_key_record = AiApiKey(
                user_id=user_id,
                provider_name=AiProviderEnum.Google,
                encrypted_api_key=get_password_hash(settings.gemini_api_key or ""),
                is_active=True
            )
            self.db.add(api_key_record)
            self.db.commit()
            self.db.refresh(api_key_record)
        
        # Check if the file is already in the cache and not expired
        cache_entry = self.db.query(GeminiFileCache).filter(
            GeminiFileCache.physical_file_id == physical_file.id,
            GeminiFileCache.api_key_id == api_key_record.id,
            (GeminiFileCache.expiration_time > datetime.now(datetime.UTC)) | (GeminiFileCache.expiration_time.is_(None))
        ).first()
        
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
                config=dict(
                    mime_type=mime_type,
                    display_name=display_name
                )
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
                expiration_time=file_info.expiration_time
            )
            
            # Check if there's an expired entry to update
            expired_entry = self.db.query(GeminiFileCache).filter(
                GeminiFileCache.physical_file_id == physical_file.id,
                GeminiFileCache.api_key_id == api_key_record.id
            ).first()
            
            if expired_entry:
                # Update the expired entry
                for field, value in cache_data.dict().items():
                    setattr(expired_entry, field, value)
                expired_entry.updated_at = datetime.utcnow()
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
                detail=f"Failed to upload file to Gemini: {str(e)}"
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
                physical_file = self.db.query(PhysicalFile).filter(PhysicalFile.id == file_id).first()
                if not physical_file:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"File with ID {file_id} not found"
                    )
                
                # Check if user has access to the file
                user_file_access = self.db.query(UserFileAccess).filter(
                    UserFileAccess.physical_file_id == file_id,
                    UserFileAccess.user_id == user_id
                ).first()
                
                # If not explicitly granted access, check if user is the uploader
                if not user_file_access and physical_file.user_id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"You don't have access to file with ID {file_id}"
                    )
                
                # Upload file to Gemini and get cache entry
                cache_entry = await self.upload_file_to_gemini(physical_file, user_id)
                
                # Add file to contents
                contents.append(cache_entry.gemini_file_unique_name)
        
        # Add prompt to contents
        contents.append(prompt)
        
        return contents
    
    async def generate_content_with_gemini(
        self,
        user_id: int,
        prompt: str,
        physical_file_ids: Optional[List[int]] = None,
        model: str = "gemini-2.0-flash",
        response_schema: Optional[Type[T]] = None,
        system_instruction: Optional[str] = None
    ) -> Any:
        """
        Generate content using Gemini model.
        
        Args:
            user_id: The ID of the user
            prompt: The text prompt
            physical_file_ids: Optional list of file IDs to include
            model: The Gemini model to use
            response_schema: Optional Pydantic schema for structured response
            system_instruction: Optional system instructions
            
        Returns:
            The generated content (format depends on response_schema)
        """
        # Initialize Gemini client if not already done
        if not self._gemini_client:
            await self.initialize_gemini_client(user_id)
        
        # Get content parts
        contents = await self.generate_content_parts(user_id, prompt, physical_file_ids)
        
        # Prepare generation config
        generation_config = {}
        
        if system_instruction:
            from google.genai import types
            generation_config["system_instruction"] = system_instruction
        
        if response_schema:
            from google.genai import types
            generation_config["response_mime_type"] = "application/json"
            generation_config["response_schema"] = response_schema.model_json_schema(by_alias=True)
        
        try:
            # Generate content
            if generation_config:
                from google.genai import types
                response = self._gemini_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(**generation_config)
                )
            else:
                response = self._gemini_client.models.generate_content(
                    model=model,
                    contents=contents
                )
            
            # Update last_used_at for the API key
            api_key_record = self.db.query(AiApiKey).filter(
                AiApiKey.user_id == user_id,
                AiApiKey.provider_name == AiProviderEnum.Google,
                AiApiKey.is_active == True
            ).first()
            
            if api_key_record:
                api_key_record.last_used_at = datetime.now(datetime.UTC)
                self.db.commit()
            
            # Return parsed response if schema provided, otherwise return text
            if response_schema:
                try:
                    json_response = json.loads(response.text)
                    return response_schema.model_validate(json_response)
                except Exception as e:
                    # If parsing fails, return the raw text
                    return response.text
            else:
                return response.text
            
        except Exception as e:
            # Log the error
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate content with Gemini: {str(e)}"
            ) 