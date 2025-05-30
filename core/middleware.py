"""
Security middleware for enhanced application security.
"""
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
import structlog
import logging

# Use both structured and standard logging for compatibility
logger = structlog.get_logger("middleware")
std_logger = logging.getLogger("middleware")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Content Security Policy (adjust based on your needs)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        
        # HSTS (only add in production with HTTPS)
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all incoming requests and responses."""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Log request
        start_time = time.time()
        
        # Get client info
        client_host = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_host = forwarded_for.split(",")[0].strip()
        
        logger.info(
            "Request started",
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
            query_params=str(request.query_params),
            client_host=client_host,
            user_agent=request.headers.get("User-Agent", "unknown")
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log response
            logger.info(
                "Request completed",
                request_id=request_id,
                status_code=response.status_code,
                process_time_ms=round(process_time * 1000, 2)
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(round(process_time * 1000, 2))
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                "Request failed",
                request_id=request_id,
                exception=str(e),
                process_time_ms=round(process_time * 1000, 2)
            )
            raise


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size."""
    
    def __init__(self, app, max_size: int = 50 * 1024 * 1024):  # 50MB default
        super().__init__(app)
        self.max_size = max_size
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check Content-Length header
        content_length = request.headers.get("Content-Length")
        if content_length:
            content_length = int(content_length)
            if content_length > self.max_size:
                logger.warning(
                    "Request body too large",
                    content_length=content_length,
                    max_size=self.max_size,
                    client_host=request.client.host if request.client else "unknown"
                )
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Request body too large. Maximum size: {self.max_size} bytes"
                )
        
        return await call_next(request)


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """Middleware to restrict access based on IP whitelist (optional)."""
    
    def __init__(self, app, whitelist: list = None, enabled: bool = False):
        super().__init__(app)
        self.whitelist = whitelist or []
        self.enabled = enabled
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled or not self.whitelist:
            return await call_next(request)
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        
        # Check whitelist
        if client_ip not in self.whitelist:
            logger.warning(
                "IP not in whitelist",
                client_ip=client_ip,
                path=str(request.url.path)
            )
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return await call_next(request)


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request timeout."""
    
    def __init__(self, app, timeout_seconds: int = 300):  # 5 minutes default
        super().__init__(app)
        self.timeout_seconds = timeout_seconds
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        import asyncio
        
        try:
            # Execute with timeout
            response = await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds
            )
            return response
            
        except asyncio.TimeoutError:
            logger.error(
                "Request timeout",
                timeout_seconds=self.timeout_seconds,
                path=str(request.url.path),
                method=request.method
            )
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"Request timeout after {self.timeout_seconds} seconds"
            )


def setup_middleware(app, config: dict = None):
    """Setup all security middleware for the application."""
    config = config or {}
    
    # Add middleware in reverse order (last added is executed first)
    
    # Request timeout
    if config.get("enable_timeout", True):
        timeout = config.get("timeout_seconds", 300)
        app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=timeout)
    
    # Request size limiting
    if config.get("enable_size_limit", True):
        max_size = config.get("max_request_size", 50 * 1024 * 1024)
        app.add_middleware(RequestSizeMiddleware, max_size=max_size)
    
    # IP whitelist (usually disabled, enable for high-security environments)
    if config.get("enable_ip_whitelist", False):
        whitelist = config.get("ip_whitelist", [])
        app.add_middleware(IPWhitelistMiddleware, whitelist=whitelist, enabled=True)
    
    # Request logging
    if config.get("enable_request_logging", True):
        app.add_middleware(RequestLoggingMiddleware)
    
    # Security headers (should be first to add headers to all responses)
    if config.get("enable_security_headers", True):
        app.add_middleware(SecurityHeadersMiddleware) 