"""
Database configuration module using centralized settings.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from logging import getLogger

logger = getLogger("database")
# Create cache directory if it doesn't exist
os.makedirs("cache", exist_ok=True)

# Get database URL from settings
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")

logger.info("Database configuration", database_url=SQLALCHEMY_DATABASE_URL.split('@')[0] + '@***')

# Create SQLAlchemy engine

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600
)
logger.info("Using PostgreSQL database", host=SQLALCHEMY_DATABASE_URL.split('@')[1].split('/')[0], database=SQLALCHEMY_DATABASE_URL.split('/')[-1])

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 