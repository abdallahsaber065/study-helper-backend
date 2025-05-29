"""
Database configuration module using centralized settings.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from logging import getLogger
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = getLogger("database")
# Create cache directory if it doesn't exist
os.makedirs("cache", exist_ok=True)

# Construct database URL from environment variables
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_NAME = os.getenv("DB_NAME", "dbname")

SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

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