"""GET /users/me and GET /users."""

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import RoleName, User
from tests.helpers import AuthUser, assert_error, auth_headers


@pytest.mark.parametrize("actor", ["admin", "manager", "user"])
async def test_me_returns_the_authenticated_user_for_every_role(
    client: AsyncClient, people: dict[str, AuthUser], actor: str
):
    current = people[actor]

    response = await client.get("/users/me", headers=current.headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == current.id
    assert body["email"] == current.email
    assert body["role"] == current.role.value
    assert set(body) == {"id", "email", "role", "created_at"}


async def test_me_never_exposes_the_password_hash(client: AsyncClient, user: AuthUser):
    response = await client.get("/users/me", headers=user.headers)

    assert "password" not in response.text
    assert "hashed" not in response.text


@pytest.mark.parametrize(
    ("actor", "expected_status"),
    [("admin", 200), ("manager", 200), ("user", 403)],
)
async def test_list_users_is_restricted_to_admins_and_managers(
    client: AsyncClient, people: dict[str, AuthUser], actor: str, expected_status: int
):
    response = await client.get("/users", headers=people[actor].headers)

    if expected_status == 403:
        assert_error(response, 403, "FORBIDDEN")
    else:
        assert response.status_code == 200


async def test_list_users_returns_every_user_in_a_pagination_envelope(
    client: AsyncClient, people: dict[str, AuthUser]
):
    response = await client.get("/users", headers=people["manager"].headers)

    body = response.json()
    assert set(body) == {"items", "total", "page", "size", "pages"}
    assert body["total"] == len(people)
    assert body["page"] == 1
    assert body["size"] == 20
    assert body["pages"] == 1
    assert {item["email"] for item in body["items"]} == {
        p.email for p in people.values()
    }


async def test_list_users_is_ordered_by_id_and_paginates(
    client: AsyncClient, people: dict[str, AuthUser]
):
    expected_ids = sorted(p.id for p in people.values())
    headers = people["admin"].headers

    first = (await client.get("/users?page=1&size=2", headers=headers)).json()
    last = (await client.get("/users?page=3&size=2", headers=headers)).json()
    beyond = (await client.get("/users?page=4&size=2", headers=headers)).json()

    assert [u["id"] for u in first["items"]] == expected_ids[:2]
    assert [u["id"] for u in last["items"]] == expected_ids[4:]
    assert first["total"] == last["total"] == 5
    assert first["pages"] == 3
    assert beyond["items"] == []
    assert beyond["total"] == 5


@pytest.mark.parametrize(
    "query", ["page=0", "page=-1", "size=0", "size=101", "page=abc", "size=1.5"]
)
async def test_list_users_rejects_out_of_range_pagination(
    client: AsyncClient, admin: AuthUser, query: str
):
    response = await client.get(f"/users?{query}", headers=admin.headers)

    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert isinstance(error["details"], list)
    assert error["details"]


async def test_list_users_accepts_the_maximum_page_size(
    client: AsyncClient, admin: AuthUser
):
    response = await client.get("/users?size=100", headers=admin.headers)

    assert response.status_code == 200
    assert response.json()["size"] == 100


async def test_role_is_read_from_the_database_not_from_the_token(
    client: AsyncClient, user: AuthUser
):
    # A USER holding a (validly signed) token that claims ADMIN gains nothing.
    forged = create_access_token(user.id, RoleName.ADMIN.value)

    me = await client.get("/users/me", headers=auth_headers(forged))
    listing = await client.get("/users", headers=auth_headers(forged))

    assert me.json()["role"] == "USER"
    assert_error(listing, 403, "FORBIDDEN")


async def test_token_of_a_deleted_user_is_rejected(
    client: AsyncClient, db_session: AsyncSession, user: AuthUser
):
    await db_session.execute(delete(User).where(User.id == user.id))
    await db_session.commit()

    response = await client.get("/users/me", headers=user.headers)

    assert_error(response, 401, "UNAUTHORIZED")
