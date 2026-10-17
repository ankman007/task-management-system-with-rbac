"""Shared test infrastructure.

Database strategy
-----------------
Tests run against a real, separate PostgreSQL database (``TEST_DATABASE_URL``),
never SQLite, so enum types, constraints and asyncpg behaviour match production.
The schema is dropped and recreated once per session and the three roles are
seeded (committed) once.

Isolation: "join an external transaction"
-----------------------------------------
Each test opens one connection and begins a transaction on it. Every
``AsyncSession`` in that test (the fixtures' session and one fresh session per
HTTP request) is bound to that connection with
``join_transaction_mode="create_savepoint"``, so the services' own
``await session.commit()`` only releases a SAVEPOINT. When the test ends the outer
transaction is rolled back and the database is exactly as the session fixture
left it.

This was chosen over ``TRUNCATE ... RESTART IDENTITY CASCADE`` because a rollback
is close to free, while a TRUNCATE takes an ACCESS EXCLUSIVE lock and rewrites
the tables after every test. The one trade-off is that Postgres' ``now()`` is
frozen at the start of the outer transaction, so rows created in one test share a
``created_at``; tests that depend on ordering set ``created_at`` explicitly via
``make_task``.
"""

import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://task_user:task_password@localhost:15432/task_db_test",
)
# Must happen before any `app` import: settings are read at import time.
# DATABASE_URL is forced (not defaulted) so a test run can never touch a dev DB.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("ENVIRONMENT", "test")

from collections.abc import AsyncIterator, Awaitable, Callable  # noqa: E402
from datetime import date, datetime  # noqa: E402
from itertools import count  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import make_url, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, RoleName, Task, TaskStatus, User  # noqa: E402
from tests.helpers import (  # noqa: E402
    DEFAULT_PASSWORD,
    SCENARIO,
    AuthUser,
    auth_headers,
)


# --------------------------------------------------------------------------- #
# Database lifecycle
# --------------------------------------------------------------------------- #
async def _ensure_database_exists(url: str) -> None:
    """Create the test database on first use (CREATE DATABASE needs AUTOCOMMIT)."""
    target = make_url(url)
    maintenance = create_async_engine(
        target.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with maintenance.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        await maintenance.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    await _ensure_database_exists(TEST_DATABASE_URL)
    # NullPool: no connection outlives the test that opened it.
    test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            Role.__table__.insert(), [{"name": role} for role in RoleName]
        )
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def role_ids(engine: AsyncEngine) -> dict[RoleName, int]:
    async with engine.connect() as conn:
        rows = await conn.execute(select(Role.name, Role.id))
        return {name: role_id for name, role_id in rows}


@pytest.fixture(scope="session")
def password_hash() -> str:
    # bcrypt is deliberately slow; hash once and share it across factory users.
    return hash_password(DEFAULT_PASSWORD)


@pytest_asyncio.fixture
async def connection(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


def _session_on(conn: AsyncConnection) -> AsyncSession:
    return AsyncSession(
        bind=conn,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def db_session(connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """Session for arranging data and asserting on it directly."""
    async with _session_on(connection) as session:
        yield session


@pytest_asyncio.fixture
async def client(connection: AsyncConnection) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        # A fresh session per request (like production), so no identity-map state
        # leaks between requests; all of them share the test's transaction.
        async with _session_on(connection) as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            yield http_client
    finally:
        app.dependency_overrides.pop(get_db, None)


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
MakeUser = Callable[..., Awaitable[AuthUser]]

# The five standard actors: fixture name -> (role, email).
ACTOR_SPECS: dict[str, tuple[RoleName, str]] = {
    "admin": (RoleName.ADMIN, "admin@example.com"),
    "manager": (RoleName.MANAGER, "manager@example.com"),
    "other_manager": (RoleName.MANAGER, "other.manager@example.com"),
    "user": (RoleName.USER, "user@example.com"),
    "other_user": (RoleName.USER, "other.user@example.com"),
}


def _to_auth_user(user: User, role: RoleName) -> AuthUser:
    token = create_access_token(user.id, role.value)
    return AuthUser(user.id, user.email, role, token, auth_headers(token))


@pytest.fixture
def make_user(
    db_session: AsyncSession, role_ids: dict[RoleName, int], password_hash: str
) -> MakeUser:
    """Insert a user directly and mint a token for them (bypasses /auth)."""
    sequence = count(1)

    async def _make_user(role: RoleName = RoleName.USER, email: str | None = None):
        email = email or f"{role.lower()}{next(sequence)}@example.com"
        user = User(email=email, hashed_password=password_hash, role_id=role_ids[role])
        db_session.add(user)
        await db_session.commit()
        return _to_auth_user(user, role)

    return _make_user


@pytest_asyncio.fixture
async def people(
    db_session: AsyncSession, role_ids: dict[RoleName, int], password_hash: str
) -> dict[str, AuthUser]:
    """All five actors by fixture name, for parametrized permission matrices.

    Inserted in a single flush (one round trip), which keeps per-test setup
    cheap; the individual actor fixtures below are views onto this dict.
    """
    users = {
        name: User(email=email, hashed_password=password_hash, role_id=role_ids[role])
        for name, (role, email) in ACTOR_SPECS.items()
    }
    db_session.add_all(users.values())
    await db_session.commit()
    return {
        name: _to_auth_user(users[name], role)
        for name, (role, _email) in ACTOR_SPECS.items()
    }


@pytest.fixture
def admin(people: dict[str, AuthUser]) -> AuthUser:
    return people["admin"]


@pytest.fixture
def manager(people: dict[str, AuthUser]) -> AuthUser:
    return people["manager"]


@pytest.fixture
def other_manager(people: dict[str, AuthUser]) -> AuthUser:
    return people["other_manager"]


@pytest.fixture
def user(people: dict[str, AuthUser]) -> AuthUser:
    return people["user"]


@pytest.fixture
def other_user(people: dict[str, AuthUser]) -> AuthUser:
    return people["other_user"]


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
def _user_id(value: AuthUser | int | None) -> int | None:
    return value.id if isinstance(value, AuthUser) else value


MakeTask = Callable[..., Awaitable[Task]]


@pytest.fixture
def make_task(db_session: AsyncSession) -> MakeTask:
    """Insert a task directly, bypassing the API and its permission rules."""
    sequence = count(1)

    async def _make_task(
        created_by: AuthUser | int,
        assigned_to: AuthUser | int | None = None,
        status: TaskStatus = TaskStatus.PENDING,
        title: str | None = None,
        description: str | None = None,
        due_date: date | None = None,
        created_at: datetime | None = None,
    ) -> Task:
        task = Task(
            title=title or f"Task {next(sequence)}",
            description=description,
            status=status,
            due_date=due_date,
            created_by=_user_id(created_by),
            assigned_to=_user_id(assigned_to),
        )
        if created_at is not None:
            task.created_at = created_at
            task.updated_at = created_at
        db_session.add(task)
        # Server defaults (id, created_at, ...) come back via INSERT ... RETURNING.
        await db_session.commit()
        return task

    return _make_task


@pytest.fixture
def fetch_task(db_session: AsyncSession) -> Callable[[int], Awaitable[Task | None]]:
    """Read a task's current state from the database, bypassing the identity map."""

    async def _fetch(task_id: int) -> Task | None:
        return await db_session.get(Task, task_id, populate_existing=True)

    return _fetch


@pytest_asyncio.fixture
async def scenario(
    db_session: AsyncSession, people: dict[str, AuthUser]
) -> dict[str, int]:
    """Create one task per `SCENARIO` entry (titled by its key); return ids by key."""
    tasks = {
        key: Task(
            title=key,
            created_by=people[creator].id,
            assigned_to=people[assignee].id if assignee else None,
        )
        for key, (creator, assignee) in SCENARIO.items()
    }
    db_session.add_all(tasks.values())
    await db_session.commit()
    return {key: task.id for key, task in tasks.items()}
