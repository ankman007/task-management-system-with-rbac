"""Plain helpers shared by the tests (fixtures live in conftest.py)."""

from dataclasses import dataclass, field

from httpx import Response

from app.models import RoleName

# Shared by every factory-made user, so tests that need to log in know it.
DEFAULT_PASSWORD = "Password123"


@dataclass(frozen=True)
class AuthUser:
    id: int
    email: str
    role: RoleName
    token: str
    headers: dict[str, str] = field(repr=False)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_error(response: Response, status_code: int, code: str | None = None) -> dict:
    """Assert the response is an error in the standard envelope; return its body."""
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"error"}, body
    assert set(body["error"]) == {"code", "message", "details"}, body
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]
    if code is not None:
        assert body["error"]["code"] == code, body
    return body["error"]


# --------------------------------------------------------------------------- #
# Permission scenario shared by the task tests
# --------------------------------------------------------------------------- #
# (creator, assignee) of each task, chosen so that every actor has tasks they
# created, tasks assigned to them and tasks unrelated to them.
SCENARIO: dict[str, tuple[str, str | None]] = {
    "manager_to_user": ("manager", "user"),
    "manager_unassigned": ("manager", None),
    "other_manager_to_manager": ("other_manager", "manager"),
    "other_manager_to_other_user": ("other_manager", "other_user"),
    "admin_to_user": ("admin", "user"),
    "admin_unassigned": ("admin", None),
}

# ADMIN sees everything; MANAGER sees tasks they created or are assigned to;
# USER sees only tasks assigned to them.
VISIBLE: dict[str, set[str]] = {
    "admin": set(SCENARIO),
    "manager": {"manager_to_user", "manager_unassigned", "other_manager_to_manager"},
    "other_manager": {"other_manager_to_manager", "other_manager_to_other_user"},
    "user": {"manager_to_user", "admin_to_user"},
    "other_user": {"other_manager_to_other_user"},
}

ACTORS = list(VISIBLE)
ACTOR_ROLES: dict[str, RoleName] = {
    "admin": RoleName.ADMIN,
    "manager": RoleName.MANAGER,
    "other_manager": RoleName.MANAGER,
    "user": RoleName.USER,
    "other_user": RoleName.USER,
}


def matrix(is_allowed) -> list[tuple[str, str, bool]]:
    """Every (actor, task) cell of the scenario with whether the action is allowed."""
    return [
        (actor, key, is_allowed(actor, key)) for actor in ACTORS for key in SCENARIO
    ]


def matrix_id(value) -> str | None:
    if isinstance(value, bool):
        return "allowed" if value else "forbidden"
    return None
