"""
FastAPI main application entry point.
"""

import json
import os
import uvicorn

# Import logging system first
from core.logging import setup_logging, get_logger, database_logger

# Setup logging early
setup_logging()
logger = get_logger("main")

from db_config import get_db
from models.models import Base, User, AiApiKey, AiProviderEnum
from app import app
from core.security import get_password_hash, encrypt_api_key
from core.config import settings

os.makedirs("cache", exist_ok=True)


@app.on_event("startup")
async def startup_db_client():
    """Initialize database and default users on startup."""
    logger.info("Starting database initialization")

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
                logger.info("Creating default admin user", username=admin_username)
                admin_user = User(
                    username=admin_username,
                    email=admin_email,
                    password_hash=get_password_hash(admin_password),
                    first_name="Admin",
                    last_name="User",
                    role="admin",
                    is_active=True,
                    is_verified=True,
                )
                db.add(admin_user)
                db.commit()
                db.refresh(admin_user)
                logger.info(
                    "Default admin user created successfully", user_id=admin_user.id
                )
            elif force_reset_admin:
                logger.info("Resetting admin user password", username=admin_username)
                admin_user.password_hash = get_password_hash(admin_password)
                db.commit()
                logger.info("Admin user password reset successfully")

        if free_username and free_email and free_password:
            free_user = db.query(User).filter(User.username == free_username).first()

            if not free_user:
                logger.info("Creating default free user", username=free_username)
                free_user = User(
                    username=free_username,
                    email=free_email,
                    password_hash=get_password_hash(free_password),
                    first_name="Free",
                    last_name="User",
                    role="user",
                    is_active=True,
                    is_verified=True,
                )
                db.add(free_user)
                db.commit()
                db.refresh(free_user)
                logger.info(
                    "Default free user created successfully", user_id=free_user.id
                )
            elif force_reset_free:
                logger.info("Resetting free user password", username=free_username)
                free_user.password_hash = get_password_hash(free_password)
                db.commit()
                logger.info("Free user password reset successfully")

            # Add Gemini API key to free user if provided
            if gemini_api_key and free_user:
                # Check if key already exists
                existing_key = (
                    db.query(AiApiKey)
                    .filter(
                        AiApiKey.user_id == free_user.id,
                        AiApiKey.provider_name == AiProviderEnum.Google,
                    )
                    .first()
                )

                if not existing_key:
                    logger.info(
                        "Adding Gemini API key to free user", user_id=free_user.id
                    )
                    api_key = AiApiKey(
                        user_id=free_user.id,
                        provider_name=AiProviderEnum.Google,
                        encrypted_api_key=encrypt_api_key(gemini_api_key),
                        is_active=True,
                    )
                    db.add(api_key)
                    db.commit()
                    logger.info("Gemini API key added successfully")
                else:
                    logger.info("Gemini API key already exists for free user")

        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error("Error initializing database", error=str(e), exc_info=True)
        database_logger.error(
            "Database initialization failed", error=str(e), exc_info=True
        )


# Run the application
if __name__ == "__main__":
    # Export OpenAPI schema to a JSON file
    try:
        logger.info("Exporting OpenAPI schema")
        openapi_schema = app.openapi()
        output_path = "cache/openapi.json"
        with open(output_path, "w") as f:
            json.dump(openapi_schema, f, indent=2)
        logger.info("OpenAPI schema successfully exported", output_path=output_path)
    except Exception as e:
        logger.error("Error exporting OpenAPI schema", error=str(e), exc_info=True)

    logger.info("Starting uvicorn server with reload enabled, ignoring 'log' folder", host="0.0.0.0", port=8000)
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        reload_excludes=["*.pyc", "*.log","*.db", "*.json"],
        reload_includes=["*.py"],
    )
