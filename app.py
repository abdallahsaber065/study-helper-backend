from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# Import routers
from routers import auth, users, files, summaries

# Create FastAPI app instance
app = FastAPI(
    title="Study Helper Backend API",
    description="Backend API for the Study Helper application with AI-powered features",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

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


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify the API is running.
    """
    return {"status": "ok", "message": "Study Helper Backend API is running"}


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint providing basic API information.
    """
    return {
        "message": "Welcome to Study Helper Backend API",
        "version": "0.1.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }
