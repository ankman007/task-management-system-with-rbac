"""Concurrent writes, run on separate database connections.

The rest of the suite shares one connection per test (see conftest.py), which
can't show what happens when two requests race. These tests commit real rows,
send requests concurrently with each request on its own connection and
transaction (as in production), and delete their rows afterwards.
"""

import asyncio
from collections.abc import AsyncIterator
from itertools import count

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.deps import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import RoleName, Task, TaskStatus, User
from tests.helpers import auth_headers

ROUNDS = 5
_emails = count(1)


@pytest_asyncio.fixture
async def committed(
    engine: AsyncEngine, role_ids: dict[RoleName, int], password_hash: str
) -> AsyncIterator["Committed"]:
    helper = Committed(engine, role_ids, password_hash)
    try:
        yield helper
    finally:
        await helper.cleanup()


class Committed:
    """Creates committed rows and removes them again."""

    def __init__(self, engine: AsyncEngine, role_ids, password_hash: str) -> None:
        self.engine = engine
        self.role_ids = role_ids
        self.password_hash = password_hash
        self.user_ids: list[int] = []

    def session(self) -> AsyncSession:
        return AsyncSession(self.engine, expire_on_commit=False)

    async def user(self, role: RoleName) -> tuple[User, dict[str, str]]:
        async with self.session() as session:
            user = User(
                email=f"race{next(_emails)}@example.com",
                hashed_password=self.password_hash,
                role_id=self.role_ids[role],
            )
            session.add(user)
            await session.commit()
        self.user_ids.append(user.id)
        return user, auth_headers(create_access_token(user.id, role.value))

    async def task(self, created_by: User, status: TaskStatus) -> int:
        async with self.session() as session:
            task = Task(title="Race", created_by=created_by.id, status=status)
            session.add(task)
            await session.commit()
            return task.id

    async def set_status(self, task_id: int, status: TaskStatus) -> None:
        async with self.session() as session:
            task = await session.get(Task, task_id)
            task.status = status
            await session.commit()

    async def status_of(self, task_id: int) -> TaskStatus:
        async with self.session() as session:
            return await session.scalar(select(Task.status).where(Task.id == task_id))

    async def role_of(self, user_id: int) -> RoleName:
        async with self.session() as session:
            user = await session.get(User, user_id)
            return user.role.name

    async def cleanup(self) -> None:
        if not self.user_ids:
            return
        async with self.session() as session:
            await session.execute(
                delete(Task).where(Task.created_by.in_(self.user_ids))
            )
            await session.execute(delete(User).where(User.id.in_(self.user_ids)))
            await session.commit()


@pytest_asyncio.fixture
async def racing_client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """A client whose every request gets its own connection and transaction."""

    async def _independent_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = _independent_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_racing_status_updates_never_produce_an_invalid_history(
    racing_client: AsyncClient, committed: Committed
):
    """IN_PROGRESS -> COMPLETED races IN_PROGRESS -> PENDING.

    Run one after the other, the only valid outcomes end in COMPLETED: either
    PENDING then COMPLETED (both succeed), or COMPLETED first and the move back
    to PENDING is rejected. Without row locking, both requests could read
    IN_PROGRESS and the task would end PENDING after being COMPLETED.
    """
    admin, headers = await committed.user(RoleName.ADMIN)
    task_id = await committed.task(admin, TaskStatus.IN_PROGRESS)

    for _ in range(ROUNDS):
        await committed.set_status(task_id, TaskStatus.IN_PROGRESS)

        to_completed, to_pending = await asyncio.gather(
            racing_client.patch(
                f"/tasks/{task_id}/status",
                json={"status": "COMPLETED"},
                headers=headers,
            ),
            racing_client.patch(
                f"/tasks/{task_id}/status", json={"status": "PENDING"}, headers=headers
            ),
        )

        assert to_completed.status_code == 200, to_completed.text
        assert to_pending.status_code in (200, 400), to_pending.text
        assert await committed.status_of(task_id) == TaskStatus.COMPLETED


@pytest.mark.parametrize(
    "bystander_admin", [False, True], ids=["two-admins", "three-admins"]
)
async def test_two_admins_demoting_each_other_never_both_succeed(
    racing_client: AsyncClient, committed: Committed, bystander_admin: bool
):
    """Each admin demotes the other at the same moment.

    With only two admins, the second request would remove the last admin
    (409). With a third admin around, it comes from someone who is no longer
    an admin (403). Either way exactly one demotion happens.
    """
    if await _committed_admin_count(committed):
        pytest.skip("another committed ADMIN exists; the race would be moot")

    for _ in range(ROUNDS):
        first, first_headers = await committed.user(RoleName.ADMIN)
        second, second_headers = await committed.user(RoleName.ADMIN)
        if bystander_admin:
            await committed.user(RoleName.ADMIN)

        responses = await asyncio.gather(
            racing_client.patch(
                f"/users/{second.id}/role", json={"role": "USER"}, headers=first_headers
            ),
            racing_client.patch(
                f"/users/{first.id}/role", json={"role": "USER"}, headers=second_headers
            ),
        )

        statuses = sorted(r.status_code for r in responses)
        texts = [r.text for r in responses]
        assert statuses[0] == 200, texts
        # A request that loses the race either finds its target is the last
        # admin (409) or finds its caller has already been demoted (403).
        assert statuses[1] in (403, 409), texts
        if bystander_admin:
            assert statuses[1] == 403, texts
        roles = {await committed.role_of(first.id), await committed.role_of(second.id)}
        assert roles == {RoleName.ADMIN, RoleName.USER}

        await committed.cleanup()
        committed.user_ids.clear()


async def _committed_admin_count(committed: Committed) -> int:
    async with committed.session() as session:
        ids = await session.scalars(
            select(User.id).where(User.role_id == committed.role_ids[RoleName.ADMIN])
        )
        return len(ids.all())
