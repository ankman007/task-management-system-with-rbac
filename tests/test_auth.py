import pytest
from fastapi import status


class TestSignup:
    """Comprehensive tests for POST /auth/signup endpoint."""

    def test_user_signup_success(self, client, db_session):
        """Test successful user signup with valid credentials."""
        response = client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "password": "strongpassword123",
                "role_id": 1,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["user"]["email"] == "testuser@example.com"
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_signup_duplicate_email(self, client):
        """Test signup fails when email already exists."""
        client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "password": "strongpassword123",
                "role_id": 1,
            },
        )

        response = client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "password": "anotherpassword456",
                "role_id": 1,
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"]

    def test_signup_invalid_role_id(self, client):
        """Test signup fails with non-existent role_id."""
        response = client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "password": "strongpassword123",
                "role_id": 999,
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "role" in response.json()["detail"].lower()

    def test_signup_missing_email(self, client):
        """Test signup fails with missing email."""
        response = client.post(
            "/auth/signup",
            json={
                "password": "strongpassword123",
                "role_id": 1,
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_signup_missing_password(self, client):
        """Test signup fails with missing password."""
        response = client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "role_id": 1,
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_signup_missing_role_id(self, client):
        """Test signup fails with missing role_id."""
        response = client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "password": "strongpassword123",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_signup_empty_email(self, client):
        """Test signup fails with empty email."""
        response = client.post(
            "/auth/signup",
            json={
                "email": "",
                "password": "strongpassword123",
                "role_id": 1,
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_signup_invalid_email_format(self, client):
        """Test signup fails with invalid email format."""
        response = client.post(
            "/auth/signup",
            json={
                "email": "not-an-email",
                "password": "strongpassword123",
                "role_id": 1,
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestLogin:
    """Comprehensive tests for POST /auth/login endpoint."""

    def test_login_success(self, client):
        """Test successful login with valid credentials."""
        client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "password": "strongpassword123",
                "role_id": 1,
            },
        )

        response = client.post(
            "/auth/login",
            json={"email": "testuser@example.com", "password": "strongpassword123"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "testuser@example.com"

    def test_login_wrong_password(self, client):
        """Test login fails with wrong password."""
        client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "password": "strongpassword123",
                "role_id": 1,
            },
        )

        response = client.post(
            "/auth/login",
            json={"email": "testuser@example.com", "password": "wrongpassword"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Incorrect" in response.json()["detail"]

    def test_login_non_existent_user(self, client):
        """Test login fails with non-existent user."""
        response = client.post(
            "/auth/login",
            json={"email": "nonexistent@example.com", "password": "anypassword"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Incorrect" in response.json()["detail"]

    def test_login_missing_email(self, client):
        """Test login fails with missing email."""
        response = client.post(
            "/auth/login",
            json={"password": "strongpassword123"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_login_missing_password(self, client):
        """Test login fails with missing password."""
        response = client.post(
            "/auth/login",
            json={"email": "testuser@example.com"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_login_empty_email(self, client):
        """Test login fails with empty email."""
        response = client.post(
            "/auth/login",
            json={"email": "", "password": "strongpassword123"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestRefreshToken:
    """Comprehensive tests for POST /auth/refresh endpoint."""

    def test_refresh_token_success(self, client):
        """Test successful token refresh with valid refresh token."""
        signup_response = client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "password": "strongpassword123",
                "role_id": 1,
            },
        )

        refresh_token = signup_response.json()["refresh_token"]

        response = client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_refresh_token_invalid(self, client):
        """Test refresh fails with invalid token."""
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Expired or invalid" in response.json()["detail"]

    def test_refresh_token_malformed(self, client):
        """Test refresh fails with malformed token."""
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "not-a-jwt-token"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_token_empty(self, client):
        """Test refresh fails with empty token."""
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": ""},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_token_missing(self, client):
        """Test refresh fails with missing refresh_token field."""
        response = client.post(
            "/auth/refresh",
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_refresh_token_deleted_user(self, client, db_session):
        """Test refresh fails when user no longer exists."""
        from app.models import User

        signup_response = client.post(
            "/auth/signup",
            json={
                "email": "testuser@example.com",
                "password": "strongpassword123",
                "role_id": 1,
            },
        )

        refresh_token = signup_response.json()["refresh_token"]

        # Delete the user from database
        user = (
            db_session.query(User).filter(User.email == "testuser@example.com").first()
        )
        db_session.delete(user)
        db_session.commit()

        response = client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "User not found" in response.json()["detail"]
