"""Integration tests for authentication endpoints."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from app.users.models import User, EmailVerificationToken


class TestRegisterEndpoint:
    """Test user registration endpoint."""
    
    @pytest.mark.asyncio
    async def test_register_success(self, async_client: AsyncClient, mock_email_service):
        """Test successful user registration."""
        with patch("app.auth.routes.get_email_service", return_value=mock_email_service):
            user_data = {
                "email": "newuser@example.com",
                "password": "SecurePassword123!",
            }
            
            response = await async_client.post("/auth/register", json=user_data)
            
            assert response.status_code == 201
            data = response.json()
            assert data["email"] == user_data["email"]
            assert data["is_active"] is True
            assert data["is_verified"] is False
            assert "id" in data
            assert "created_at" in data
            
            # Verify email service was called
            mock_email_service.send_verification_email.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, async_client: AsyncClient, test_user: User):
        """Test registration with duplicate email."""
        user_data = {
            "email": test_user.email,
            "password": "SecurePassword123!",
        }
        
        response = await async_client.post("/auth/register", json=user_data)
        
        assert response.status_code == 400
        data = response.json()
        assert "already registered" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_register_invalid_email(self, async_client: AsyncClient):
        """Test registration with invalid email."""
        user_data = {
            "email": "invalid-email",
            "password": "SecurePassword123!",
        }
        
        response = await async_client.post("/auth/register", json=user_data)
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_register_weak_password(self, async_client: AsyncClient):
        """Test registration with weak password."""
        user_data = {
            "email": "newuser@example.com",
            "password": "123",  # Too short
        }
        
        response = await async_client.post("/auth/register", json=user_data)
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_register_missing_fields(self, async_client: AsyncClient):
        """Test registration with missing fields."""
        user_data = {
            "email": "newuser@example.com",
            # Missing password
        }
        
        response = await async_client.post("/auth/register", json=user_data)
        
        assert response.status_code == 422


class TestLoginEndpoint:
    """Test user login endpoint."""
    
    @pytest.mark.asyncio
    async def test_login_success(self, async_client: AsyncClient, test_user: User):
        """Test successful login."""
        login_data = {
            "username": test_user.email,
            "password": test_user.plain_password,
        }
        
        response = await async_client.post("/auth/token", data=login_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
    
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, async_client: AsyncClient, test_user: User):
        """Test login with invalid credentials."""
        login_data = {
            "username": test_user.email,
            "password": "wrong_password",
        }
        
        response = await async_client.post("/auth/token", data=login_data)
        
        assert response.status_code == 401
        data = response.json()
        assert "incorrect" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, async_client: AsyncClient):
        """Test login with non-existent user."""
        login_data = {
            "username": "nonexistent@example.com",
            "password": "somepassword",
        }
        
        response = await async_client.post("/auth/token", data=login_data)
        
        assert response.status_code == 401
        data = response.json()
        assert "incorrect" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_login_inactive_user(self, async_client: AsyncClient, async_session, test_user_data):
        """Test login with inactive user."""
        # Create inactive user
        from app.auth.utils import hash_password
        
        user = User(
            email="inactive@example.com",
            hashed_password=hash_password("password123"),
            is_active=False,
            is_verified=True,
        )
        async_session.add(user)
        await async_session.commit()
        
        login_data = {
            "username": "inactive@example.com",
            "password": "password123",
        }
        
        response = await async_client.post("/auth/token", data=login_data)
        
        assert response.status_code == 400
        data = response.json()
        assert "inactive" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_login_missing_fields(self, async_client: AsyncClient):
        """Test login with missing fields."""
        login_data = {
            "username": "test@example.com",
            # Missing password
        }
        
        response = await async_client.post("/auth/token", data=login_data)
        
        assert response.status_code == 422


class TestMeEndpoint:
    """Test get current user endpoint."""
    
    @pytest.mark.asyncio
    async def test_me_success(self, async_client: AsyncClient, test_user: User, auth_headers: dict):
        """Test successful user info retrieval."""
        response = await async_client.get("/users/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email
        assert data["is_active"] == test_user.is_active
        assert data["is_verified"] == test_user.is_verified
    
    @pytest.mark.asyncio
    async def test_me_no_token(self, async_client: AsyncClient):
        """Test user info retrieval without token."""
        response = await async_client.get("/users/me")
        
        assert response.status_code == 401
        data = response.json()
        assert "not authenticated" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_me_invalid_token(self, async_client: AsyncClient):
        """Test user info retrieval with invalid token."""
        headers = {"Authorization": "Bearer invalid_token"}
        response = await async_client.get("/users/me", headers=headers)
        
        assert response.status_code == 401
        data = response.json()
        assert "validate credentials" in data["detail"].lower()


class TestEmailVerificationEndpoint:
    """Test email verification endpoint."""
    
    @pytest.mark.asyncio
    async def test_verify_email_success(
        self, 
        async_client: AsyncClient, 
        async_session,
        test_user: User
    ):
        """Test successful email verification."""
        # Create verification token
        from itsdangerous import URLSafeTimedSerializer
        from app.config import get_settings
        
        settings = get_settings()
        serializer = URLSafeTimedSerializer(settings.secret_key)
        token = serializer.dumps(test_user.email, salt="email-verification")
        
        # Create token in database
        verification_token = EmailVerificationToken(
            user_id=test_user.id,
            token_hash=token,
            token_type="verification",
            expires_at="2025-12-31 23:59:59",
            ip_address="127.0.0.1",
        )
        async_session.add(verification_token)
        await async_session.commit()
        
        response = await async_client.post(f"/auth/verify-email/{token}")
        
        assert response.status_code == 200
        data = response.json()
        assert "verified successfully" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_verify_email_invalid_token(self, async_client: AsyncClient):
        """Test email verification with invalid token."""
        response = await async_client.post("/auth/verify-email/invalid_token")
        
        assert response.status_code == 400
        data = response.json()
        assert "invalid" in data["detail"].lower() or "expired" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_resend_verification_success(
        self, 
        async_client: AsyncClient, 
        test_user: User,
        auth_headers: dict,
        mock_email_service
    ):
        """Test successful verification email resend."""
        with patch("app.auth.routes.get_email_service", return_value=mock_email_service):
            response = await async_client.post("/auth/resend-verification", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert "sent" in data["message"].lower()
            
            mock_email_service.send_verification_email.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_resend_verification_already_verified(
        self, 
        async_client: AsyncClient, 
        async_session,
        auth_headers: dict
    ):
        """Test resending verification for already verified user."""
        # User in fixture is already verified, so this should fail
        response = await async_client.post("/auth/resend-verification", headers=auth_headers)
        
        assert response.status_code == 400
        data = response.json()
        assert "already verified" in data["detail"].lower()


class TestPasswordResetEndpoint:
    """Test password reset endpoints."""
    
    @pytest.mark.asyncio
    async def test_forgot_password_success(
        self, 
        async_client: AsyncClient, 
        test_user: User,
        mock_email_service
    ):
        """Test successful forgot password request."""
        with patch("app.auth.routes.get_email_service", return_value=mock_email_service):
            request_data = {"email": test_user.email}
            response = await async_client.post("/auth/forgot-password", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            assert "sent" in data["message"].lower()
            
            mock_email_service.send_password_reset_email.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent_email(self, async_client: AsyncClient):
        """Test forgot password with non-existent email."""
        request_data = {"email": "nonexistent@example.com"}
        response = await async_client.post("/auth/forgot-password", json=request_data)
        
        # Should still return 200 for security (don't reveal if email exists)
        assert response.status_code == 200
        data = response.json()
        assert "sent" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_reset_password_success(
        self, 
        async_client: AsyncClient, 
        async_session,
        test_user: User
    ):
        """Test successful password reset."""
        # Create reset token
        from itsdangerous import URLSafeTimedSerializer
        from app.config import get_settings
        
        settings = get_settings()
        serializer = URLSafeTimedSerializer(settings.secret_key)
        token = serializer.dumps(test_user.email, salt="password-reset")
        
        # Create token in database
        reset_token = EmailVerificationToken(
            user_id=test_user.id,
            token_hash=token,
            token_type="reset",
            expires_at="2025-12-31 23:59:59",
            ip_address="127.0.0.1",
        )
        async_session.add(reset_token)
        await async_session.commit()
        
        reset_data = {
            "token": token,
            "new_password": "NewSecurePassword123!",
        }
        
        response = await async_client.post("/auth/reset-password", json=reset_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "reset successfully" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, async_client: AsyncClient):
        """Test password reset with invalid token."""
        reset_data = {
            "token": "invalid_token",
            "new_password": "NewSecurePassword123!",
        }
        
        response = await async_client.post("/auth/reset-password", json=reset_data)
        
        assert response.status_code == 400
        data = response.json()
        assert "invalid" in data["detail"].lower() or "expired" in data["detail"].lower()


class TestRefreshTokenEndpoint:
    """Test refresh token endpoint."""
    
    @pytest.mark.asyncio
    async def test_refresh_token_success(self, async_client: AsyncClient, test_user: User):
        """Test successful token refresh."""
        # First login to get refresh token
        login_data = {
            "username": test_user.email,
            "password": test_user.plain_password,
        }
        
        login_response = await async_client.post("/auth/token", data=login_data)
        assert login_response.status_code == 200
        
        refresh_token = login_response.json()["refresh_token"]
        
        # Use refresh token to get new access token
        refresh_data = {"refresh_token": refresh_token}
        response = await async_client.post("/auth/refresh", json=refresh_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, async_client: AsyncClient):
        """Test refresh with invalid token."""
        refresh_data = {"refresh_token": "invalid_refresh_token"}
        response = await async_client.post("/auth/refresh", json=refresh_data)
        
        assert response.status_code == 401
        data = response.json()
        assert "validate credentials" in data["detail"].lower()


class TestLogoutEndpoint:
    """Test logout endpoint."""
    
    @pytest.mark.asyncio
    async def test_logout_success(self, async_client: AsyncClient, auth_headers: dict):
        """Test successful logout."""
        response = await async_client.post("/auth/logout", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "logged out" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_logout_no_token(self, async_client: AsyncClient):
        """Test logout without token."""
        response = await async_client.post("/auth/logout")
        
        assert response.status_code == 401
        data = response.json()
        assert "not authenticated" in data["detail"].lower()


class TestChangePasswordEndpoint:
    """Test change password endpoint."""
    
    @pytest.mark.asyncio
    async def test_change_password_success(
        self, 
        async_client: AsyncClient, 
        test_user: User,
        auth_headers: dict
    ):
        """Test successful password change."""
        change_data = {
            "current_password": test_user.plain_password,
            "new_password": "NewSecurePassword123!",
        }
        
        response = await async_client.post("/auth/change-password", json=change_data, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "changed successfully" in data["message"].lower()
    
    @pytest.mark.asyncio
    async def test_change_password_wrong_current(
        self, 
        async_client: AsyncClient, 
        auth_headers: dict
    ):
        """Test password change with wrong current password."""
        change_data = {
            "current_password": "wrong_password",
            "new_password": "NewSecurePassword123!",
        }
        
        response = await async_client.post("/auth/change-password", json=change_data, headers=auth_headers)
        
        assert response.status_code == 400
        data = response.json()
        assert "current password is incorrect" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_change_password_weak_new_password(
        self, 
        async_client: AsyncClient, 
        test_user: User,
        auth_headers: dict
    ):
        """Test password change with weak new password."""
        change_data = {
            "current_password": test_user.plain_password,
            "new_password": "123",  # Too weak
        }
        
        response = await async_client.post("/auth/change-password", json=change_data, headers=auth_headers)
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
