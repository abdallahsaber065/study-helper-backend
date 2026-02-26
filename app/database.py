"""Database configuration and session management."""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# Create the SQLAlchemy base class
Base = declarative_base()

# Build connect_args for SQLite (required for multi-thread use in tests)
_sync_connect_args: dict = {}
_async_connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    _sync_connect_args = {"check_same_thread": False}
    _async_connect_args = {"check_same_thread": False}

# Sync Engine for migrations and some operations
_sync_engine_kwargs: dict = {
    "echo": settings.database_echo,
    "connect_args": _sync_connect_args,
}
if not settings.database_url.startswith("sqlite"):
    _sync_engine_kwargs["pool_size"] = settings.database_pool_size
    _sync_engine_kwargs["max_overflow"] = settings.database_max_overflow

sync_engine = create_engine(settings.database_url, **_sync_engine_kwargs)

# Async Engine – use the dedicated async URL from settings
_async_engine_kwargs: dict = {
    "echo": settings.database_echo,
    "connect_args": _async_connect_args,
}
if not settings.database_async_url.startswith("sqlite"):
    _async_engine_kwargs["pool_size"] = settings.database_pool_size
    _async_engine_kwargs["max_overflow"] = settings.database_max_overflow

async_engine = create_async_engine(settings.database_async_url, **_async_engine_kwargs)

# Session makers
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Database session dependency for FastAPI
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session for dependency injection."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Sync session context manager for migrations
@contextmanager
def get_sync_db_session() -> Generator[Session, None, None]:
    """Get sync database session for migrations and scripts."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Async session context manager for scripts
@asynccontextmanager
async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session for scripts."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Database initialization
async def init_db() -> None:
    """Initialize database tables."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await async_engine.dispose()


def create_db_tables() -> None:
    """Create database tables (sync version for migrations)."""
    Base.metadata.create_all(bind=sync_engine)


def drop_db_tables() -> None:
    """Drop database tables (sync version for testing)."""
    Base.metadata.drop_all(bind=sync_engine)


# Event listeners for connection pool management
@event.listens_for(sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set database-specific settings on connection."""
    # This would be used for SQLite pragmas, but we're using PostgreSQL
    pass


@event.listens_for(sync_engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """Handle connection checkout from pool."""
    # Add any connection-level setup here if needed
    pass


# Health check function
async def check_db_health() -> bool:
    """Check if database is accessible."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute("SELECT 1")
            return result.scalar() == 1
    except Exception:
        return False


def check_sync_db_health() -> bool:
    """Check if database is accessible (sync version)."""
    try:
        with get_sync_db_session() as session:
            result = session.execute("SELECT 1")
            return result.scalar() == 1
    except Exception:
        return False
