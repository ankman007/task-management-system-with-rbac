"""POST /tasks."""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.models import Task
from tests.helpers import AuthUser, assert_error

TASK_FIELDS = {
    "id",
    "title",
    "description",
    "status",
    "due_date",
    "assigned_to",
    "created_by",
    "created_at",
    "updated_at",
}


@pytest.mark.parametrize(
    ("actor", "expected_status"),
    [("admin", 201), ("manager", 201), ("user", 403)],
)
async def test_only_admins_and_managers_can_create_tasks(
    client: AsyncClient, people: dict[str, AuthUser], actor: str, expected_status: int
):
    response = await client.post(
        "/tasks", json={"title": "Ship it"}, headers=people[actor].headers
    )

    if expected_status == 403:
        assert_error(response, 403, "FORBIDDEN")
    else:
        assert response.status_code == 201, response.text


async def test_create_task_returns_the_full_task_with_pending_status(
    client: AsyncClient, manager: AuthUser, user: AuthUser
):
    due = date.today() + timedelta(days=7)
    payload = {
        "title": "Write the report",
        "description": "Quarterly numbers",
        "due_date": due.isoformat(),
        "assigned_to": user.id,
    }

    response = await client.post("/tasks", json=payload, headers=manager.headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == TASK_FIELDS
    assert body["title"] == "Write the report"
    assert body["description"] == "Quarterly numbers"
    assert body["status"] == "PENDING"
    assert body["due_date"] == due.isoformat()
    assert body["assigned_to"] == user.id
    assert body["created_by"] == manager.id
    assert body["created_at"]
    assert body["updated_at"]


async def test_create_task_persists_it_with_the_caller_as_creator(
    client: AsyncClient,
    admin: AuthUser,
    fetch_task: Callable[[int], Awaitable[Task | None]],
):
    response = await client.post(
        "/tasks", json={"title": "Persist me"}, headers=admin.headers
    )

    stored = await fetch_task(response.json()["id"])
    assert stored is not None
    assert stored.title == "Persist me"
    assert stored.created_by == admin.id
    assert stored.status == "PENDING"


async def test_create_task_with_only_a_title_leaves_optional_fields_null(
    client: AsyncClient, admin: AuthUser
):
    response = await client.post(
        "/tasks", json={"title": "Minimal"}, headers=admin.headers
    )

    body = response.json()
    assert body["description"] is None
    assert body["due_date"] is None
    assert body["assigned_to"] is None


@pytest.mark.parametrize("assignee", ["admin", "manager", "other_manager", "user"])
async def test_a_task_can_be_assigned_to_any_existing_user_on_creation(
    client: AsyncClient, people: dict[str, AuthUser], assignee: str
):
    response = await client.post(
        "/tasks",
        json={"title": "Delegate", "assigned_to": people[assignee].id},
        headers=people["manager"].headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["assigned_to"] == people[assignee].id


async def test_create_task_with_an_unknown_assignee_is_rejected(
    client: AsyncClient, admin: AuthUser
):
    response = await client.post(
        "/tasks",
        json={"title": "Orphan", "assigned_to": 999_999},
        headers=admin.headers,
    )

    assert_error(response, 422, "ASSIGNEE_NOT_FOUND")


@pytest.mark.parametrize("days_from_today", [0, 1, 365])
async def test_due_date_today_or_in_the_future_is_accepted(
    client: AsyncClient, admin: AuthUser, days_from_today: int
):
    due = date.today() + timedelta(days=days_from_today)

    response = await client.post(
        "/tasks",
        json={"title": "Dated", "due_date": due.isoformat()},
        headers=admin.headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["due_date"] == due.isoformat()


@pytest.mark.parametrize(
    ("payload", "failing_field"),
    [
        pytest.param({}, "body.title", id="missing-title"),
        pytest.param({"title": ""}, "body.title", id="empty-title"),
        pytest.param({"title": "   "}, "body.title", id="whitespace-title"),
        pytest.param({"title": "x" * 201}, "body.title", id="title-over-200"),
        pytest.param(
            {
                "title": "Late",
                "due_date": (date.today() - timedelta(days=1)).isoformat(),
            },
            "body.due_date",
            id="due-date-in-the-past",
        ),
        pytest.param(
            {"title": "Bad", "due_date": "next tuesday"}, "body.due_date", id="bad-date"
        ),
        pytest.param({"title": "Bad", "assigned_to": 0}, "body.assigned_to", id="id-0"),
        pytest.param(
            {"title": "Bad", "assigned_to": "abc"}, "body.assigned_to", id="id-not-int"
        ),
        pytest.param(
            # Tasks always start PENDING; status can't be chosen on creation.
            {"title": "Done", "status": "COMPLETED"},
            "body.status",
            id="status-not-allowed",
        ),
        pytest.param({"title": "Me", "created_by": 1}, "body.created_by", id="creator"),
    ],
)
async def test_create_task_rejects_invalid_payloads(
    client: AsyncClient, admin: AuthUser, payload: dict, failing_field: str
):
    response = await client.post("/tasks", json=payload, headers=admin.headers)

    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert failing_field in {item["field"] for item in error["details"]}


async def test_title_of_exactly_200_characters_is_accepted(
    client: AsyncClient, admin: AuthUser
):
    response = await client.post(
        "/tasks", json={"title": "x" * 200}, headers=admin.headers
    )

    assert response.status_code == 201


async def test_role_gate_runs_before_body_validation(
    client: AsyncClient, user: AuthUser
):
    # A USER learns nothing about the payload rules: 403, not 422.
    response = await client.post("/tasks", json={"title": ""}, headers=user.headers)

    assert_error(response, 403, "FORBIDDEN")
