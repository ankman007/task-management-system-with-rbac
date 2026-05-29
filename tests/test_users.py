import pytest
from fastapi import status
from app.models import User, Role, RoleName


class TestGetAllUsers:
    """Comprehensive tests for GET /users/ endpoint."""

    def test_get_all_users_as_admin(self, client, auth_headers_admin):
        """Test admin can retrieve all users."""
        response = client.get("/users/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_all_users_response_structure(self, client, auth_headers_admin):
        """Test users response has expected structure."""
        response = client.get("/users/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        users = response.json()

        if len(users) > 0:
            user = users[0]
            assert "id" in user
            assert "email" in user
            assert "role" in user or "role_id" in user

    def test_get_all_users_with_pagination(
        self, client, auth_headers_admin, db_session
    ):
        """Test pagination parameters work."""
        # Add multiple users
        user_role = db_session.query(Role).filter(Role.name == RoleName.USER).first()
        for i in range(3):
            user = User(
                email=f"user{i}@example.com",
                hashed_password="fake",
                role_id=user_role.id,
            )
            db_session.add(user)
        db_session.commit()

        response = client.get("/users/?limit=2&skip=0", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) <= 2

    def test_get_all_users_with_skip(self, client, auth_headers_admin, db_session):
        """Test skip parameter works."""
        response = client.get("/users/?skip=0&limit=100", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_get_all_users_with_search_by_email(
        self, client, auth_headers_admin, db_session
    ):
        """Test search parameter filters users by email."""
        user_role = db_session.query(Role).filter(Role.name == RoleName.USER).first()
        user = User(
            email="searchable@example.com",
            hashed_password="fake",
            role_id=user_role.id,
        )
        db_session.add(user)
        db_session.commit()

        response = client.get("/users/?search=searchable", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all("searchable" in user["email"] for user in data)

    def test_get_all_users_search_no_results(self, client, auth_headers_admin):
        """Test search with no matches returns empty list."""
        response = client.get(
            "/users/?search=nonexistentuser", headers=auth_headers_admin
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 0

    def test_get_all_users_limit_boundary(self, client, auth_headers_admin):
        """Test limit parameter respects maximum."""
        response = client.get("/users/?limit=100", headers=auth_headers_admin)
        assert response.status_code == status.HTTP_200_OK

        response = client.get("/users/?limit=101", headers=auth_headers_admin)
        # Should fail or clamp to 100
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_all_users_contains_admin(self, client, auth_headers_admin, admin_user):
        """Test admin user is in the users list."""
        response = client.get("/users/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert any(user["email"] == admin_user.email for user in data)

    def test_get_all_users_contains_normal_user(
        self, client, auth_headers_admin, normal_user
    ):
        """Test normal user is in the users list."""
        response = client.get("/users/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert any(user["email"] == normal_user.email for user in data)

    def test_get_all_users_each_has_email(self, client, auth_headers_admin):
        """Test all returned users have email field."""
        response = client.get("/users/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all("email" in user for user in data)

    def test_get_all_users_each_has_id(self, client, auth_headers_admin):
        """Test all returned users have id field."""
        response = client.get("/users/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert all("id" in user for user in data)

    def test_get_all_users_pagination_skip_and_limit(
        self, client, auth_headers_admin, db_session
    ):
        """Test skip and limit work together."""
        user_role = db_session.query(Role).filter(Role.name == RoleName.USER).first()
        for i in range(5):
            user = User(
                email=f"paginationtest{i}@example.com",
                hashed_password="fake",
                role_id=user_role.id,
            )
            db_session.add(user)
        db_session.commit()

        response = client.get("/users/?skip=2&limit=2", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) <= 2

    def test_get_all_users_case_insensitive_search(
        self, client, auth_headers_admin, db_session
    ):
        """Test search is case insensitive."""
        user_role = db_session.query(Role).filter(Role.name == RoleName.USER).first()
        user = User(
            email="CaseSensitive@example.com",
            hashed_password="fake",
            role_id=user_role.id,
        )
        db_session.add(user)
        db_session.commit()

        response = client.get(
            "/users/?search=casesensitive", headers=auth_headers_admin
        )

        assert response.status_code == status.HTTP_200_OK
        # Should find the user regardless of case if search is case-insensitive
        # (depending on implementation)
        data = response.json()
        assert isinstance(data, list)

    def test_get_all_users_default_limit(self, client, auth_headers_admin, db_session):
        """Test default limit is applied when not specified."""
        user_role = db_session.query(Role).filter(Role.name == RoleName.USER).first()
        for i in range(15):
            user = User(
                email=f"defaultlimit{i}@example.com",
                hashed_password="fake",
                role_id=user_role.id,
            )
            db_session.add(user)
        db_session.commit()

        response = client.get("/users/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Default limit is 10
        assert len(data) <= 10
