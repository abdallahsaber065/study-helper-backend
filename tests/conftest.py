"""Global test configuration and fixtures."""

import asyncio
import os
import tempfile
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.database import Base, get_db_session, get_async_db_session
from backend.main import app
from app.users.models import User  # noqa: F401 – registers tables in Base.metadata
from app.files.models import FileMetadata  # noqa: F401 – registers tables in Base.metadata
from app.auth.utils import create_access_token, hash_password


# Test settings override
class TestSettings(Settings):
    """Test-specific settings."""
    
    # Database
    database_url: str = "sqlite:///./test_study_assistant.db"
    database_async_url: str = "sqlite+aiosqlite:///./test_study_assistant.db"
    
    # Testing flags
    testing: bool = True
    debug: bool = True
    
    # Disable external services
    enable_redis: bool = False
    enable_celery: bool = False
    enable_email: bool = False
    
    # Security
    jwt_secret_key: str = "test_secret_key_for_testing_only_do_not_use_in_production"
    
    # File upload
    max_file_size: int = 10 * 1024 * 1024  # 10MB for testing
    upload_dir: str = "test_uploads"


@pytest.fixture(scope="session")
def test_settings() -> TestSettings:
    """Override settings for testing."""
    return TestSettings()


# Override the settings dependency
@pytest.fixture(autouse=True)
def override_settings(test_settings: TestSettings) -> None:
    """Override the get_settings dependency."""
    app.dependency_overrides[get_settings] = lambda: test_settings


# Database fixtures
# Use in-memory SQLite with StaticPool so all connections share the same DB.
# This avoids file-locking and stale-data issues between test runs.
_TEST_SYNC_URL = "sqlite:///./test_study_assistant_unit.db"
_TEST_ASYNC_URL = "sqlite+aiosqlite:///./test_study_assistant_unit.db"


@pytest.fixture(scope="session")
def sync_engine():
    """Create a synchronous test database engine."""
    engine = create_engine(
        _TEST_SYNC_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


@pytest.fixture(scope="session")
def async_engine():
    """Create an asynchronous test database engine."""
    engine = create_async_engine(
        _TEST_ASYNC_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


@pytest.fixture(scope="session", autouse=True)
def setup_test_database(sync_engine):
    """Create all tables once per session, drop stale data first."""
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)
    yield
    Base.metadata.drop_all(bind=sync_engine)


@pytest.fixture(autouse=True)
async def clean_tables(async_engine):
    """Truncate all tables before each test for full isolation."""
    from sqlalchemy import text

    async with async_engine.connect() as conn:
        # Disable FK constraints temporarily (SQLite syntax)
        await conn.execute(text("PRAGMA foreign_keys = OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        await conn.commit()


@pytest.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create an async database session for testing."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session_maker() as session:
        yield session


@pytest.fixture
def override_get_async_db_session(async_session: AsyncSession):
    """Override both session dependencies so routes use the test database."""
    async def _get_test_db():
        yield async_session
    
    app.dependency_overrides[get_db_session] = _get_test_db
    app.dependency_overrides[get_async_db_session] = _get_test_db
    yield
    del app.dependency_overrides[get_db_session]
    del app.dependency_overrides[get_async_db_session]


# HTTP client fixtures
@pytest.fixture
def client(override_get_async_db_session) -> Generator[TestClient, None, None]:
    """Create a test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client(override_get_async_db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    from fastapi.testclient import TestClient
    from httpx import ASGITransport
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# User fixtures
@pytest.fixture
async def test_user_data() -> dict:
    """Test user data – unverified so that email-verification tests work correctly."""
    return {
        "email": "test@example.com",
        "password": "TestPassword123!",
        "is_active": True,
        "is_verified": False,
    }


@pytest.fixture
async def test_user(async_session: AsyncSession, test_user_data: dict) -> User:
    """Create a test user in the database."""
    user_data = test_user_data.copy()
    password = user_data.pop("password")
    hashed_password = hash_password(password)
    
    user = User(**user_data, hashed_password=hashed_password)
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    
    # Add the plain password back for testing
    user.plain_password = password
    return user


@pytest.fixture
async def admin_user(async_session: AsyncSession) -> User:
    """Create an admin user for testing."""
    user_data = {
        "email": "admin@example.com",
        "hashed_password": hash_password("AdminPassword123!"),
        "is_active": True,
        "is_verified": True,
    }
    
    user = User(**user_data)
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    
    user.plain_password = "AdminPassword123!"
    return user


@pytest.fixture
def access_token(test_user: User) -> str:
    """Create an access token for the test user."""
    return create_access_token(data={"sub": str(test_user.id)})


@pytest.fixture
def admin_access_token(admin_user: User) -> str:
    """Create an access token for the admin user."""
    return create_access_token(data={"sub": str(admin_user.id)})


@pytest.fixture
def auth_headers(access_token: str) -> dict:
    """Create authorization headers with the access token."""
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def admin_auth_headers(admin_access_token: str) -> dict:
    """Create admin authorization headers."""
    return {"Authorization": f"Bearer {admin_access_token}"}


# File fixtures
@pytest.fixture
def temp_upload_dir(test_settings: TestSettings) -> Generator[str, None, None]:
    """Create a temporary upload directory for testing."""
    upload_dir = test_settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    yield upload_dir
    
    # Cleanup
    import shutil
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)


@pytest.fixture
def sample_file_content() -> bytes:
    """Sample file content for testing."""
    return b"This is a sample file content for testing purposes. It contains some text to process."


@pytest.fixture
def sample_pdf_content() -> bytes:
    """Sample PDF content for testing."""
    # Minimal PDF content
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 4 0 R
>>
>>
/MediaBox [0 0 612 792]
/Contents 5 0 R
>>
endobj

4 0 obj
<<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
endobj

5 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Test PDF content) Tj
ET
endstream
endobj

xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000247 00000 n 
0000000315 00000 n 
trailer
<<
/Size 6
/Root 1 0 R
>>
startxref
404
%%EOF"""


@pytest.fixture
async def test_file_metadata(
    async_session: AsyncSession, 
    test_user: User,
    temp_upload_dir: str,
    sample_file_content: bytes
) -> FileMetadata:
    """Create test file metadata in the database."""
    import uuid
    from pathlib import Path
    
    file_id = str(uuid.uuid4())
    filename = "test_document.txt"
    file_path = Path(temp_upload_dir) / f"{file_id}.txt"
    
    # Write test file
    file_path.write_bytes(sample_file_content)
    
    file_metadata = FileMetadata(
        id=file_id,
        user_id=test_user.id,
        stored_filename=f"{file_id}.txt",
        original_filename=filename,
        mime_type="text/plain",
        file_size=len(sample_file_content),
        file_path=str(file_path),
        file_hash="test_hash",
    )
    
    async_session.add(file_metadata)
    await async_session.commit()
    await async_session.refresh(file_metadata)
    
    return file_metadata


# Mock fixtures for external services
@pytest.fixture
def mock_openai_provider():
    """Mock OpenAI provider for testing."""
    mock = MagicMock()
    mock.generate_summary = AsyncMock(return_value={
        "summary": "This is a test summary generated by AI.",
        "tokens_used": 150,
        "model": "gpt-3.5-turbo",
        "cost": 0.0001,
    })
    mock.generate_quiz = AsyncMock(return_value={
        "quiz": {
            "title": "Test Quiz",
            "questions": [
                {
                    "question": "What is this test about?",
                    "type": "multiple_choice",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "A",
                }
            ]
        },
        "tokens_used": 200,
        "model": "gpt-3.5-turbo",
        "cost": 0.0002,
    })
    return mock


@pytest.fixture
def mock_email_service():
    """Mock email service for testing."""
    mock = MagicMock()
    mock.send_verification_email = AsyncMock(return_value={"status": "sent"})
    mock.send_password_reset_email = AsyncMock(return_value={"status": "sent"})
    mock.send_notification_email = AsyncMock(return_value={"status": "sent"})
    mock.health_check = AsyncMock(return_value={"status": "healthy"})
    return mock


@pytest.fixture
def mock_redis():
    """Mock Redis for testing."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.exists = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def mock_celery_task():
    """Mock Celery task for testing."""
    mock = MagicMock()
    mock.apply_async = MagicMock()
    mock.delay = MagicMock()
    mock.id = "test_task_id"
    mock.state = "PENDING"
    return mock


# Event loop configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
