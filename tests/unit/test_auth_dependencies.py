"""Unit tests for authentication dependencies."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.auth.dependencies import (
    get_current_user,
    get_current_active_user,
    get_current_verified_user,
    get_optional_current_user,
    get_current_user_websocket,
)
from app.users.models import User


class TestGetCurrentUser:
    """Test get_current_user dependency."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        mock_db = AsyncMock()
        return mock_db
    
    @pytest.fixture
    def mock_user(self):
        """Mock user object."""
        user = User(
            id=1,
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_verified=True,
        )
        return user
    
    @patch("app.auth.dependencies.get_user_id_from_token")
    async def test_get_current_user_success(self, mock_get_user_id, mock_db, mock_user):
        """Test successful user retrieval."""
        # Setup mocks
        mock_get_user_id.return_value = 1
        
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result
        
        # Test
        token = "valid_token"
        user = await get_current_user(token, mock_db)
        
        assert user == mock_user
        mock_get_user_id.assert_called_once_with(token)
        mock_db.execute.assert_called_once()
    
    @patch("app.auth.dependencies.get_user_id_from_token")
    async def test_get_current_user_not_found(self, mock_get_user_id, mock_db):
        """Test user not found in database."""
        # Setup mocks
        mock_get_user_id.return_value = 999
        
        # Mock database query returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        # Test
        token = "valid_token"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token, mock_db)
        
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail
    
    @patch("app.auth.dependencies.get_user_id_from_token")
    async def test_get_current_user_invalid_token(self, mock_get_user_id, mock_db):
        """Test invalid token handling."""
        # Mock token verification failure
        mock_get_user_id.side_effect = HTTPException(status_code=401, detail="Invalid token")
        
        # Test
        token = "invalid_token"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token, mock_db)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail


class TestGetCurrentActiveUser:
    """Test get_current_active_user dependency."""
    
    async def test_get_current_active_user_success(self):
        """Test with active user."""
        user = User(
            id=1,
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_verified=True,
        )
        
        result = await get_current_active_user(user)
        assert result == user
    
    async def test_get_current_active_user_inactive(self):
        """Test with inactive user."""
        user = User(
            id=1,
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=False,
            is_verified=True,
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(user)
        
        assert exc_info.value.status_code == 400
        assert "Inactive user" in exc_info.value.detail


class TestGetCurrentVerifiedUser:
    """Test get_current_verified_user dependency."""
    
    async def test_get_current_verified_user_success(self):
        """Test with verified user."""
        user = User(
            id=1,
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_verified=True,
        )
        
        result = await get_current_verified_user(user)
        assert result == user
    
    async def test_get_current_verified_user_unverified(self):
        """Test with unverified user."""
        user = User(
            id=1,
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_verified=False,
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_verified_user(user)
        
        assert exc_info.value.status_code == 400
        assert "User email not verified" in exc_info.value.detail


class TestGetOptionalCurrentUser:
    """Test get_optional_current_user dependency."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return AsyncMock()
    
    async def test_get_optional_current_user_no_token(self, mock_db):
        """Test with no token provided."""
        result = await get_optional_current_user(None, mock_db)
        assert result is None
    
    @patch("app.auth.dependencies.get_current_user")
    async def test_get_optional_current_user_valid_token(self, mock_get_current_user, mock_db):
        """Test with valid token."""
        user = User(
            id=1,
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_verified=True,
        )
        mock_get_current_user.return_value = user
        
        result = await get_optional_current_user("valid_token", mock_db)
        assert result == user
    
    @patch("app.auth.dependencies.get_current_user")
    async def test_get_optional_current_user_invalid_token(self, mock_get_current_user, mock_db):
        """Test with invalid token."""
        mock_get_current_user.side_effect = HTTPException(status_code=401, detail="Invalid token")
        
        result = await get_optional_current_user("invalid_token", mock_db)
        assert result is None


class TestGetCurrentUserWebSocket:
    """Test get_current_user_websocket dependency."""
    
    @patch("app.auth.dependencies.get_async_db_session")
    @patch("app.auth.dependencies.get_user_id_from_token")
    async def test_get_current_user_websocket_success(self, mock_get_user_id, mock_get_db_session):
        """Test successful WebSocket user retrieval."""
        # Setup user
        user = User(
            id=1,
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_verified=True,
        )
        
        # Setup mocks
        mock_get_user_id.return_value = 1
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result
        
        # Mock async context manager
        mock_get_db_session.return_value.__aenter__.return_value = mock_db
        mock_get_db_session.return_value.__aexit__.return_value = None
        
        # Test
        token = "valid_token"
        result = await get_current_user_websocket(token)
        
        assert result == user
        mock_get_user_id.assert_called_once_with(token)
    
    @patch("app.auth.dependencies.get_async_db_session")
    @patch("app.auth.dependencies.get_user_id_from_token")
    async def test_get_current_user_websocket_user_not_found(self, mock_get_user_id, mock_get_db_session):
        """Test WebSocket user not found."""
        # Setup mocks
        mock_get_user_id.return_value = 999
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        mock_get_db_session.return_value.__aenter__.return_value = mock_db
        mock_get_db_session.return_value.__aexit__.return_value = None
        
        # Test
        token = "valid_token"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_websocket(token)
        
        assert exc_info.value.status_code == 401
        assert "User not found" in exc_info.value.detail
    
    @patch("app.auth.dependencies.get_async_db_session")
    @patch("app.auth.dependencies.get_user_id_from_token")
    async def test_get_current_user_websocket_inactive_user(self, mock_get_user_id, mock_get_db_session):
        """Test WebSocket with inactive user."""
        # Setup inactive user
        user = User(
            id=1,
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=False,
            is_verified=True,
        )
        
        # Setup mocks
        mock_get_user_id.return_value = 1
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result
        
        mock_get_db_session.return_value.__aenter__.return_value = mock_db
        mock_get_db_session.return_value.__aexit__.return_value = None
        
        # Test
        token = "valid_token"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_websocket(token)
        
        assert exc_info.value.status_code == 400
        assert "Inactive user" in exc_info.value.detail
    
    @patch("app.auth.dependencies.get_user_id_from_token")
    async def test_get_current_user_websocket_invalid_token(self, mock_get_user_id):
        """Test WebSocket with invalid token."""
        mock_get_user_id.side_effect = HTTPException(status_code=401, detail="Invalid token")
        
        token = "invalid_token"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_websocket(token)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail
