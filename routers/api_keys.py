"""
API key management routes.
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.security import get_current_active_user, encrypt_api_key
from core.logging import get_logger
from db_config import get_db
from models.models import User, AiApiKey, AiProviderEnum
from schemas.ai_cache import (
    AiApiKeyCreate, 
    AiApiKeyRead, 
    AiApiKeyUpdate, 
    AiApiKeyList,
    AiApiKeyTestRequest,
    AiApiKeyTestResponse
)
from services.ai_manager import AIManager

router = APIRouter(prefix="/api-keys", tags=["API Keys"])
logger = get_logger("api_keys")


@router.post("", response_model=AiApiKeyRead, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    api_key_data: AiApiKeyCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new API key for the current user.
    
    - **provider_name**: Name of the API provider (e.g., "Google", "OpenAI")
    - **api_key**: The actual API key (will be encrypted before storage)
    - **is_active**: Whether the key should be active
    """
    # Check if provider_name is valid
    try:
        provider = AiProviderEnum(api_key_data.provider_name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider name. Valid options are: {[p.value for p in AiProviderEnum]}"
        )
    
    # Test the API key validity before saving
    try:
        ai_manager = AIManager(db)
        # Initialize client with the provided key
        if provider == AiProviderEnum.Google:
            from google import genai
            client = genai.Client(api_key=api_key_data.api_key)
            # Simple test to check if the key is valid
            models = client.list_models()
            if not models:
                raise ValueError("Unable to list models with provided API key")
        elif provider == AiProviderEnum.OpenAI:
            import openai
            client = openai.OpenAI(api_key=api_key_data.api_key)
            # Simple test to check if the key is valid
            models = client.models.list()
            if not models:
                raise ValueError("Unable to list models with provided API key")
        
        # If we get here, the key is valid
        logger.info(
            "API key validated successfully", 
            user_id=current_user.id, 
            provider=provider.value
        )
    except Exception as e:
        logger.error(
            "Invalid API key", 
            error=str(e), 
            user_id=current_user.id, 
            provider=provider.value
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid API key for {provider.value}: {str(e)}"
        )
    
    # Encrypt the API key
    encrypted_key = encrypt_api_key(api_key_data.api_key)
    
    # Create new API key record
    db_api_key = AiApiKey(
        user_id=current_user.id,
        encrypted_api_key=encrypted_key,
        provider_name=provider,
        is_active=api_key_data.is_active
    )
    
    try:
        db.add(db_api_key)
        db.commit()
        db.refresh(db_api_key)
        
        logger.info(
            "API key created", 
            user_id=current_user.id, 
            provider=provider.value, 
            api_key_id=db_api_key.id
        )
        
        return db_api_key
    except IntegrityError as e:
        db.rollback()
        logger.error(
            "Failed to create API key - database error", 
            error=str(e), 
            user_id=current_user.id, 
            provider=provider.value
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key could not be created due to database constraint violation"
        )


@router.get("", response_model=AiApiKeyList)
async def list_api_keys(
    provider: Optional[str] = Query(None, description="Filter by provider name"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all API keys for the current user.
    
    Optionally filter by provider name and active status.
    """
    query = db.query(AiApiKey).filter(AiApiKey.user_id == current_user.id)
    
    # Apply filters if provided
    if provider:
        try:
            provider_enum = AiProviderEnum(provider)
            query = query.filter(AiApiKey.provider_name == provider_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid provider name. Valid options are: {[p.value for p in AiProviderEnum]}"
            )
    
    if is_active is not None:
        query = query.filter(AiApiKey.is_active == is_active)
    
    # Get total count and results
    total = query.count()
    api_keys = query.all()
    
    logger.info(
        "API keys listed", 
        user_id=current_user.id, 
        count=len(api_keys)
    )
    
    return AiApiKeyList(
        items=api_keys,
        total=total
    )


@router.get("/{api_key_id}", response_model=AiApiKeyRead)
async def get_api_key(
    api_key_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific API key by ID.
    """
    api_key = db.query(AiApiKey).filter(
        AiApiKey.id == api_key_id,
        AiApiKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    return api_key


@router.put("/{api_key_id}", response_model=AiApiKeyRead)
async def update_api_key(
    api_key_id: int,
    api_key_data: AiApiKeyUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update an API key.
    
    Can update the API key value, provider name, and active status.
    """
    api_key = db.query(AiApiKey).filter(
        AiApiKey.id == api_key_id,
        AiApiKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Update provider name if provided
    if api_key_data.provider_name is not None:
        try:
            provider = AiProviderEnum(api_key_data.provider_name)
            api_key.provider_name = provider
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid provider name. Valid options are: {[p.value for p in AiProviderEnum]}"
            )
    
    # Update API key if provided
    if api_key_data.api_key is not None:
        # Test the API key validity before saving
        try:
            if api_key.provider_name == AiProviderEnum.Google:
                from google import genai
                client = genai.Client(api_key=api_key_data.api_key)
                models = client.list_models()
                if not models:
                    raise ValueError("Unable to list models with provided API key")
            elif api_key.provider_name == AiProviderEnum.OpenAI:
                import openai
                client = openai.OpenAI(api_key=api_key_data.api_key)
                models = client.models.list()
                if not models:
                    raise ValueError("Unable to list models with provided API key")
            
            # If we get here, the key is valid
            encrypted_key = encrypt_api_key(api_key_data.api_key)
            api_key.encrypted_api_key = encrypted_key
            
            logger.info(
                "API key updated with new value", 
                user_id=current_user.id, 
                api_key_id=api_key_id,
                provider=api_key.provider_name.value
            )
        except Exception as e:
            logger.error(
                "Invalid API key", 
                error=str(e), 
                user_id=current_user.id, 
                provider=api_key.provider_name.value
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid API key for {api_key.provider_name.value}: {str(e)}"
            )
    
    # Update active status if provided
    if api_key_data.is_active is not None:
        api_key.is_active = api_key_data.is_active
    
    # Update timestamp
    api_key.updated_at = datetime.now(timezone.utc)
    
    try:
        db.commit()
        db.refresh(api_key)
        
        logger.info(
            "API key updated", 
            user_id=current_user.id, 
            api_key_id=api_key_id,
            provider=api_key.provider_name.value
        )
        
        return api_key
    except IntegrityError as e:
        db.rollback()
        logger.error(
            "Failed to update API key - database error", 
            error=str(e), 
            user_id=current_user.id, 
            api_key_id=api_key_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key could not be updated due to database constraint violation"
        )


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    api_key_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete an API key.
    """
    api_key = db.query(AiApiKey).filter(
        AiApiKey.id == api_key_id,
        AiApiKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    try:
        db.delete(api_key)
        db.commit()
        
        logger.info(
            "API key deleted", 
            user_id=current_user.id, 
            api_key_id=api_key_id,
            provider=api_key.provider_name.value
        )
        
    except Exception as e:
        db.rollback()
        logger.error(
            "Failed to delete API key", 
            error=str(e), 
            user_id=current_user.id, 
            api_key_id=api_key_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}"
        )


@router.post("/test", response_model=AiApiKeyTestResponse)
async def test_api_key(
    test_data: AiApiKeyTestRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Test if an API key is valid without saving it.
    """
    # Check if provider_name is valid
    try:
        provider = AiProviderEnum(test_data.provider_name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider name. Valid options are: {[p.value for p in AiProviderEnum]}"
        )
    
    # Test the API key
    try:
        if provider == AiProviderEnum.Google:
            from google import genai
            client = genai.Client(api_key=test_data.api_key)
            models = client.list_models()
            if not models:
                raise ValueError("Unable to list models with provided API key")
        elif provider == AiProviderEnum.OpenAI:
            import openai
            client = openai.OpenAI(api_key=test_data.api_key)
            models = client.models.list()
            if not models:
                raise ValueError("Unable to list models with provided API key")
        
        # If we get here, the key is valid
        logger.info(
            "API key test successful", 
            user_id=current_user.id, 
            provider=provider.value
        )
        
        return AiApiKeyTestResponse(
            is_valid=True,
            message=f"API key for {provider.value} is valid"
        )
    except Exception as e:
        logger.warning(
            "API key test failed", 
            error=str(e), 
            user_id=current_user.id, 
            provider=provider.value
        )
        
        return AiApiKeyTestResponse(
            is_valid=False,
            message=f"Invalid API key for {provider.value}: {str(e)}"
        ) 