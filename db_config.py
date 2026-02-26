"""
Database configuration module using centralized settings.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from core.config import settings

# Import logging after settings to avoid circular imports
try:
    from core.logging import get_logger
    logger = get_logger("database")
except ImportError:
    # Fallback to standard logging if core.logging is not available yet
    import logging
    logger = logging.getLogger("database")

# Load environment variables from .env file

# Construct database URL from environment variables
DB_HOST = settings.db_host
DB_PORT = settings.db_port
DB_USER = settings.db_user
DB_PASSWORD = settings.db_password
DB_NAME = settings.db_name

SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
ASYNC_SQLALCHEMY_DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

logger.info("Database configuration loaded", 
           host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER)

# Create SQLAlchemy engines
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.enable_sql_logging  # Enable SQL logging based on settings
)

async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.enable_sql_logging  # Enable SQL logging based on settings
)

# Create SessionLocal classes
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Create Base class
Base = declarative_base()

# Dependency to get database session (sync)
def get_db():
    db = SessionLocal()
    try:
        logger.debug("Database session created")
        yield db
    except Exception as e:
        logger.error("Database session error", error=str(e), exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()
        logger.debug("Database session closed")

# Dependency to get async database session
async def get_async_db():
    async with AsyncSessionLocal() as db:
        try:
            logger.debug("Async database session created")
            yield db
        except Exception as e:
            logger.error("Async database session error", error=str(e), exc_info=True)
            await db.rollback()
            raise
        finally:
            await db.close()
            logger.debug("Async database session closed") 