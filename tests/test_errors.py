"""Authentication failures and the uniform error envelope."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import create_access_token
from app.models import RoleName
from tests.helpers import AuthUser, assert_error, auth_headers

# Every protected endpoint, with a body that would otherwise be valid, so the
# only reason to fail is authentication.
PROTECTED_ENDPOINTS = [
    ("GET", "/users/me", None),
    ("GET", "/users", None),
    ("GET", "/tasks", None),
    ("POST", "/tasks", {"title": "Write tests"}),
    ("GET", "/tasks/1", None),
    ("PATCH", "/tasks/1/assign", {"assigned_to": None}),
    ("PATCH", "/tasks/1/status", {"status": "IN_PROGRESS"}),
    ("DELETE", "/tasks/1", None),
]
ENDPOINT_IDS = [f"{method} {path}" for method, path, _ in PROTECTED_ENDPOINTS]


def _assert_unauthorized(response) -> None:
    assert_error(response, 401, "UNAUTHORIZED")
    assert response.headers.get("www-authenticate") == "Bearer"


def _sign(claims: dict, key: str = settings.secret_key) -> str:
    return jwt.encode(claims, key, algorithm=settings.jwt_algorithm)


def _claims(user_id: int, **overrides) -> dict:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": "USER",
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


@pytest.mark.parametrize(
    ("method", "path", "body"), PROTECTED_ENDPOINTS, ids=ENDPOINT_IDS
)
async def test_protected_endpoint_without_token_returns_401(
    client: AsyncClient, method: str, path: str, body: dict | None
):
    response = await client.request(method, path, json=body)

    _assert_unauthorized(response)


@pytest.mark.parametrize(
    ("method", "path", "body"), PROTECTED_ENDPOINTS, ids=ENDPOINT_IDS
)
async def test_protected_endpoint_with_garbage_token_returns_401(
    client: AsyncClient, method: str, path: str, body: dict | None
):
    response = await client.request(
        method, path, json=body, headers=auth_headers("not-a-jwt")
    )

    _assert_unauthorized(response)


async def test_expired_token_is_rejected(client: AsyncClient, user: AuthUser):
    expired = create_access_token(
        user.id, user.role.value, expires_delta=timedelta(minutes=-1)
    )

    response = await client.get("/users/me", headers=auth_headers(expired))

    _assert_unauthorized(response)


async def test_token_with_tampered_payload_is_rejected(
    client: AsyncClient, user: AuthUser, admin: AuthUser
):
    # Swap in another user's payload but keep the original signature.
    header, _, signature = user.token.split(".")
    _, admin_payload, _ = admin.token.split(".")
    tampered = f"{header}.{admin_payload}.{signature}"

    response = await client.get("/users/me", headers=auth_headers(tampered))

    _assert_unauthorized(response)


async def test_token_with_tampered_signature_is_rejected(
    client: AsyncClient, user: AuthUser
):
    header, payload, signature = user.token.split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]

    response = await client.get(
        "/users/me", headers=auth_headers(f"{header}.{payload}.{flipped}")
    )

    _assert_unauthorized(response)


async def test_token_signed_with_another_key_is_rejected(
    client: AsyncClient, user: AuthUser
):
    token = _sign(
        _claims(user.id), key="some-other-secret-key-that-is-entirely-different"
    )

    response = await client.get("/users/me", headers=auth_headers(token))

    _assert_unauthorized(response)


async def test_unsigned_alg_none_token_is_rejected(client: AsyncClient, user: AuthUser):
    token = jwt.encode(_claims(user.id), key=None, algorithm="none")

    response = await client.get("/users/me", headers=auth_headers(token))

    _assert_unauthorized(response)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"sub": None}, id="missing-sub"),
        pytest.param({"exp": None}, id="missing-exp"),
        pytest.param({"sub": "not-a-number"}, id="non-numeric-sub"),
        pytest.param({"type": "refresh"}, id="wrong-token-type"),
    ],
)
async def test_validly_signed_token_with_bad_claims_is_rejected(
    client: AsyncClient, user: AuthUser, overrides: dict
):
    token = _sign(_claims(user.id, **overrides))

    response = await client.get("/users/me", headers=auth_headers(token))

    _assert_unauthorized(response)


async def test_token_for_a_user_that_never_existed_is_rejected(client: AsyncClient):
    token = create_access_token(999_999, RoleName.ADMIN.value)

    response = await client.get("/users/me", headers=auth_headers(token))

    _assert_unauthorized(response)


@pytest.mark.parametrize(
    "authorization",
    ["Bearer", "Bearer ", "Basic dXNlcjpwYXNz", "Token abc"],
    ids=["scheme-only", "empty-token", "basic-scheme", "unknown-scheme"],
)
async def test_malformed_authorization_header_is_rejected(
    client: AsyncClient, authorization: str
):
    response = await client.get("/users/me", headers={"Authorization": authorization})

    _assert_unauthorized(response)


async def test_valid_token_is_accepted(client: AsyncClient, user: AuthUser):
    response = await client.get("/users/me", headers=user.headers)

    assert response.status_code == 200


async def test_unknown_route_returns_404_in_the_error_envelope(client: AsyncClient):
    response = await client.get("/definitely-not-a-route")

    error = assert_error(response, 404, "NOT_FOUND")
    assert error["details"] is None


async def test_wrong_http_method_returns_405_in_the_error_envelope(
    client: AsyncClient,
):
    response = await client.delete("/users/me")

    assert_error(response, 405, "METHOD_NOT_ALLOWED")


async def test_validation_error_details_list_each_failing_field(
    client: AsyncClient, admin: AuthUser
):
    response = await client.get("/users?page=0&size=1000", headers=admin.headers)

    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert isinstance(error["details"], list)
    for item in error["details"]:
        assert set(item) == {"field", "message", "type"}
    fields = {item["field"] for item in error["details"]}
    assert fields == {"query.page", "query.size"}


async def test_malformed_json_body_returns_422_in_the_error_envelope(
    client: AsyncClient,
):
    response = await client.post(
        "/auth/register",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert_error(response, 422, "VALIDATION_ERROR")


async def test_health_endpoint_needs_no_authentication(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
