"""
Health check and system monitoring endpoints.
"""
import time
import psutil
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
import structlog

from db_config import get_db
from core.config import settings
from models.models import User, AiApiKey, AiProviderEnum
from services.ai_manager import AIManager

router = APIRouter(prefix="/health", tags=["Health"])
logger = structlog.get_logger("health")


class HealthChecker:
    """Service for performing various health checks."""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def check_database(self) -> Dict[str, Any]:
        """Check database connectivity and basic operations."""
        try:
            start_time = time.time()
            
            # Test basic connection
            result = self.db.execute(text("SELECT 1"))
            result.fetchone()
            
            # Test user count query
            user_count = self.db.query(User).count()
            
            response_time = (time.time() - start_time) * 1000
            
            return {
                "status": "healthy",
                "response_time_ms": round(response_time, 2),
                "user_count": user_count,
                "details": "Database connection successful"
            }
            
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
                "details": "Database connection failed"
            }
    
    async def check_ai_services(self) -> Dict[str, Any]:
        """Check AI service availability."""
        results = {}
        
        # Check Gemini
        try:
            if settings.gemini_api_key:
                ai_manager = AIManager(self.db)
                # Simple test - just check if we can initialize the client
                await ai_manager.initialize_gemini_client(user_id=1)  # Use admin user ID
                results["gemini"] = {
                    "status": "healthy",
                    "details": "API key configured and client initialized"
                }
            else:
                results["gemini"] = {
                    "status": "not_configured",
                    "details": "API key not configured"
                }
        except Exception as e:
            results["gemini"] = {
                "status": "unhealthy",
                "error": str(e),
                "details": "Failed to initialize Gemini client"
            }
        
        # Check OpenAI
        try:
            if settings.openai_api_key:
                ai_manager = AIManager(self.db)
                await ai_manager.initialize_openai_client(user_id=1)  # Use admin user ID
                results["openai"] = {
                    "status": "healthy",
                    "details": "API key configured and client initialized"
                }
            else:
                results["openai"] = {
                    "status": "not_configured",
                    "details": "API key not configured"
                }
        except Exception as e:
            results["openai"] = {
                "status": "unhealthy",
                "error": str(e),
                "details": "Failed to initialize OpenAI client"
            }
        
        return results
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage."""
        try:
            # Get CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Get memory usage
            memory = psutil.virtual_memory()
            
            # Get disk usage
            disk = psutil.disk_usage('/')
            
            return {
                "status": "healthy",
                "cpu_percent": cpu_percent,
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "percent_used": memory.percent
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "percent_used": round((disk.used / disk.total) * 100, 2)
                }
            }
            
        except Exception as e:
            logger.error("System resource check failed", error=str(e))
            return {
                "status": "error",
                "error": str(e)
            }


@router.get("/", summary="Basic health check")
async def health_check():
    """
    Basic health check endpoint to verify the API is running.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "Study Helper Backend API",
        "version": settings.app_version
    }


@router.get("/detailed", summary="Detailed health check")
async def detailed_health_check(db: Session = Depends(get_db)):
    """
    Comprehensive health check including database, AI services, and system resources.
    """
    checker = HealthChecker(db)
    
    # Run all health checks
    checks = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": settings.app_name,
        "version": settings.app_version,
        "database": await checker.check_database(),
        "ai_services": await checker.check_ai_services(),
        "system": checker.check_system_resources()
    }
    
    # Determine overall status
    overall_status = "healthy"
    
    # Check database
    if checks["database"]["status"] != "healthy":
        overall_status = "unhealthy"
    
    # Check AI services (at least one should be healthy or not_configured)
    ai_services = checks["ai_services"]
    if all(service.get("status") == "unhealthy" for service in ai_services.values()):
        overall_status = "degraded"
    
    # Check system resources
    system = checks["system"]
    if system["status"] == "healthy":
        if (system.get("cpu_percent", 0) > 90 or 
            system.get("memory", {}).get("percent_used", 0) > 90 or
            system.get("disk", {}).get("percent_used", 0) > 90):
            overall_status = "degraded"
    
    checks["overall_status"] = overall_status
    
    # Log health check results
    logger.info("Health check performed", status=overall_status, checks=checks)
    
    # Return appropriate HTTP status
    if overall_status == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=checks
        )
    
    return checks


@router.get("/database", summary="Database health check")
async def database_health_check(db: Session = Depends(get_db)):
    """
    Check database connectivity and performance.
    """
    checker = HealthChecker(db)
    result = await checker.check_database()
    
    if result["status"] != "healthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result
        )
    
    return result


@router.get("/ai-services", summary="AI services health check")
async def ai_services_health_check(db: Session = Depends(get_db)):
    """
    Check AI service availability and configuration.
    """
    checker = HealthChecker(db)
    result = await checker.check_ai_services()
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ai_services": result
    }


@router.get("/system", summary="System resources check")
async def system_health_check():
    """
    Check system resource usage (CPU, memory, disk).
    """
    checker = HealthChecker(None)  # No DB needed for system checks
    result = checker.check_system_resources()
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": result
    }


@router.get("/readiness", summary="Readiness probe")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Kubernetes-style readiness probe.
    Returns 200 if the service is ready to handle requests.
    """
    checker = HealthChecker(db)
    
    # Check essential services
    db_check = await checker.check_database()
    
    if db_check["status"] != "healthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )
    
    return {"status": "ready"}


@router.get("/liveness", summary="Liveness probe")
async def liveness_check():
    """
    Kubernetes-style liveness probe.
    Returns 200 if the service is alive.
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat()
    } 