"""PATCH /tasks/{id}/status: permissions and the status state machine."""

import pytest
from httpx import AsyncClient

from app.models import TaskStatus
from tests.helpers import VISIBLE, AuthUser, assert_error, matrix, matrix_id

PENDING, IN_PROGRESS, COMPLETED = (
    TaskStatus.PENDING,
    TaskStatus.IN_PROGRESS,
    TaskStatus.COMPLETED,
)

ALLOWED_TRANSITIONS = {
    PENDING: {IN_PROGRESS, COMPLETED},
    IN_PROGRESS: {PENDING, COMPLETED},
    COMPLETED: {IN_PROGRESS},
}

# Every (from, to) pair, including "no-op" transitions to the same status.
TRANSITION_TABLE = [
    pytest.param(
        current,
        target,
        target in ALLOWED_TRANSITIONS[current],
        id=f"{current}->{target}",
    )
    for current in TaskStatus
    for target in TaskStatus
]


@pytest.mark.parametrize(("current", "target", "allowed"), TRANSITION_TABLE)
async def test_status_transition_table(
    client: AsyncClient,
    make_task,
    fetch_task,
    admin: AuthUser,
    current: TaskStatus,
    target: TaskStatus,
    allowed: bool,
):
    task = await make_task(created_by=admin, status=current)

    response = await client.patch(
        f"/tasks/{task.id}/status", json={"status": target}, headers=admin.headers
    )

    if allowed:
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target
        assert (await fetch_task(task.id)).status == target
    else:
        assert_error(response, 400, "INVALID_STATUS_TRANSITION")
        assert (await fetch_task(task.id)).status == current


async def test_a_completed_task_cannot_go_straight_back_to_pending(
    client: AsyncClient, make_task, admin: AuthUser
):
    task = await make_task(created_by=admin, status=COMPLETED)

    response = await client.patch(
        f"/tasks/{task.id}/status", json={"status": "PENDING"}, headers=admin.headers
    )

    assert_error(response, 400, "INVALID_STATUS_TRANSITION")


async def test_a_task_can_be_reopened_and_completed_again(
    client: AsyncClient, make_task, admin: AuthUser
):
    task = await make_task(created_by=admin)

    statuses = []
    for target in (IN_PROGRESS, COMPLETED, IN_PROGRESS, PENDING, COMPLETED):
        response = await client.patch(
            f"/tasks/{task.id}/status", json={"status": target}, headers=admin.headers
        )
        statuses.append(response.json()["status"])

    assert statuses == [
        "IN_PROGRESS",
        "COMPLETED",
        "IN_PROGRESS",
        "PENDING",
        "COMPLETED",
    ]


# ADMIN: any task. MANAGER: created or assigned. USER: assigned. That is exactly
# the visibility rule.
@pytest.mark.parametrize(
    ("actor", "task_key", "allowed"),
    matrix(lambda actor, key: key in VISIBLE[actor]),
    ids=matrix_id,
)
async def test_status_update_permission_matrix(
    client: AsyncClient,
    people: dict[str, AuthUser],
    scenario: dict[str, int],
    fetch_task,
    actor: str,
    task_key: str,
    allowed: bool,
):
    task_id = scenario[task_key]

    response = await client.patch(
        f"/tasks/{task_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=people[actor].headers,
    )

    if allowed:
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "IN_PROGRESS"
        assert (await fetch_task(task_id)).status == IN_PROGRESS
    else:
        assert_error(response, 403, "FORBIDDEN")
        assert (await fetch_task(task_id)).status == PENDING


async def test_status_update_returns_the_full_task(
    client: AsyncClient, make_task, manager: AuthUser, user: AuthUser
):
    task = await make_task(created_by=manager, assigned_to=user, title="Fix bug")

    response = await client.patch(
        f"/tasks/{task.id}/status", json={"status": "COMPLETED"}, headers=user.headers
    )

    body = response.json()
    assert body["id"] == task.id
    assert body["title"] == "Fix bug"
    assert body["assigned_to"] == user.id
    assert body["created_by"] == manager.id
    assert body["status"] == "COMPLETED"


@pytest.mark.parametrize("actor", ["admin", "manager", "user"])
async def test_status_update_on_a_missing_task_returns_404(
    client: AsyncClient, people: dict[str, AuthUser], actor: str
):
    response = await client.patch(
        "/tasks/999999/status",
        json={"status": "IN_PROGRESS"},
        headers=people[actor].headers,
    )

    assert_error(response, 404, "NOT_FOUND")


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing-status"),
        pytest.param({"status": "DONE"}, id="unknown-status"),
        pytest.param({"status": "pending"}, id="wrong-case"),
        pytest.param({"status": None}, id="null-status"),
        pytest.param({"status": "COMPLETED", "title": "x"}, id="extra-field"),
    ],
)
async def test_status_update_rejects_invalid_payloads(
    client: AsyncClient, make_task, admin: AuthUser, payload: dict
):
    task = await make_task(created_by=admin)

    response = await client.patch(
        f"/tasks/{task.id}/status", json=payload, headers=admin.headers
    )

    assert_error(response, 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------- #
# Order of checks: 404 -> permission 403 -> 400
# --------------------------------------------------------------------------- #
async def test_lack_of_permission_is_reported_before_an_invalid_transition(
    client: AsyncClient, make_task, admin: AuthUser, user: AuthUser
):
    task = await make_task(created_by=admin, status=COMPLETED)  # not assigned

    response = await client.patch(
        f"/tasks/{task.id}/status", json={"status": "PENDING"}, headers=user.headers
    )

    assert_error(response, 403, "FORBIDDEN")


async def test_permitted_user_gets_400_for_an_invalid_transition(
    client: AsyncClient, make_task, admin: AuthUser, user: AuthUser
):
    task = await make_task(created_by=admin, assigned_to=user, status=COMPLETED)

    response = await client.patch(
        f"/tasks/{task.id}/status", json={"status": "PENDING"}, headers=user.headers
    )

    assert_error(response, 400, "INVALID_STATUS_TRANSITION")
