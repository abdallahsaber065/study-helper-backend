"""
Structured logging configuration for the application.
"""

import sys
import logging
import logging.handlers
import structlog
import os
import gzip
import shutil
from pathlib import Path
from typing import Any, Dict
from datetime import datetime
from pythonjsonlogger import jsonlogger
from core.config import settings


def add_timestamp(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Add timestamp to log entries."""
    event_dict["timestamp"] = datetime.utcnow().isoformat()
    return event_dict


def add_log_level(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Add log level to log entries."""
    event_dict["level"] = method_name.upper()
    return event_dict


def add_logger_name(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Add logger name to log entries."""
    logger_name = getattr(logger, "name", "unknown")
    event_dict["logger"] = logger_name
    return event_dict


class SecurityFilter(logging.Filter):
    """Filter to remove sensitive information from logs."""

    SENSITIVE_KEYS = {
        "password",
        "token",
        "secret",
        "key",
        "api_key",
        "authorization",
        "auth",
        "credential",
        "pass",
    }

    def filter(self, record):
        """Filter sensitive information from log records."""
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self._sanitize_message(record.msg)

        if hasattr(record, "args") and record.args:
            record.args = tuple(self._sanitize_value(arg) for arg in record.args)

        return True

    def _sanitize_message(self, message: str) -> str:
        """Sanitize message content."""
        # Basic sanitization for common patterns
        import re

        # Hide potential API keys (long alphanumeric strings)
        message = re.sub(r"\b[A-Za-z0-9]{32,}\b", "[REDACTED]", message)

        # Hide potential JWT tokens
        message = re.sub(
            r"Bearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+",
            "Bearer [REDACTED]",
            message,
        )

        return message

    def _sanitize_value(self, value: Any) -> Any:
        """Sanitize a single value."""
        if isinstance(value, str):
            return self._sanitize_message(value)
        elif isinstance(value, dict):
            return {
                k: (
                    "[REDACTED]"
                    if any(sensitive in k.lower() for sensitive in self.SENSITIVE_KEYS)
                    else v
                )
                for k, v in value.items()
            }
        return value


def setup_logging():
    """Configure structured logging for the application."""

    # Ensure log directory exists if file logging is enabled
    if settings.enable_file_logging:
        ensure_log_directory()

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            add_timestamp,
            add_log_level,
            (
                structlog.processors.JSONRenderer()
                if settings.log_format == "json" and not settings.debug
                else structlog.dev.ConsoleRenderer(colors=True)
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    if settings.debug:
        log_level = logging.DEBUG

    # Configure console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if settings.debug:
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    else:
        if settings.log_format == "json":
            console_formatter = jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        else:
            console_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(SecurityFilter())
    console_handler.setLevel(log_level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    # Add file handlers if enabled
    if settings.enable_file_logging:
        # Main application log
        app_file_handler = create_file_handler(settings.app_log_file, log_level)
        root_logger.addHandler(app_file_handler)

        # Error log (only errors and critical)
        error_file_handler = create_file_handler(settings.error_log_file, logging.ERROR)
        root_logger.addHandler(error_file_handler)

    # Configure specific loggers with their own file handlers
    loggers_config = {
        "uvicorn": {
            "level": logging.INFO,
            "file": settings.access_log_file if settings.enable_file_logging else None,
        },
        "uvicorn.access": {
            "level": logging.INFO,
            "file": settings.access_log_file if settings.enable_file_logging else None,
        },
        "fastapi": {
            "level": logging.INFO,
            "file": settings.app_log_file if settings.enable_file_logging else None,
        },
        "sqlalchemy.engine": {
            "level": (
                logging.WARNING if not settings.enable_sql_logging else logging.INFO
            ),
            "file": (
                settings.database_log_file if settings.enable_file_logging else None
            ),
        },
        "alembic": {
            "level": logging.INFO,
            "file": (
                settings.database_log_file if settings.enable_file_logging else None
            ),
        },
        "httpx": {
            "level": logging.WARNING,
            "file": settings.app_log_file if settings.enable_file_logging else None,
        },
        "app": {
            "level": logging.DEBUG if settings.debug else logging.INFO,
            "file": settings.app_log_file if settings.enable_file_logging else None,
        },
        "startup": {
            "level": logging.INFO,
            "file": settings.app_log_file if settings.enable_file_logging else None,
        },
        "database": {
            "level": logging.INFO,
            "file": (
                settings.database_log_file if settings.enable_file_logging else None
            ),
        },
        "security": {
            "level": logging.INFO,
            "file": (
                settings.security_log_file if settings.enable_file_logging else None
            ),
        },
        "ai_manager": {
            "level": logging.INFO,
            "file": settings.ai_log_file if settings.enable_file_logging else None,
        },
        "background_tasks": {
            "level": logging.INFO,
            "file": settings.app_log_file if settings.enable_file_logging else None,
        },
    }

    for logger_name, config in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(config["level"])
        logger.propagate = True

        # Add specific file handler if configured and file logging is enabled
        if config["file"] and settings.enable_file_logging:
            # Check if this file handler already exists to avoid duplicates
            file_handler_exists = any(
                isinstance(
                    handler,
                    (
                        logging.handlers.RotatingFileHandler,
                        logging.handlers.TimedRotatingFileHandler,
                        CompressedRotatingFileHandler,
                    ),
                )
                and hasattr(handler, "baseFilename")
                and config["file"] in handler.baseFilename
                for handler in logger.handlers
            )

            if not file_handler_exists:
                file_handler = create_file_handler(config["file"], config["level"])
                logger.addHandler(file_handler)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Application-specific logger instances
app_logger = get_logger("app")
security_logger = get_logger("security")
ai_logger = get_logger("ai_manager")
db_logger = get_logger("database")
task_logger = get_logger("background_tasks")


def ensure_log_directory():
    """Ensure the log directory exists."""
    log_dir = Path(settings.log_directory)
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


class CompressedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Custom rotating file handler that compresses old log files."""

    def __init__(self, *args, **kwargs):
        self.compress_logs = kwargs.pop("compress_logs", settings.log_compression)
        super().__init__(*args, **kwargs)

    def doRollover(self):
        """Override to add compression of rotated files."""
        super().doRollover()

        if self.compress_logs and self.backupCount > 0:
            # Compress the most recent backup file
            backup_file = f"{self.baseFilename}.1"
            if os.path.exists(backup_file):
                compressed_file = f"{backup_file}.gz"
                with open(backup_file, "rb") as f_in:
                    with gzip.open(compressed_file, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(backup_file)

                # Rename existing compressed files
                for i in range(2, self.backupCount + 1):
                    old_compressed = f"{self.baseFilename}.{i}.gz"
                    new_compressed = f"{self.baseFilename}.{i+1}.gz"
                    if os.path.exists(old_compressed):
                        if os.path.exists(new_compressed):
                            os.remove(new_compressed)
                        os.rename(old_compressed, new_compressed)


def create_file_handler(
    log_file: str,
    level: int = logging.INFO,
    max_bytes: int = None,
    backup_count: int = None,
) -> logging.Handler:
    """Create a rotating file handler with proper configuration."""
    log_dir = ensure_log_directory()
    file_path = log_dir / log_file

    max_bytes = max_bytes or (settings.log_file_max_size_mb * 1024 * 1024)
    backup_count = backup_count or settings.log_file_backup_count

    if settings.log_compression:
        handler = CompressedRotatingFileHandler(
            filename=str(file_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            compress_logs=True,
        )
    else:
        handler = logging.handlers.RotatingFileHandler(
            filename=str(file_path), maxBytes=max_bytes, backupCount=backup_count
        )

    handler.setLevel(level)

    # Set formatter based on settings
    if settings.log_format == "json":
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    handler.addFilter(SecurityFilter())

    return handler


def create_timed_rotating_handler(
    log_file: str, level: int = logging.INFO
) -> logging.Handler:
    """Create a time-based rotating file handler."""
    log_dir = ensure_log_directory()
    file_path = log_dir / log_file

    handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(file_path),
        when=settings.log_rotation_when,
        interval=settings.log_rotation_interval,
        backupCount=settings.log_file_backup_count,
    )

    handler.setLevel(level)

    # Set formatter based on settings
    if settings.log_format == "json":
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    handler.addFilter(SecurityFilter())

    return handler
