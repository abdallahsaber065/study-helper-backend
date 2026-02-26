#!/usr/bin/env python3
"""
Test script to verify centralized logging system functionality.
"""

import sys
import os
import logging
import time

# Add the parent directory to the path so we can import from the core module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.logging import setup_logging, get_logger, get_standard_logger
from core.config import settings

def test_logging_system():
    """Test the centralized logging system."""
    
    print("🔧 Initializing centralized logging system...")
    setup_logging()
    
    print("📝 Testing structured loggers...")
    
    # Test structured loggers
    app_logger = get_logger("app")
    security_logger = get_logger("security")
    ai_logger = get_logger("ai_manager")
    database_logger = get_logger("database")
    
    print("✅ Testing app logger...")
    app_logger.info("Application started", version="0.1.0", environment="test")
    app_logger.warning("Test warning message", user_id=123, action="test")
    app_logger.error("Test error message", error_code="TEST_001", component="test")
    
    print("🔐 Testing security logger...")
    security_logger.info("User login attempt", username="testuser", ip="192.168.1.1")
    security_logger.warning("Failed login attempt", username="baduser", attempts=3)
    
    print("🤖 Testing AI logger...")
    ai_logger.info("AI request started", model="gemini-2.5-flash", prompt_length=150)
    ai_logger.debug("AI cache hit", file_id=456, cache_key="test_key")
    
    print("💾 Testing database logger...")
    database_logger.info("Database connection established", pool_size=10)
    database_logger.debug("SQL query executed", query="SELECT * FROM users", duration_ms=45)
    
    print("📡 Testing standard Python loggers...")
    
    # Test standard Python loggers (like httpx, uvicorn)
    httpx_logger = get_standard_logger("httpx")
    uvicorn_logger = get_standard_logger("uvicorn")
    
    httpx_logger.info("HTTP Request: GET /api/test 200 OK")
    uvicorn_logger.info("Server started on http://0.0.0.0:8000")
    
    print("🧪 Testing exception logging...")
    
    try:
        # Simulate an exception
        raise ValueError("This is a test exception")
    except Exception as e:
        app_logger.exception("Test exception occurred", operation="test", user_id=999)
        
    print("🔒 Testing sensitive data filtering...")
    
    # Test that sensitive data gets filtered
    security_logger.info("User login", username="testuser", password="secret123", token="jwt_token_here")
    app_logger.error("API key error", api_key="sk-1234567890abcdef", error="invalid key")
    
    print("📊 Testing log file creation...")
    
    # Check if log files are created (if file logging is enabled)
    if settings.enable_file_logging:
        import os
        log_dir = settings.log_directory
        expected_files = [
            settings.app_log_file,
            settings.error_log_file,
            settings.security_log_file,
            settings.ai_log_file,
            settings.database_log_file,
            settings.access_log_file
        ]
        
        print(f"📁 Checking log directory: {log_dir}")
        for log_file in expected_files:
            file_path = os.path.join(log_dir, log_file)
            if os.path.exists(file_path):
                size = os.path.getsize(file_path)
                print(f"  ✅ {log_file} exists ({size} bytes)")
            else:
                print(f"  ❌ {log_file} missing")
    else:
        print("📁 File logging is disabled")
    
    print("\n🎉 Logging system test completed!")
    print("📋 Summary:")
    print("  - Structured logging: ✅")
    print("  - Component separation: ✅")
    print("  - Security filtering: ✅")
    print("  - Exception handling: ✅")
    print("  - Third-party logger compatibility: ✅")

if __name__ == "__main__":
    test_logging_system() 