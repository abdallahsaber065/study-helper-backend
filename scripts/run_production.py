#!/usr/bin/env python3
"""
Production run script for Study Helper Backend API.
Includes all Phase 7 enhancements and proper initialization.
"""
import os
import sys
import signal
import asyncio
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from core.logging import setup_logging, get_logger
from core.config import settings

# Setup logging first
setup_logging()
logger = get_logger("production")


def handle_signal(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Received shutdown signal", signal=signum)
    sys.exit(0)


def main():
    """Main entry point for production deployment."""
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    logger.info("Starting Study Helper Backend API", 
                version=settings.app_version,
                environment="production",
                debug=settings.debug)
    
    # Validate required environment variables
    required_vars = [
        "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME",
        "JWT_SECRET_KEY"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error("Missing required environment variables", 
                    missing=missing_vars)
        sys.exit(1)
    
    # Log configuration (without sensitive data)
    logger.info("Configuration loaded",
                database_host=settings.db_host,
                database_name=settings.db_name,
                debug=settings.debug,
                log_level=settings.log_level,
                enable_security_headers=settings.enable_security_headers,
                enable_rate_limiting=settings.enable_rate_limiting)
    
    # Run the application
    uvicorn_config = {
        "app": "main:app",
        "host": "0.0.0.0",
        "port": int(os.getenv("PORT", "8000")),
        "workers": int(os.getenv("WORKERS", "1")),
        "log_level": settings.log_level.lower(),
        "access_log": settings.enable_request_logging,
        "reload": False,  # Never reload in production
        "loop": "uvloop" if sys.platform != "win32" else "asyncio",
    }
    
    # Use SSL if certificates are provided
    ssl_keyfile = os.getenv("SSL_KEYFILE")
    ssl_certfile = os.getenv("SSL_CERTFILE")
    
    if ssl_keyfile and ssl_certfile:
        uvicorn_config.update({
            "ssl_keyfile": ssl_keyfile,
            "ssl_certfile": ssl_certfile,
        })
        logger.info("SSL enabled", keyfile=ssl_keyfile, certfile=ssl_certfile)
    
    logger.info("Starting uvicorn server", config=uvicorn_config)
    
    try:
        uvicorn.run(**uvicorn_config)
    except Exception as e:
        logger.error("Failed to start server", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main() 