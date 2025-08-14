"""Main FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import close_db, init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown."""
    # Startup
    await init_db()
    
    # Ensure upload directory exists
    from app.files.utils import ensure_upload_directory
    ensure_upload_directory()
    
    yield
    # Shutdown
    from app.services.email_service import cleanup_email_service
    await cleanup_email_service()
    await close_db()


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="AI-powered Quiz & Summary Generation Platform Backend",
    version=settings.version,
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Security middleware
if settings.environment == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"],  # Configure with your actual domain
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


# Health check endpoints
@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
    }


@app.get("/health/detailed", tags=["Health"])
async def detailed_health_check() -> dict:
    """Detailed health check with dependency status."""
    from app.database import check_db_health
    from app.services.email_service import get_email_service

    db_healthy = await check_db_health()
    
    # Check email service health
    try:
        email_service = get_email_service()
        email_health = await email_service.health_check()
        email_healthy = email_health["status"] == "healthy"
    except Exception:
        email_healthy = False
        email_health = {"status": "unhealthy", "error": "Service unavailable"}

    overall_healthy = db_healthy and email_healthy

    health_status = {
        "status": "healthy" if overall_healthy else "unhealthy",
        "service": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "dependencies": {
            "database": "healthy" if db_healthy else "unhealthy",
            "email_service": email_health,
        },
    }

    status_code = 200 if overall_healthy else 503
    return JSONResponse(content=health_status, status_code=status_code)


# Root endpoint
@app.get("/", tags=["Root"])
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.version,
        "docs_url": "/docs" if settings.debug else None,
        "health_url": "/health",
    }


# Include routers
from app.auth.routes import router as auth_router
from app.files.routes import router as files_router
from app.summaries.routes import router as summaries_router
from app.usage.routes import router as usage_router
from app.users.routes import router as users_router
from app.websocket.routes import router as websocket_router
from app.quizzes.routes import router as quizzes_router
from app.notifications.routes import router as notifications_router
from app.dashboards.routes import router as dashboards_router

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(users_router, prefix="/users", tags=["Users"])
app.include_router(files_router, prefix="/files", tags=["Files"])
app.include_router(summaries_router, prefix="/summaries", tags=["Summaries"])
app.include_router(quizzes_router, prefix="/quizzes", tags=["Quizzes"])
app.include_router(usage_router, tags=["Usage & Quotas"])
app.include_router(websocket_router, tags=["WebSocket"])
app.include_router(notifications_router, tags=["Notifications"])
app.include_router(dashboards_router, tags=["Dashboards"])


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled exceptions."""
    if settings.debug:
        # In debug mode, let FastAPI handle the exception normally
        raise exc
    
    # In production, return a generic error message
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_id": "INTERNAL_ERROR",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)