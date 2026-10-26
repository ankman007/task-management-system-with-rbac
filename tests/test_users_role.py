"""PATCH /users/{id}/role: ADMIN-only role management."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RoleName, User
from tests.helpers import AuthUser, assert_error


async def _role_in_db(db_session: AsyncSession, user_id: int) -> RoleName:
    user = await db_session.get(User, user_id, populate_existing=True)
    assert user is not None
    return user.role.name


@pytest.mark.parametrize(
    ("target", "new_role"),
    [
        ("user", RoleName.MANAGER),
        ("user", RoleName.ADMIN),
        ("manager", RoleName.USER),
        ("manager", RoleName.ADMIN),
    ],
)
async def test_admin_can_change_any_users_role(
    client: AsyncClient,
    db_session: AsyncSession,
    people: dict[str, AuthUser],
    target: str,
    new_role: RoleName,
):
    target_user = people[target]

    response = await client.patch(
        f"/users/{target_user.id}/role",
        json={"role": new_role},
        headers=people["admin"].headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == target_user.id
    assert body["email"] == target_user.email
    assert body["role"] == new_role
    assert await _role_in_db(db_session, target_user.id) == new_role


@pytest.mark.parametrize("actor", ["manager", "other_manager", "user", "other_user"])
@pytest.mark.parametrize("new_role", list(RoleName))
async def test_non_admins_cannot_change_roles_including_their_own(
    client: AsyncClient,
    db_session: AsyncSession,
    people: dict[str, AuthUser],
    actor: str,
    new_role: RoleName,
):
    caller = people[actor]

    response = await client.patch(
        f"/users/{caller.id}/role", json={"role": new_role}, headers=caller.headers
    )

    assert_error(response, 403, "FORBIDDEN")
    assert await _role_in_db(db_session, caller.id) == caller.role


async def test_manager_cannot_promote_another_user(
    client: AsyncClient,
    db_session: AsyncSession,
    manager: AuthUser,
    user: AuthUser,
):
    response = await client.patch(
        f"/users/{user.id}/role", json={"role": "MANAGER"}, headers=manager.headers
    )

    assert_error(response, 403, "FORBIDDEN")
    assert await _role_in_db(db_session, user.id) == RoleName.USER


async def test_promotion_takes_effect_with_the_users_existing_token(
    client: AsyncClient, admin: AuthUser, user: AuthUser
):
    task = {"title": "Plan the sprint"}
    before = await client.post("/tasks", json=task, headers=user.headers)
    assert_error(before, 403, "FORBIDDEN")

    await client.patch(
        f"/users/{user.id}/role", json={"role": "MANAGER"}, headers=admin.headers
    )
    after = await client.post("/tasks", json=task, headers=user.headers)

    assert after.status_code == 201, after.text


async def test_demotion_takes_effect_with_the_users_existing_token(
    client: AsyncClient, admin: AuthUser, manager: AuthUser
):
    await client.patch(
        f"/users/{manager.id}/role", json={"role": "USER"}, headers=admin.headers
    )

    response = await client.post(
        "/tasks", json={"title": "Plan the sprint"}, headers=manager.headers
    )

    assert_error(response, 403, "FORBIDDEN")


async def test_setting_the_current_role_is_a_no_op(
    client: AsyncClient, admin: AuthUser, manager: AuthUser
):
    response = await client.patch(
        f"/users/{manager.id}/role", json={"role": "MANAGER"}, headers=admin.headers
    )

    assert response.status_code == 200
    assert response.json()["role"] == "MANAGER"


async def test_unknown_user_returns_404(client: AsyncClient, admin: AuthUser):
    response = await client.patch(
        "/users/999999/role", json={"role": "USER"}, headers=admin.headers
    )

    assert_error(response, 404, "NOT_FOUND")


@pytest.mark.parametrize(
    "body",
    [
        {"role": "SUPERUSER"},
        {"role": "admin"},
        {"role": ""},
        {"role": None},
        {},
        {"role": "USER", "email": "someone@example.com"},
    ],
    ids=["unknown", "lowercase", "empty", "null", "missing", "extra-field"],
)
async def test_invalid_role_payloads_are_rejected(
    client: AsyncClient, admin: AuthUser, user: AuthUser, body: dict
):
    response = await client.patch(
        f"/users/{user.id}/role", json=body, headers=admin.headers
    )

    assert_error(response, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("user_id", ["0", "-1", "abc"])
async def test_invalid_user_id_is_rejected(
    client: AsyncClient, admin: AuthUser, user_id: str
):
    response = await client.patch(
        f"/users/{user_id}/role", json={"role": "USER"}, headers=admin.headers
    )

    assert_error(response, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("new_role", [RoleName.MANAGER, RoleName.USER])
async def test_the_last_admin_cannot_demote_themselves(
    client: AsyncClient, db_session: AsyncSession, admin: AuthUser, new_role: RoleName
):
    response = await client.patch(
        f"/users/{admin.id}/role", json={"role": new_role}, headers=admin.headers
    )

    assert_error(response, 409, "LAST_ADMIN")
    assert await _role_in_db(db_session, admin.id) == RoleName.ADMIN


async def test_an_admin_can_demote_themselves_when_another_admin_exists(
    client: AsyncClient, db_session: AsyncSession, admin: AuthUser, make_user
):
    await make_user(RoleName.ADMIN)

    response = await client.patch(
        f"/users/{admin.id}/role", json={"role": "USER"}, headers=admin.headers
    )

    assert response.status_code == 200, response.text
    assert await _role_in_db(db_session, admin.id) == RoleName.USER


async def test_an_admin_can_demote_another_admin_but_not_the_last_one(
    client: AsyncClient, db_session: AsyncSession, admin: AuthUser, make_user
):
    second_admin = await make_user(RoleName.ADMIN)

    first = await client.patch(
        f"/users/{second_admin.id}/role", json={"role": "USER"}, headers=admin.headers
    )
    last = await client.patch(
        f"/users/{admin.id}/role", json={"role": "USER"}, headers=admin.headers
    )

    assert first.status_code == 200, first.text
    assert_error(last, 409, "LAST_ADMIN")
    assert await _role_in_db(db_session, admin.id) == RoleName.ADMIN


async def test_a_demoted_admin_loses_admin_rights_immediately(
    client: AsyncClient, admin: AuthUser, make_user
):
    second_admin = await make_user(RoleName.ADMIN)
    await client.patch(
        f"/users/{second_admin.id}/role", json={"role": "USER"}, headers=admin.headers
    )

    response = await client.patch(
        f"/users/{admin.id}/role", json={"role": "USER"}, headers=second_admin.headers
    )

    assert_error(response, 403, "FORBIDDEN")
