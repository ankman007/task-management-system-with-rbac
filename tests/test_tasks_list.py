"""GET /tasks: visibility per role, pagination, ordering and status filter."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.models import TaskStatus
from tests.helpers import VISIBLE, AuthUser, assert_error, matrix, matrix_id


@pytest.mark.parametrize("actor", list(VISIBLE))
async def test_list_returns_exactly_the_tasks_visible_to_the_caller(
    client: AsyncClient,
    people: dict[str, AuthUser],
    scenario: dict[str, int],
    actor: str,
):
    response = await client.get("/tasks", headers=people[actor].headers)

    assert response.status_code == 200, response.text
    body = response.json()
    expected_ids = {scenario[key] for key in VISIBLE[actor]}
    assert {item["id"] for item in body["items"]} == expected_ids
    assert body["total"] == len(expected_ids)


async def test_list_is_empty_for_a_user_with_no_assigned_tasks(
    client: AsyncClient, make_task, admin: AuthUser, user: AuthUser
):
    await make_task(created_by=admin)

    response = await client.get("/tasks", headers=user.headers)

    body = response.json()
    assert body == {"items": [], "total": 0, "page": 1, "size": 20, "pages": 0}


async def test_list_orders_tasks_newest_first(
    client: AsyncClient, make_task, admin: AuthUser
):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # Inserted out of order so neither id nor insertion order matches recency.
    middle = await make_task(created_by=admin, created_at=base + timedelta(hours=1))
    newest = await make_task(created_by=admin, created_at=base + timedelta(hours=2))
    oldest = await make_task(created_by=admin, created_at=base)

    response = await client.get("/tasks", headers=admin.headers)

    assert [t["id"] for t in response.json()["items"]] == [
        newest.id,
        middle.id,
        oldest.id,
    ]


async def test_list_paginates_with_accurate_totals(
    client: AsyncClient, make_task, admin: AuthUser
):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    tasks = [
        await make_task(created_by=admin, created_at=base + timedelta(minutes=i))
        for i in range(25)
    ]
    newest_first = [t.id for t in reversed(tasks)]

    pages = [
        (await client.get(f"/tasks?page={n}&size=10", headers=admin.headers)).json()
        for n in (1, 2, 3, 4)
    ]

    assert [len(p["items"]) for p in pages] == [10, 10, 5, 0]
    assert all(p["total"] == 25 and p["pages"] == 3 for p in pages)
    assert [p["page"] for p in pages] == [1, 2, 3, 4]
    assert all(p["size"] == 10 for p in pages)
    seen = [item["id"] for p in pages for item in p["items"]]
    assert seen == newest_first  # no gaps, no duplicates, stable order


async def test_list_uses_a_default_page_size_of_20(
    client: AsyncClient, make_task, admin: AuthUser
):
    for _ in range(21):
        await make_task(created_by=admin)

    body = (await client.get("/tasks", headers=admin.headers)).json()

    assert body["size"] == 20
    assert len(body["items"]) == 20
    assert body["total"] == 21
    assert body["pages"] == 2


async def test_pagination_totals_count_only_visible_tasks(
    client: AsyncClient, make_task, admin: AuthUser, user: AuthUser
):
    for i in range(6):
        await make_task(created_by=admin, assigned_to=user if i % 2 else None)

    body = (await client.get("/tasks?size=2", headers=user.headers)).json()

    assert body["total"] == 3
    assert body["pages"] == 2


@pytest.mark.parametrize(
    "query",
    ["page=0", "page=-1", "size=0", "size=101", "page=x", "status=DONE", "status="],
)
async def test_list_rejects_invalid_query_parameters(
    client: AsyncClient, admin: AuthUser, query: str
):
    response = await client.get(f"/tasks?{query}", headers=admin.headers)

    assert_error(response, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("status", list(TaskStatus))
async def test_status_filter_returns_only_tasks_in_that_status(
    client: AsyncClient, make_task, admin: AuthUser, status: TaskStatus
):
    ids_by_status = {
        s: {(await make_task(created_by=admin, status=s)).id for _ in range(2)}
        for s in TaskStatus
    }

    response = await client.get(f"/tasks?status={status.value}", headers=admin.headers)

    body = response.json()
    assert {item["id"] for item in body["items"]} == ids_by_status[status]
    assert {item["status"] for item in body["items"]} == {status.value}
    assert body["total"] == 2


async def test_status_filter_is_combined_with_visibility(
    client: AsyncClient, make_task, admin: AuthUser, user: AuthUser
):
    mine = await make_task(
        created_by=admin, assigned_to=user, status=TaskStatus.COMPLETED
    )
    await make_task(created_by=admin, assigned_to=user, status=TaskStatus.PENDING)
    await make_task(created_by=admin, status=TaskStatus.COMPLETED)  # not visible

    response = await client.get("/tasks?status=COMPLETED", headers=user.headers)

    body = response.json()
    assert [item["id"] for item in body["items"]] == [mine.id]
    assert body["total"] == 1


# --------------------------------------------------------------------------- #
# GET /tasks/{id}
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("actor", "task_key", "allowed"),
    matrix(lambda actor, key: key in VISIBLE[actor]),
    ids=matrix_id,
)
async def test_get_task_is_allowed_only_when_the_task_is_visible(
    client: AsyncClient,
    people: dict[str, AuthUser],
    scenario: dict[str, int],
    actor: str,
    task_key: str,
    allowed: bool,
):
    task_id = scenario[task_key]

    response = await client.get(f"/tasks/{task_id}", headers=people[actor].headers)

    if allowed:
        assert response.status_code == 200, response.text
        assert response.json()["id"] == task_id
        assert response.json()["title"] == task_key
    else:
        assert_error(response, 403, "FORBIDDEN")


@pytest.mark.parametrize("actor", ["admin", "manager", "user"])
async def test_get_missing_task_returns_404_for_every_role(
    client: AsyncClient, people: dict[str, AuthUser], actor: str
):
    response = await client.get("/tasks/999999", headers=people[actor].headers)

    assert_error(response, 404, "NOT_FOUND")


async def test_get_task_with_a_non_integer_id_is_a_validation_error(
    client: AsyncClient, admin: AuthUser
):
    response = await client.get("/tasks/abc", headers=admin.headers)

    assert_error(response, 422, "VALIDATION_ERROR")
