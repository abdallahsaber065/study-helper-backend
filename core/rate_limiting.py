"""
Rate limiting and security middleware for API protection.
"""
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from collections import defaultdict
from fastapi import HTTPException, status, Request
from fastapi.security import HTTPBearer
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """In-memory rate limiter with different policies."""
    
    def __init__(self):
        # Store: {key: {"count": int, "window_start": float, "blocked_until": float}}
        self.storage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "count": 0,
            "window_start": time.time(),
            "blocked_until": 0
        })
        
        # Rate limiting policies
        self.policies = {
            "default": {"requests": 100, "window": 60},  # 100 requests per minute
            "auth": {"requests": 10, "window": 60},       # 10 auth requests per minute
            "ai_generation": {"requests": 20, "window": 3600},  # 20 AI requests per hour
            "file_upload": {"requests": 50, "window": 3600},    # 50 uploads per hour
            "comment": {"requests": 30, "window": 60},          # 30 comments per minute
            "admin": {"requests": 1000, "window": 60},          # Higher limit for admins
        }
    
    def _get_client_key(self, request: Request, user_id: Optional[int] = None) -> str:
        """Generate a unique key for the client."""
        if user_id:
            return f"user_{user_id}"
        
        # Use X-Forwarded-For if behind proxy, otherwise use direct IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        return f"ip_{client_ip}"
    
    def is_allowed(
        self,
        request: Request,
        policy_name: str = "default",
        user_id: Optional[int] = None,
        user_role: Optional[str] = None
    ) -> tuple[bool, Dict[str, Any]]:
        """Check if request is allowed under rate limiting policy."""
        
        # Admin users get higher limits
        if user_role == "admin" and policy_name != "admin":
            policy_name = "admin"
        
        if policy_name not in self.policies:
            policy_name = "default"
        
        policy = self.policies[policy_name]
        client_key = self._get_client_key(request, user_id)
        rate_key = f"{policy_name}_{client_key}"
        
        current_time = time.time()
        client_data = self.storage[rate_key]
        
        # Check if client is currently blocked
        if client_data["blocked_until"] > current_time:
            return False, {
                "error": "Rate limit exceeded",
                "blocked_until": client_data["blocked_until"],
                "retry_after": int(client_data["blocked_until"] - current_time)
            }
        
        # Reset window if expired
        if current_time - client_data["window_start"] >= policy["window"]:
            client_data["count"] = 0
            client_data["window_start"] = current_time
            client_data["blocked_until"] = 0
        
        # Check if limit exceeded
        if client_data["count"] >= policy["requests"]:
            # Block for the remaining window time
            window_end = client_data["window_start"] + policy["window"]
            client_data["blocked_until"] = window_end
            
            return False, {
                "error": "Rate limit exceeded",
                "requests_per_window": policy["requests"],
                "window_seconds": policy["window"],
                "retry_after": int(window_end - current_time)
            }
        
        # Increment counter
        client_data["count"] += 1
        
        return True, {
            "requests_remaining": policy["requests"] - client_data["count"],
            "window_reset": client_data["window_start"] + policy["window"]
        }
    
    def get_rate_limit_info(
        self,
        request: Request,
        policy_name: str = "default",
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get current rate limit status for client."""
        if policy_name not in self.policies:
            policy_name = "default"
        
        policy = self.policies[policy_name]
        client_key = self._get_client_key(request, user_id)
        rate_key = f"{policy_name}_{client_key}"
        
        current_time = time.time()
        client_data = self.storage[rate_key]
        
        # Reset if window expired
        if current_time - client_data["window_start"] >= policy["window"]:
            client_data["count"] = 0
            client_data["window_start"] = current_time
        
        return {
            "policy": policy_name,
            "limit": policy["requests"],
            "window_seconds": policy["window"],
            "current_count": client_data["count"],
            "remaining": max(0, policy["requests"] - client_data["count"]),
            "window_reset": client_data["window_start"] + policy["window"],
            "blocked": client_data["blocked_until"] > current_time
        }
    
    def cleanup_expired(self):
        """Clean up expired entries to prevent memory bloat."""
        current_time = time.time()
        expired_keys = []
        
        for key, data in self.storage.items():
            # Remove entries that are old and not blocked
            if (current_time - data["window_start"] > 3600 and  # 1 hour old
                data["blocked_until"] <= current_time):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.storage[key]
        
        return len(expired_keys)


# Global rate limiter instance
rate_limiter = RateLimiter()


class SecurityValidator:
    """Additional security validation for requests."""
    
    @staticmethod
    def validate_content_size(content: str, max_size: int = 1000000) -> bool:
        """Validate content size to prevent DoS attacks."""
        return len(content.encode('utf-8')) <= max_size
    
    @staticmethod
    def validate_file_upload(file_size: int, file_type: str) -> tuple[bool, str]:
        """Validate file upload security."""
        # File size limits (in bytes)
        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
        
        if file_size > MAX_FILE_SIZE:
            return False, f"File size exceeds maximum limit of {MAX_FILE_SIZE // (1024*1024)}MB"
        
        # Allowed file types
        ALLOWED_TYPES = [
            'text/plain', 'text/markdown', 'text/csv',
            'application/pdf', 'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'image/jpeg', 'image/png', 'image/webp',
            'audio/wav', 'audio/mp3', 'audio/mpeg',
            'video/mp4', 'video/webm'
        ]
        
        if file_type not in ALLOWED_TYPES:
            return False, f"File type '{file_type}' is not allowed"
        
        return True, "Valid"
    
    @staticmethod
    def validate_user_input(text: str) -> tuple[bool, str]:
        """Validate user input for potential security issues."""
        if not text or not text.strip():
            return False, "Empty input not allowed"
        
        # Check for potential script injection patterns
        dangerous_patterns = [
            '<script', '</script>', 'javascript:', 'vbscript:',
            'onload=', 'onerror=', 'onclick=', 'eval(',
            'document.cookie', 'document.write'
        ]
        
        text_lower = text.lower()
        for pattern in dangerous_patterns:
            if pattern in text_lower:
                logger.warning(f"Potentially dangerous pattern detected: {pattern}")
                return False, f"Input contains potentially dangerous content"
        
        # Check length limits
        if len(text) > 50000:  # 50k characters
            return False, "Input text too long"
        
        return True, "Valid"
    
    @staticmethod
    def validate_sql_injection(text: str) -> tuple[bool, str]:
        """Check for potential SQL injection patterns."""
        sql_patterns = [
            'union select', 'drop table', 'delete from',
            'insert into', 'update set', '--', ';--',
            'xp_', 'sp_', 'exec(', 'execute('
        ]
        
        text_lower = text.lower().replace(' ', '').replace('\n', ' ')
        for pattern in sql_patterns:
            if pattern.replace(' ', '') in text_lower:
                logger.warning(f"Potential SQL injection detected: {pattern}")
                return False, "Input contains potentially malicious content"
        
        return True, "Valid"


# Security validator instance
security_validator = SecurityValidator()


def check_rate_limit(
    request: Request,
    policy: str = "default",
    user_id: Optional[int] = None,
    user_role: Optional[str] = None
):
    """FastAPI dependency for rate limiting."""
    allowed, info = rate_limiter.is_allowed(request, policy, user_id, user_role)
    
    if not allowed:
        retry_after = info.get("retry_after", 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=info.get("error", "Rate limit exceeded"),
            headers={"Retry-After": str(retry_after)}
        )
    
    return info


def validate_request_security(
    content: Optional[str] = None,
    file_size: Optional[int] = None,
    file_type: Optional[str] = None
):
    """FastAPI dependency for security validation."""
    if content:
        # Check content size
        if not security_validator.validate_content_size(content):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Content size exceeds maximum limit"
            )
        
        # Check user input
        valid, message = security_validator.validate_user_input(content)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )
        
        # Check SQL injection
        valid, message = security_validator.validate_sql_injection(content)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid input detected"
            )
    
    if file_size and file_type:
        valid, message = security_validator.validate_file_upload(file_size, file_type)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )
    
    return True 