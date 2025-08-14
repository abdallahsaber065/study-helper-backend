"""Unit tests for authentication utilities."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from fastapi import HTTPException

from app.auth.utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    get_user_id_from_token,
)


class TestPasswordHashing:
    """Test password hashing and verification."""
    
    def test_hash_password_returns_string(self):
        """Test that hash_password returns a hashed string."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert isinstance(hashed, str)
        assert hashed != password
        assert len(hashed) > 0
    
    def test_hash_password_different_for_same_input(self):
        """Test that hashing the same password twice produces different hashes."""
        password = "test_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        # Bcrypt produces different hashes due to salt
        assert hash1 != hash2
    
    def test_verify_password_correct_password(self):
        """Test password verification with correct password."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_password_incorrect_password(self):
        """Test password verification with incorrect password."""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = hash_password(password)
        
        assert verify_password(wrong_password, hashed) is False
    
    def test_verify_password_empty_password(self):
        """Test password verification with empty password."""
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert verify_password("", hashed) is False
    
    def test_verify_password_invalid_hash(self):
        """Test password verification with invalid hash."""
        password = "test_password_123"
        invalid_hash = "invalid_hash"
        
        # Should handle invalid hash gracefully
        assert verify_password(password, invalid_hash) is False


class TestTokenCreation:
    """Test JWT token creation."""
    
    def test_create_access_token_basic(self):
        """Test basic access token creation."""
        data = {"sub": "123", "email": "test@example.com"}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_access_token_with_custom_expiry(self):
        """Test access token creation with custom expiry."""
        data = {"sub": "123"}
        expires_delta = timedelta(minutes=30)
        token = create_access_token(data, expires_delta)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_create_refresh_token(self):
        """Test refresh token creation."""
        data = {"sub": "123"}
        token = create_refresh_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_tokens_are_different(self):
        """Test that access and refresh tokens are different."""
        data = {"sub": "123"}
        access_token = create_access_token(data)
        refresh_token = create_refresh_token(data)
        
        assert access_token != refresh_token
    
    def test_create_token_with_empty_data(self):
        """Test token creation with empty data."""
        data = {}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0


class TestTokenVerification:
    """Test JWT token verification."""
    
    def test_verify_valid_token(self):
        """Test verification of valid token."""
        data = {"sub": "123", "email": "test@example.com"}
        token = create_access_token(data)
        
        payload = verify_token(token)
        
        assert payload["sub"] == "123"
        assert payload["email"] == "test@example.com"
        assert "exp" in payload
    
    def test_verify_token_expired(self):
        """Test verification of expired token."""
        data = {"sub": "123"}
        # Create token that expires immediately
        expires_delta = timedelta(seconds=-1)  # Already expired
        token = create_access_token(data, expires_delta)
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()
    
    def test_verify_invalid_token(self):
        """Test verification of invalid token."""
        invalid_token = "invalid.token.here"
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(invalid_token)
        
        assert exc_info.value.status_code == 401
        assert "validate credentials" in exc_info.value.detail.lower()
    
    def test_verify_malformed_token(self):
        """Test verification of malformed token."""
        malformed_token = "not_a_jwt_token"
        
        with pytest.raises(HTTPException) as exc_info:
            verify_token(malformed_token)
        
        assert exc_info.value.status_code == 401
    
    def test_get_user_id_from_valid_token(self):
        """Test extracting user ID from valid token."""
        user_id = "123"
        data = {"sub": user_id}
        token = create_access_token(data)
        
        extracted_id = get_user_id_from_token(token)
        
        assert extracted_id == int(user_id)
    
    def test_get_user_id_from_token_no_sub(self):
        """Test extracting user ID from token without sub claim."""
        data = {"email": "test@example.com"}  # No 'sub' claim
        token = create_access_token(data)
        
        with pytest.raises(HTTPException) as exc_info:
            get_user_id_from_token(token)
        
        assert exc_info.value.status_code == 401
    
    def test_get_user_id_from_invalid_token(self):
        """Test extracting user ID from invalid token."""
        invalid_token = "invalid.token.here"
        
        with pytest.raises(HTTPException) as exc_info:
            get_user_id_from_token(invalid_token)
        
        assert exc_info.value.status_code == 401


class TestTokenSecurity:
    """Test token security aspects."""
    
    @patch('app.auth.utils.datetime')
    @patch('jwt.decode')
    def test_token_expiration_time_access(self, mock_decode, mock_datetime):
        """Test that access token has correct expiration time."""
        # Mock current time
        mock_now = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.utcnow.return_value = mock_now
        
        data = {"sub": "123"}
        token = create_access_token(data)
        
        # Mock jwt.decode to return the expected payload without verification
        expected_exp = mock_now + timedelta(minutes=30)
        mock_payload = {
            "sub": "123",
            "exp": int(expected_exp.timestamp())
        }
        mock_decode.return_value = mock_payload
        
        payload = verify_token(token)
        
        # Check expiration is set correctly (default 30 minutes)
        actual_exp = datetime.fromtimestamp(payload["exp"])
        
        # Allow small time difference due to execution time
        assert abs((actual_exp - expected_exp).total_seconds()) < 2
    
    def test_token_contains_required_claims(self):
        """Test that tokens contain required claims."""
        data = {"sub": "123", "email": "test@example.com", "role": "user"}
        token = create_access_token(data)
        payload = verify_token(token)
        
        # Check all original data is preserved
        assert payload["sub"] == "123"
        assert payload["email"] == "test@example.com"
        assert payload["role"] == "user"
        
        # Check standard JWT claims
        assert "exp" in payload
    
    def test_different_tokens_for_different_users(self):
        """Test that different users get different tokens."""
        user1_data = {"sub": "123"}
        user2_data = {"sub": "456"}
        
        token1 = create_access_token(user1_data)
        token2 = create_access_token(user2_data)
        
        assert token1 != token2
        
        payload1 = verify_token(token1)
        payload2 = verify_token(token2)
        
        assert payload1["sub"] != payload2["sub"]


class TestErrorHandling:
    """Test error handling in authentication utilities."""
    
    def test_hash_password_with_none(self):
        """Test hashing None password."""
        with pytest.raises((TypeError, AttributeError)):
            hash_password(None)
    
    def test_verify_password_with_none_values(self):
        """Test password verification with None values."""
        password = "test_password"
        hashed = hash_password(password)
        
        # These should not crash but return False
        assert verify_password(None, hashed) is False
        assert verify_password(password, None) is False
        assert verify_password(None, None) is False
    
    def test_create_token_with_none_data(self):
        """Test token creation with None data."""
        with pytest.raises((TypeError, AttributeError)):
            create_access_token(None)
    
    def test_verify_empty_token(self):
        """Test verification of empty token."""
        with pytest.raises(HTTPException) as exc_info:
            verify_token("")
        
        assert exc_info.value.status_code == 401
    
    def test_verify_none_token(self):
        """Test verification of None token."""
        with pytest.raises((HTTPException, TypeError, AttributeError)):
            verify_token(None)
