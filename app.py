from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# Import logging system
from core.logging import setup_logging, get_logger, app_logger

# Import Phase 7 enhancements
from core.exceptions import setup_exception_handlers
from core.middleware import setup_middleware

# Import routers
from routers import (
    auth, users, files, summaries, mcqs, communities, 
    interactions, notifications, preferences, versioning, 
    analytics, background_tasks, health, api_keys
)

# Initialize logging system early
setup_logging()
logger = get_logger("fastapi")

# Create FastAPI app instance
app = FastAPI(
    title="Study Helper Backend API",
    description="Backend API for the Study Helper application with AI-powered features",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Setup global exception handlers
setup_exception_handlers(app)

# Setup security middleware
middleware_config = {
    "enable_security_headers": True,
    "enable_request_logging": True,
    "enable_size_limit": True,
    "max_request_size": 50 * 1024 * 1024,  # 50MB
    "enable_timeout": True,
    "timeout_seconds": 300,  # 5 minutes
    "enable_ip_whitelist": False,  # Disabled by default
}
setup_middleware(app, middleware_config)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(files.router)
app.include_router(summaries.router)
app.include_router(mcqs.router)
app.include_router(communities.router)
app.include_router(interactions.router)
app.include_router(notifications.router)
app.include_router(preferences.router)
app.include_router(versioning.router)
app.include_router(analytics.router)
app.include_router(background_tasks.router)
app.include_router(health.router)  # Add health check router
app.include_router(api_keys.router)  # Add API key management router


# Enhanced health check endpoint (keep the simple one for backwards compatibility)
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Basic health check endpoint to verify the API is running.
    """
    logger.info("Health check endpoint accessed")
    return {"status": "ok", "message": "Study Helper Backend API is running"}


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint providing basic API information.
    """
    logger.info("Root endpoint accessed")
    return {
        "message": "Welcome to Study Helper Backend API",
        "version": "0.1.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "health_checks": {
            "basic": "/health",
            "detailed": "/health/detailed",
            "database": "/health/database",
            "ai_services": "/health/ai-services", 
            "system": "/health/system"
        }
    }


# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Handle application startup."""
    app_logger.info("FastAPI application starting up", extra={"component": "startup"})


@app.on_event("shutdown")
async def shutdown_event():
    """Handle application shutdown."""
    app_logger.info("FastAPI application shutting down", extra={"component": "shutdown"})
