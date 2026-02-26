"""
Main FastAPI application entry point for the study-assistant backend.

This module wires together all feature routers from the ``app/`` package
into a single FastAPI application instance.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.auth.routes import router as auth_router
from app.users.routes import router as users_router
from app.files.routes import router as files_router
from app.summaries.routes import router as summaries_router
from app.quizzes.routes import router as quizzes_router
from app.notifications.routes import router as notifications_router
from app.usage.routes import router as usage_router
from app.dashboards.routes import router as dashboards_router
from app.websocket.routes import router as websocket_router

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Application lifespan handler for startup and shutdown events."""
    yield


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="AI-powered Quiz & Summary Generation Platform",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # Register feature routers
    application.include_router(auth_router, prefix="/auth", tags=["Authentication"])
    application.include_router(users_router, prefix="/users", tags=["Users"])
    application.include_router(files_router, prefix="/files", tags=["Files"])
    application.include_router(summaries_router, prefix="/summaries", tags=["Summaries"])
    application.include_router(quizzes_router, prefix="/quizzes", tags=["Quizzes"])
    application.include_router(
        notifications_router, prefix="/notifications", tags=["Notifications"]
    )
    application.include_router(usage_router, prefix="/usage", tags=["Usage"])
    application.include_router(
        dashboards_router, prefix="/dashboards", tags=["Dashboards"]
    )
    application.include_router(websocket_router, prefix="/ws", tags=["WebSocket"])

    @application.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """Basic health check."""
        return {"status": "ok", "version": settings.version}

    return application


# Application instance used by tests and ASGI servers
app = create_app()
