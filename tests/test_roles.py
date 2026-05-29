import pytest
from fastapi import status


class TestGetAllRoles:
    """Comprehensive tests for GET /roles/ endpoint."""

    def test_get_all_roles_as_admin(self, client, auth_headers_admin):
        """Test admin can retrieve all roles."""
        response = client.get("/roles/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert any(role["name"] == "ADMIN" for role in data)
        assert any(role["name"] == "USER" for role in data)

    def test_get_all_roles_as_user_denied(self, client, auth_headers_user):
        """Test regular user cannot retrieve roles."""
        response = client.get("/roles/", headers=auth_headers_user)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Permission denied" in response.json()["detail"]

    def test_get_all_roles_contains_admin_role(self, client, auth_headers_admin):
        """Test response contains ADMIN role."""
        response = client.get("/roles/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        roles = response.json()
        assert any(role["name"] == "ADMIN" for role in roles)

    def test_get_all_roles_contains_user_role(self, client, auth_headers_admin):
        """Test response contains USER role."""
        response = client.get("/roles/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        roles = response.json()
        assert any(role["name"] == "USER" for role in roles)

    def test_get_all_roles_not_empty(self, client, auth_headers_admin):
        """Test response is not empty."""
        response = client.get("/roles/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        roles = response.json()
        assert len(roles) >= 2

    def test_get_all_roles_each_has_id(self, client, auth_headers_admin):
        """Test all returned roles have id field."""
        response = client.get("/roles/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        roles = response.json()
        assert all("id" in role for role in roles)

    def test_get_all_roles_each_has_name(self, client, auth_headers_admin):
        """Test all returned roles have name field."""
        response = client.get("/roles/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        roles = response.json()
        assert all("name" in role for role in roles)

    def test_get_all_roles_ordered_by_id(self, client, auth_headers_admin):
        """Test roles are ordered by id."""
        response = client.get("/roles/", headers=auth_headers_admin)

        assert response.status_code == status.HTTP_200_OK
        roles = response.json()
        ids = [role["id"] for role in roles]
        assert ids == sorted(ids)
