#!/usr/bin/env python3
"""
Test script to demonstrate rotating file logging functionality.
"""
import sys
import os
import time
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logging import setup_logging, get_logger
from core.config import settings

def test_logging():
    """Test the rotating file logging functionality."""
    print("Setting up logging...")
    setup_logging()
    
    # Get different loggers
    app_logger = get_logger("app")
    security_logger = get_logger("security")
    ai_logger = get_logger("ai_manager")
    db_logger = get_logger("database")
    
    print(f"Log directory: {settings.log_directory}")
    print(f"File logging enabled: {settings.enable_file_logging}")
    print(f"Log format: {settings.log_format}")
    print(f"Max file size: {settings.log_file_max_size_mb}MB")
    print(f"Backup count: {settings.log_file_backup_count}")
    print(f"Compression enabled: {settings.log_compression}")
    print()
    
    # Test different log levels and loggers
    print("Testing different log levels and loggers...")
    
    app_logger.info("Application started successfully")
    app_logger.debug("Debug information for troubleshooting")
    app_logger.warning("This is a warning message")
    
    security_logger.info("User authentication successful", user_id=123)
    security_logger.warning("Failed login attempt", ip_address="192.168.1.100")
    security_logger.error("Security breach detected", severity="high")
    
    ai_logger.info("AI request processed", model="gemini-2.0-flash", tokens=150)
    ai_logger.warning("AI rate limit approaching", remaining_calls=5)
    
    db_logger.info("Database connection established")
    db_logger.warning("Slow query detected", duration="2.5s")
    db_logger.error("Database connection failed", error="timeout")
    
    # Test error logging
    try:
        raise ValueError("This is a test exception")
    except Exception as e:
        app_logger.error("Test exception occurred", exc_info=True)
    
    print("Log entries written. Check the logs directory for files.")
    
    # Show log files created
    log_dir = Path(settings.log_directory)
    if log_dir.exists():
        print(f"\nLog files in {log_dir}:")
        for log_file in log_dir.glob("*.log*"):
            size = log_file.stat().st_size
            print(f"  {log_file.name} ({size} bytes)")
    
    return True


def test_log_rotation():
    """Test log rotation by generating many log entries."""
    print("\nTesting log rotation...")
    setup_logging()
    
    app_logger = get_logger("app")
    
    # Generate many log entries to trigger rotation
    print("Generating log entries to test rotation...")
    for i in range(1000):
        app_logger.info(f"Log entry {i+1} - Testing log rotation functionality with some additional text to increase log size")
        if i % 100 == 0:
            print(f"Generated {i+1} log entries...")
    
    # Check for rotated files
    log_dir = Path(settings.log_directory)
    if log_dir.exists():
        print(f"\nLog files after rotation test:")
        for log_file in sorted(log_dir.glob("*.log*")):
            size = log_file.stat().st_size
            print(f"  {log_file.name} ({size} bytes)")


if __name__ == "__main__":
    print("=== Testing Rotating File Logging ===")
    
    # Test basic logging
    test_logging()
    
    # Test rotation (optional - generates many log entries)
    response = input("\nDo you want to test log rotation? (y/N): ")
    if response.lower() in ['y', 'yes']:
        test_log_rotation()
    
    print("\nLogging test completed!") 