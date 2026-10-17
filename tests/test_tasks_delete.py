"""DELETE /tasks/{id}: ADMIN only."""

import pytest
from httpx import AsyncClient

from tests.helpers import AuthUser, assert_error, matrix, matrix_id


# Being the creator or the assignee does not matter: only ADMIN may delete.
@pytest.mark.parametrize(
    ("actor", "task_key", "allowed"),
    matrix(lambda actor, _key: actor == "admin"),
    ids=matrix_id,
)
async def test_delete_permission_matrix(
    client: AsyncClient,
    people: dict[str, AuthUser],
    scenario: dict[str, int],
    fetch_task,
    actor: str,
    task_key: str,
    allowed: bool,
):
    task_id = scenario[task_key]

    response = await client.delete(f"/tasks/{task_id}", headers=people[actor].headers)

    if allowed:
        assert response.status_code == 204, response.text
        assert response.content == b""
        assert await fetch_task(task_id) is None
    else:
        assert_error(response, 403, "FORBIDDEN")
        assert await fetch_task(task_id) is not None


async def test_deleted_task_is_gone_from_get_and_list(
    client: AsyncClient, make_task, admin: AuthUser
):
    task = await make_task(created_by=admin)
    keep = await make_task(created_by=admin)

    await client.delete(f"/tasks/{task.id}", headers=admin.headers)

    assert_error(
        await client.get(f"/tasks/{task.id}", headers=admin.headers), 404, "NOT_FOUND"
    )
    listing = (await client.get("/tasks", headers=admin.headers)).json()
    assert [t["id"] for t in listing["items"]] == [keep.id]


async def test_deleting_twice_returns_404_the_second_time(
    client: AsyncClient, make_task, admin: AuthUser
):
    task = await make_task(created_by=admin)

    first = await client.delete(f"/tasks/{task.id}", headers=admin.headers)
    second = await client.delete(f"/tasks/{task.id}", headers=admin.headers)

    assert first.status_code == 204
    assert_error(second, 404, "NOT_FOUND")


async def test_admin_deleting_a_missing_task_gets_404(
    client: AsyncClient, admin: AuthUser
):
    response = await client.delete("/tasks/999999", headers=admin.headers)

    assert_error(response, 404, "NOT_FOUND")


@pytest.mark.parametrize("actor", ["manager", "user"])
async def test_non_admins_are_rejected_before_the_task_is_looked_up(
    client: AsyncClient, people: dict[str, AuthUser], actor: str
):
    # 403 even for a missing task: the role gate runs first and leaks nothing.
    response = await client.delete("/tasks/999999", headers=people[actor].headers)

    assert_error(response, 403, "FORBIDDEN")
