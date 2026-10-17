"""PATCH /tasks/{id}/assign."""

import pytest
from httpx import AsyncClient

from app.models import RoleName
from tests.helpers import (
    ACTOR_ROLES,
    VISIBLE,
    AuthUser,
    assert_error,
    matrix,
    matrix_id,
)


def _may_assign(actor: str, task_key: str) -> bool:
    # USER never; ADMIN always; MANAGER only on tasks they created or hold.
    return ACTOR_ROLES[actor] != RoleName.USER and task_key in VISIBLE[actor]


@pytest.mark.parametrize(
    ("actor", "task_key", "allowed"), matrix(_may_assign), ids=matrix_id
)
async def test_assign_permission_matrix(
    client: AsyncClient,
    people: dict[str, AuthUser],
    scenario: dict[str, int],
    fetch_task,
    actor: str,
    task_key: str,
    allowed: bool,
):
    task_id = scenario[task_key]
    before = (await fetch_task(task_id)).assigned_to
    new_assignee = people["other_user"].id

    response = await client.patch(
        f"/tasks/{task_id}/assign",
        json={"assigned_to": new_assignee},
        headers=people[actor].headers,
    )

    if allowed:
        assert response.status_code == 200, response.text
        assert response.json()["assigned_to"] == new_assignee
        assert (await fetch_task(task_id)).assigned_to == new_assignee
    else:
        assert_error(response, 403, "FORBIDDEN")
        assert (await fetch_task(task_id)).assigned_to == before


async def test_assign_returns_the_full_updated_task(
    client: AsyncClient, make_task, manager: AuthUser, user: AuthUser
):
    task = await make_task(created_by=manager, title="Report")

    response = await client.patch(
        f"/tasks/{task.id}/assign",
        json={"assigned_to": user.id},
        headers=manager.headers,
    )

    body = response.json()
    assert body["id"] == task.id
    assert body["title"] == "Report"
    assert body["assigned_to"] == user.id
    assert body["created_by"] == manager.id
    assert body["status"] == "PENDING"


async def test_assign_null_unassigns_the_task(
    client: AsyncClient, make_task, fetch_task, admin: AuthUser, user: AuthUser
):
    task = await make_task(created_by=admin, assigned_to=user)

    response = await client.patch(
        f"/tasks/{task.id}/assign", json={"assigned_to": None}, headers=admin.headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["assigned_to"] is None
    assert (await fetch_task(task.id)).assigned_to is None


async def test_assigning_a_task_makes_it_visible_to_the_new_assignee(
    client: AsyncClient, make_task, manager: AuthUser, user: AuthUser
):
    task = await make_task(created_by=manager)
    assert (
        await client.get(f"/tasks/{task.id}", headers=user.headers)
    ).status_code == 403

    await client.patch(
        f"/tasks/{task.id}/assign",
        json={"assigned_to": user.id},
        headers=manager.headers,
    )

    assert (
        await client.get(f"/tasks/{task.id}", headers=user.headers)
    ).status_code == 200


async def test_reassigning_a_task_away_revokes_the_previous_assignees_access(
    client: AsyncClient,
    make_task,
    admin: AuthUser,
    user: AuthUser,
    other_user: AuthUser,
):
    task = await make_task(created_by=admin, assigned_to=user)

    await client.patch(
        f"/tasks/{task.id}/assign",
        json={"assigned_to": other_user.id},
        headers=admin.headers,
    )

    response = await client.get(f"/tasks/{task.id}", headers=user.headers)
    assert_error(response, 403, "FORBIDDEN")


async def test_a_manager_assigned_to_a_task_may_reassign_it(
    client: AsyncClient,
    make_task,
    other_manager: AuthUser,
    manager: AuthUser,
    user: AuthUser,
):
    task = await make_task(created_by=other_manager, assigned_to=manager)

    response = await client.patch(
        f"/tasks/{task.id}/assign",
        json={"assigned_to": user.id},
        headers=manager.headers,
    )

    assert response.status_code == 200, response.text


async def test_assign_to_an_unknown_user_is_rejected_and_changes_nothing(
    client: AsyncClient, make_task, fetch_task, admin: AuthUser, user: AuthUser
):
    task = await make_task(created_by=admin, assigned_to=user)

    response = await client.patch(
        f"/tasks/{task.id}/assign",
        json={"assigned_to": 999_999},
        headers=admin.headers,
    )

    assert_error(response, 422, "ASSIGNEE_NOT_FOUND")
    assert (await fetch_task(task.id)).assigned_to == user.id


@pytest.mark.parametrize("actor", ["admin", "manager"])
async def test_assign_on_a_missing_task_returns_404(
    client: AsyncClient, people: dict[str, AuthUser], actor: str
):
    response = await client.patch(
        "/tasks/999999/assign",
        json={"assigned_to": people["user"].id},
        headers=people[actor].headers,
    )

    assert_error(response, 404, "NOT_FOUND")


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing-assigned_to"),
        pytest.param({"assigned_to": 0}, id="non-positive-id"),
        pytest.param({"assigned_to": "someone"}, id="non-integer-id"),
        pytest.param({"assigned_to": None, "status": "COMPLETED"}, id="extra-field"),
    ],
)
async def test_assign_rejects_invalid_payloads(
    client: AsyncClient, make_task, admin: AuthUser, payload: dict
):
    task = await make_task(created_by=admin)

    response = await client.patch(
        f"/tasks/{task.id}/assign", json=payload, headers=admin.headers
    )

    assert_error(response, 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------- #
# Order of checks: 401 -> role 403 -> 404 -> permission 403 -> 422
# --------------------------------------------------------------------------- #
async def test_user_role_is_rejected_before_the_task_is_looked_up(
    client: AsyncClient, user: AuthUser
):
    response = await client.patch(
        "/tasks/999999/assign", json={"assigned_to": None}, headers=user.headers
    )

    assert_error(response, 403, "FORBIDDEN")


async def test_missing_task_is_reported_before_an_unknown_assignee(
    client: AsyncClient, admin: AuthUser
):
    response = await client.patch(
        "/tasks/999999/assign", json={"assigned_to": 999_999}, headers=admin.headers
    )

    assert_error(response, 404, "NOT_FOUND")


async def test_lack_of_permission_is_reported_before_an_unknown_assignee(
    client: AsyncClient, make_task, other_manager: AuthUser, manager: AuthUser
):
    task = await make_task(created_by=other_manager)

    response = await client.patch(
        f"/tasks/{task.id}/assign",
        json={"assigned_to": 999_999},
        headers=manager.headers,
    )

    assert_error(response, 403, "FORBIDDEN")
