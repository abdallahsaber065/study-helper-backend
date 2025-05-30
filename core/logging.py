"""
Centralized logging system with rotating file handlers, compression, and singleton pattern.
"""
import sys
import os
import logging
import logging.handlers
import gzip
import shutil
import threading
from pathlib import Path
from typing import Dict, Optional, Any, Union
from datetime import datetime
from pythonjsonlogger import jsonlogger
from core.config import settings


class ComponentFilter(logging.Filter):
    """Filter to ensure all log records have a component field."""
    
    def __init__(self, default_component: str = "unknown"):
        super().__init__()
        self.default_component = default_component
    
    def filter(self, record):
        """Add component field if missing."""
        if not hasattr(record, 'component'):
            # Try to infer component from logger name
            logger_name = record.name
            if logger_name in ['httpx', 'uvicorn', 'uvicorn.access']:
                record.component = 'http'
            elif logger_name.startswith('sqlalchemy'):
                record.component = 'database'
            elif logger_name.startswith('alembic'):
                record.component = 'database'
            else:
                record.component = self.default_component
        return True


class SecurityFilter(logging.Filter):
    """Filter to remove sensitive information from logs."""
    
    SENSITIVE_KEYS = {
        'password', 'token', 'secret', 'key', 'api_key', 
        'authorization', 'auth', 'credential', 'pass',
        'jwt', 'bearer', 'session'
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
        import re
        
        # Hide potential API keys (long alphanumeric strings)
        message = re.sub(r'\b[A-Za-z0-9]{32,}\b', '[REDACTED]', message)
        
        # Hide potential JWT tokens
        message = re.sub(
            r'Bearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+',
            'Bearer [REDACTED]',
            message
        )
        
        # Hide passwords in URLs
        message = re.sub(r'://[^:]+:[^@]+@', '://[REDACTED]:[REDACTED]@', message)
        
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


class CompressedTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Custom timed rotating file handler that compresses old log files."""
    
    def __init__(self, *args, **kwargs):
        self.compress_logs = kwargs.pop('compress_logs', settings.log_compression)
        super().__init__(*args, **kwargs)
    
    def doRollover(self):
        """Override to add compression of rotated files."""
        super().doRollover()
        
        if self.compress_logs:
            # Find the most recent backup file
            backup_file = None
            for i in range(1, self.backupCount + 1):
                potential_backup = f"{self.baseFilename}.{self.suffix}.{i}"
                if os.path.exists(potential_backup):
                    backup_file = potential_backup
                    break
            
            if backup_file and os.path.exists(backup_file):
                compressed_file = f"{backup_file}.gz"
                try:
                    with open(backup_file, 'rb') as f_in:
                        with gzip.open(compressed_file, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(backup_file)
                except Exception as e:
                    # If compression fails, keep the original file
                    print(f"Warning: Failed to compress log file {backup_file}: {e}")


class CompressedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Custom rotating file handler that compresses old log files."""
    
    def __init__(self, *args, **kwargs):
        self.compress_logs = kwargs.pop('compress_logs', settings.log_compression)
        super().__init__(*args, **kwargs)
    
    def doRollover(self):
        """Override to add compression of rotated files."""
        super().doRollover()
        
        if self.compress_logs and self.backupCount > 0:
            # Compress the most recent backup file
            backup_file = f"{self.baseFilename}.1"
            if os.path.exists(backup_file):
                compressed_file = f"{backup_file}.gz"
                try:
                    with open(backup_file, 'rb') as f_in:
                        with gzip.open(compressed_file, 'wb') as f_out:
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
                except Exception as e:
                    # If compression fails, keep the original file
                    print(f"Warning: Failed to compress log file {backup_file}: {e}")


class StructuredLogger:
    """A logger wrapper that provides structured logging capabilities."""
    
    def __init__(self, name: str, logger: logging.Logger):
        self.name = name
        self._logger = logger
        self._name = name  # For compatibility with existing code
    
    def _format_message(self, msg: str, **kwargs) -> str:
        """Format message with structured data."""
        if not kwargs:
            return msg
        
        if settings.log_format == "json":
            # For JSON format, structured data will be handled by the formatter
            return msg
        else:
            # For text format, append structured data to message
            structured_parts = []
            for key, value in kwargs.items():
                structured_parts.append(f"{key}={value}")
            
            if structured_parts:
                return f"{msg} [{', '.join(structured_parts)}]"
            return msg
    
    def _log(self, level: int, msg: str, *args, **kwargs):
        """Internal logging method."""
        # Extract logging-specific kwargs
        exc_info = kwargs.pop('exc_info', False)
        extra = kwargs.pop('extra', {})
        
        # Add component info to extra
        extra['component'] = self.name
        
        # Format message with remaining kwargs as structured data
        formatted_msg = self._format_message(msg, **kwargs)
        
        self._logger.log(level, formatted_msg, *args, exc_info=exc_info, extra=extra)
    
    def debug(self, msg: str, *args, **kwargs):
        """Log debug message."""
        self._log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """Log info message."""
        self._log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Log warning message."""
        self._log(logging.WARNING, msg, *args, **kwargs)
    
    def warn(self, msg: str, *args, **kwargs):
        """Log warning message (alias)."""
        self.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """Log error message."""
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Log exception message."""
        kwargs['exc_info'] = True
        self.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        """Log critical message."""
        self._log(logging.CRITICAL, msg, *args, **kwargs)


class CentralizedLogManager:
    """Singleton centralized log manager with rotating handlers and compression."""
    
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._loggers: Dict[str, StructuredLogger] = {}
        self._handlers: Dict[str, logging.Handler] = {}
        self._log_directory = None
        self._setup_complete = False
        
        with self._lock:
            if not self._initialized:
                self._ensure_log_directory()
                self._setup_root_logger()
                self._setup_component_loggers()
                self._initialized = True
                self._setup_complete = True
    
    def _ensure_log_directory(self):
        """Ensure the log directory exists."""
        self._log_directory = Path(settings.log_directory)
        self._log_directory.mkdir(parents=True, exist_ok=True)
    
    def _create_formatter(self, include_component: bool = True, require_component: bool = False) -> logging.Formatter:
        """Create a formatter based on settings."""
        if settings.log_format == "json":
            if include_component:
                fmt = "%(asctime)s %(name)s %(levelname)s %(component)s %(message)s"
            else:
                fmt = "%(asctime)s %(name)s %(levelname)s %(message)s"
            return jsonlogger.JsonFormatter(
                fmt=fmt,
                datefmt="%Y-%m-%dT%H:%M:%S"
            )
        else:
            if include_component and require_component:
                fmt = "%(asctime)s - %(name)s - %(levelname)s - [%(component)s] - %(message)s"
            elif include_component:
                # Use a safer format that doesn't require component
                fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            else:
                fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            return logging.Formatter(
                fmt=fmt,
                datefmt="%Y-%m-%d %H:%M:%S"
            )
    
    def _create_rotating_handler(self, log_file: str, level: int = logging.INFO, use_component_filter: bool = True) -> logging.Handler:
        """Create a rotating file handler with proper configuration."""
        file_path = self._log_directory / log_file
        max_bytes = settings.log_file_max_size_mb * 1024 * 1024
        backup_count = settings.log_file_backup_count
        
        # Choose rotation strategy based on settings
        if settings.log_rotation_when != "size":
            # Time-based rotation
            handler = CompressedTimedRotatingFileHandler(
                filename=str(file_path),
                when=settings.log_rotation_when,
                interval=settings.log_rotation_interval,
                backupCount=backup_count,
                compress_logs=settings.log_compression
            )
        else:
            # Size-based rotation
            handler = CompressedRotatingFileHandler(
                filename=str(file_path),
                maxBytes=max_bytes,
                backupCount=backup_count,
                compress_logs=settings.log_compression
            )
        
        handler.setLevel(level)
        
        # Add component filter for file handlers
        if use_component_filter:
            handler.addFilter(ComponentFilter())
            handler.setFormatter(self._create_formatter(include_component=True, require_component=True))
        else:
            handler.setFormatter(self._create_formatter(include_component=False))
        
        handler.addFilter(SecurityFilter())
        
        return handler
    
    def _create_console_handler(self) -> logging.Handler:
        """Create console handler."""
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
        
        # Console handler gets component filter and simpler format
        handler.addFilter(ComponentFilter())
        handler.setFormatter(self._create_formatter(include_component=False))
        handler.addFilter(SecurityFilter())
        return handler
    
    def _setup_root_logger(self):
        """Setup the root logger."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
        
        # Add console handler
        console_handler = self._create_console_handler()
        root_logger.addHandler(console_handler)
        self._handlers['console'] = console_handler
        
        # Add main app log file handler if file logging is enabled
        if settings.enable_file_logging:
            app_handler = self._create_rotating_handler(settings.app_log_file)
            root_logger.addHandler(app_handler)
            self._handlers['app'] = app_handler
            
            # Add error log handler (only for ERROR and CRITICAL)
            error_handler = self._create_rotating_handler(settings.error_log_file, logging.ERROR)
            root_logger.addHandler(error_handler)
            self._handlers['error'] = error_handler
    
    def _setup_component_loggers(self):
        """Setup loggers for different components."""
        if not settings.enable_file_logging:
            return
        
        # Component logger configurations
        component_configs = {
            'security': {
                'file': settings.security_log_file,
                'level': logging.INFO,
                'loggers': ['security', 'auth']
            },
            'ai': {
                'file': settings.ai_log_file,
                'level': logging.INFO,
                'loggers': ['ai_manager', 'ai', 'gemini', 'openai']
            },
            'database': {
                'file': settings.database_log_file,
                'level': logging.INFO if settings.enable_sql_logging else logging.WARNING,
                'loggers': ['database', 'sqlalchemy.engine', 'alembic']
            },
            'access': {
                'file': settings.access_log_file,
                'level': logging.INFO,
                'loggers': ['uvicorn', 'uvicorn.access', 'access', 'httpx']
            }
        }
        
        for component, config in component_configs.items():
            # Create handler for this component
            handler = self._create_rotating_handler(config['file'], config['level'])
            self._handlers[component] = handler
            
            # Configure loggers for this component
            for logger_name in config['loggers']:
                logger = logging.getLogger(logger_name)
                
                # Don't clear handlers for root logger components to avoid affecting other loggers
                if logger_name not in ['uvicorn', 'uvicorn.access', 'httpx']:
                    logger.handlers.clear()
                
                logger.addHandler(handler)
                logger.setLevel(config['level'])
                
                # Prevent propagation to root logger for component-specific loggers to avoid duplicates
                if logger_name in ['security', 'auth', 'ai_manager', 'ai', 'gemini', 'openai']:
                    logger.propagate = False
    
    def get_logger(self, name: str) -> StructuredLogger:
        """Get a structured logger instance for a component."""
        if name in self._loggers:
            return self._loggers[name]
        
        # Create a new structured logger
        standard_logger = logging.getLogger(name)
        structured_logger = StructuredLogger(name, standard_logger)
        self._loggers[name] = structured_logger
        
        return structured_logger
    
    def get_standard_logger(self, name: str) -> logging.Logger:
        """Get a standard Python logger instance."""
        return logging.getLogger(name)
    
    def shutdown(self):
        """Shutdown all handlers gracefully."""
        try:
            # Close all custom handlers first
            for handler_name, handler in self._handlers.items():
                try:
                    if hasattr(handler, 'close'):
                        handler.close()
                except Exception as e:
                    print(f"Error closing handler {handler_name}: {e}")
            
            # Clear handlers dict
            self._handlers.clear()
            
            # Close all logger handlers
            for logger_name, structured_logger in self._loggers.items():
                try:
                    logger = structured_logger._logger
                    for handler in logger.handlers[:]:  # Copy list to avoid modification during iteration
                        try:
                            handler.close()
                            logger.removeHandler(handler)
                        except Exception as e:
                            print(f"Error closing handler for logger {logger_name}: {e}")
                except Exception as e:
                    print(f"Error processing logger {logger_name}: {e}")
            
            # Clear structured loggers
            self._loggers.clear()
            
            # Close root logger handlers
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:  # Copy list to avoid modification during iteration
                try:
                    handler.close()
                    root_logger.removeHandler(handler)
                except Exception as e:
                    print(f"Error closing root handler: {e}")
            
            # Call logging shutdown to ensure all handlers are properly closed
            logging.shutdown()
            
        except Exception as e:
            print(f"Error during logging shutdown: {e}")
        
        # Reset initialization flag
        self._initialized = False


# Global singleton instance
_log_manager = None


def setup_logging():
    """Setup centralized logging system."""
    global _log_manager
    if _log_manager is None:
        _log_manager = CentralizedLogManager()
    return _log_manager


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    global _log_manager
    if _log_manager is None:
        _log_manager = CentralizedLogManager()
    return _log_manager.get_logger(name)


def get_standard_logger(name: str) -> logging.Logger:
    """Get a standard Python logger instance."""
    global _log_manager
    if _log_manager is None:
        _log_manager = CentralizedLogManager()
    return _log_manager.get_standard_logger(name)


def shutdown_logging():
    """Shutdown logging system gracefully."""
    global _log_manager
    if _log_manager is not None:
        _log_manager.shutdown()
        _log_manager = None


def force_close_all_handlers():
    """Force close all logging handlers to release file locks."""
    try:
        # Get all existing loggers
        loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
        loggers.append(logging.getLogger())  # Add root logger
        
        # Close all handlers for all loggers
        for logger in loggers:
            for handler in logger.handlers[:]:
                try:
                    handler.close()
                    logger.removeHandler(handler)
                except Exception as e:
                    print(f"Error force closing handler: {e}")
        
        # Call logging shutdown
        logging.shutdown()
        
        print("✅ All logging handlers force closed")
        
    except Exception as e:
        print(f"❌ Error during force close: {e}")


# Pre-configured logger instances for common components
app_logger = get_logger("app")
security_logger = get_logger("security")
ai_logger = get_logger("ai_manager")
database_logger = get_logger("database")
access_logger = get_logger("access")


def _cleanup_logging():
    """Cleanup function to be called at exit."""
    try:
        shutdown_logging()
    except Exception as e:
        print(f"Error during logging cleanup: {e}")


import atexit
atexit.register(_cleanup_logging) 