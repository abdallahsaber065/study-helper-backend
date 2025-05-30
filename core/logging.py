"""
Structured logging configuration for the application.
"""
import sys
import logging
import structlog
from typing import Any, Dict
from datetime import datetime
from pythonjsonlogger import jsonlogger
from core.config import settings


def add_timestamp(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add timestamp to log entries."""
    event_dict["timestamp"] = datetime.utcnow().isoformat()
    return event_dict


def add_log_level(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add log level to log entries."""
    event_dict["level"] = method_name.upper()
    return event_dict


def add_logger_name(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add logger name to log entries."""
    logger_name = getattr(logger, 'name', 'unknown')
    event_dict["logger"] = logger_name
    return event_dict


class SecurityFilter(logging.Filter):
    """Filter to remove sensitive information from logs."""
    
    SENSITIVE_KEYS = {
        'password', 'token', 'secret', 'key', 'api_key', 
        'authorization', 'auth', 'credential', 'pass'
    }
    
    def filter(self, record):
        """Filter sensitive information from log records."""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self._sanitize_message(record.msg)
        
        if hasattr(record, 'args') and record.args:
            record.args = tuple(self._sanitize_value(arg) for arg in record.args)
        
        return True
    
    def _sanitize_message(self, message: str) -> str:
        """Sanitize message content."""
        # Basic sanitization for common patterns
        import re
        
        # Hide potential API keys (long alphanumeric strings)
        message = re.sub(r'\b[A-Za-z0-9]{32,}\b', '[REDACTED]', message)
        
        # Hide potential JWT tokens
        message = re.sub(r'Bearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+', 'Bearer [REDACTED]', message)
        
        return message
    
    def _sanitize_value(self, value: Any) -> Any:
        """Sanitize a single value."""
        if isinstance(value, str):
            return self._sanitize_message(value)
        elif isinstance(value, dict):
            return {
                k: '[REDACTED]' if any(sensitive in k.lower() for sensitive in self.SENSITIVE_KEYS) else v
                for k, v in value.items()
            }
        return value


def setup_logging():
    """Configure structured logging for the application."""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            add_timestamp,
            add_log_level,
            structlog.processors.JSONRenderer() if not settings.debug else structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    if settings.debug:
        log_level = logging.DEBUG
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(log_format)
    else:
        log_level = logging.INFO
        handler = logging.StreamHandler(sys.stdout)
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S"
        )
    
    handler.setFormatter(formatter)
    handler.addFilter(SecurityFilter())
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    
    # Configure specific loggers
    loggers_config = {
        "uvicorn": logging.INFO,
        "uvicorn.access": logging.INFO,
        "fastapi": logging.INFO,
        "sqlalchemy.engine": logging.WARNING,
        "alembic": logging.INFO,
        "httpx": logging.WARNING,
        "app": logging.DEBUG if settings.debug else logging.INFO,
        "startup": logging.INFO,
        "database": logging.INFO,
        "security": logging.INFO,
        "ai_manager": logging.INFO,
        "background_tasks": logging.INFO,
    }
    
    for logger_name, level in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = True


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Application-specific logger instances
app_logger = get_logger("app")
security_logger = get_logger("security")
ai_logger = get_logger("ai_manager")
db_logger = get_logger("database")
task_logger = get_logger("background_tasks") 