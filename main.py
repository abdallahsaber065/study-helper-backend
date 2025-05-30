"""
FastAPI main application entry point.
"""
import os
from fastapi import FastAPI, Depends
import json
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from db_config import get_db
from models.models import Base, User, AiApiKey, AiProviderEnum
from app import app
from core.security import get_password_hash, encrypt_api_key
from core.config import settings

os.makedirs("cache", exist_ok=True)

# Flag to prevent duplicate startup execution
_startup_executed = False

@app.on_event("startup")
async def startup_db_client():
    """Initialize database and default users on startup."""
    global _startup_executed
    
    if _startup_executed:
        return
    
    try:
        db = next(get_db())
        
        # Create default admin user if not exists
        admin_username = settings.default_admin_username
        admin_email = settings.default_admin_email
        admin_password = settings.default_admin_password
        force_reset_admin = settings.force_reset_password_admin
        
        # Create default free user if not exists
        free_username = settings.default_free_user_username
        free_email = settings.default_free_user_email
        free_password = settings.default_free_user_password
        force_reset_free = settings.force_reset_password_free
        
        # Get Gemini API key
        gemini_api_key = settings.gemini_api_key
        
        if admin_username and admin_email and admin_password:
            admin_user = db.query(User).filter(User.username == admin_username).first()
            
            if not admin_user:
                admin_user = User(
                    username=admin_username,
                    email=admin_email,
                    password_hash=get_password_hash(admin_password),
                    first_name="Admin",
                    last_name="User",
                    role="admin",
                    is_active=True,
                    is_verified=True
                )
                db.add(admin_user)
                db.commit()
                db.refresh(admin_user)
            elif force_reset_admin:
                admin_user.password_hash = get_password_hash(admin_password)
                db.commit()
        
        if free_username and free_email and free_password:
            free_user = db.query(User).filter(User.username == free_username).first()
            
            if not free_user:
                free_user = User(
                    username=free_username,
                    email=free_email,
                    password_hash=get_password_hash(free_password),
                    first_name="Free",
                    last_name="User",
                    role="user",
                    is_active=True,
                    is_verified=True
                )
                db.add(free_user)
                db.commit()
                db.refresh(free_user)
            elif force_reset_free:
                free_user.password_hash = get_password_hash(free_password)
                db.commit()
            
            # Add Gemini API key to free user if provided
            if gemini_api_key and free_user:
                # Check if key already exists
                existing_key = db.query(AiApiKey).filter(
                    AiApiKey.user_id == free_user.id,
                    AiApiKey.provider_name == AiProviderEnum.Google
                ).first()
                
                if not existing_key:
                    api_key = AiApiKey(
                        user_id=free_user.id,
                        provider_name=AiProviderEnum.Google,
                        encrypted_api_key=encrypt_api_key(gemini_api_key),
                        is_active=True
                    )
                    db.add(api_key)
                    db.commit()
                
        # Mark startup as completed
        _startup_executed = True
                
    except Exception as e:
        _startup_executed = True  # Prevent retry loops

# Run the application
if __name__ == "__main__":
    # Export OpenAPI schema to a JSON file
    try:
        openapi_schema = app.openapi()
        output_path = "cache/openapi.json"
        with open(output_path, "w") as f:
            json.dump(openapi_schema, f, indent=2)
        print(f"OpenAPI schema successfully exported to {output_path}")
    except Exception as e:
        print(f"Error exporting OpenAPI schema: {e}")

    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
