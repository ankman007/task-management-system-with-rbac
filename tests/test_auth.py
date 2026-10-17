"""POST /auth/register and POST /auth/login."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import verify_password
from app.models import User
from tests.helpers import DEFAULT_PASSWORD, AuthUser, assert_error, auth_headers

VALID_PASSWORD = "s3cretPassword"


async def _register(client: AsyncClient, **body):
    body.setdefault("email", "new.person@example.com")
    body.setdefault("password", VALID_PASSWORD)
    return await client.post("/auth/register", json=body)


async def _login(client: AsyncClient, username: str, password: str):
    return await client.post(
        "/auth/login", data={"username": username, "password": password}
    )


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #
async def test_register_creates_a_user_with_the_user_role(client: AsyncClient):
    response = await _register(client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "email", "role", "created_at"}
    assert body["email"] == "new.person@example.com"
    assert body["role"] == "USER"
    assert isinstance(body["id"], int)


async def test_register_stores_a_hash_not_the_plain_password(
    client: AsyncClient, db_session: AsyncSession
):
    await _register(client)

    stored = await db_session.scalar(
        select(User).where(User.email == "new.person@example.com")
    )
    assert stored is not None
    assert stored.hashed_password != VALID_PASSWORD
    assert verify_password(VALID_PASSWORD, stored.hashed_password)


async def test_register_lowercases_the_email(client: AsyncClient):
    response = await _register(client, email="Mixed.Case@Example.COM")

    assert response.status_code == 201
    assert response.json()["email"] == "mixed.case@example.com"


@pytest.mark.parametrize(
    "duplicate", ["new.person@example.com", "NEW.PERSON@EXAMPLE.COM"]
)
async def test_register_rejects_an_already_registered_email_case_insensitively(
    client: AsyncClient, duplicate: str
):
    assert (await _register(client)).status_code == 201

    response = await _register(client, email=duplicate)

    assert_error(response, 409, "EMAIL_ALREADY_REGISTERED")


@pytest.mark.parametrize("role", ["ADMIN", "MANAGER", "USER"])
async def test_register_rejects_a_role_field_so_users_cannot_self_promote(
    client: AsyncClient, db_session: AsyncSession, role: str
):
    response = await _register(client, role=role)

    assert_error(response, 422, "VALIDATION_ERROR")
    assert await db_session.scalar(select(User)) is None


@pytest.mark.parametrize(
    ("body", "failing_field"),
    [
        pytest.param({"email": "not-an-email"}, "body.email", id="invalid-email"),
        pytest.param({"email": ""}, "body.email", id="empty-email"),
        pytest.param({"password": "a1b2c3"}, "body.password", id="too-short"),
        pytest.param({"password": "onlyletters"}, "body.password", id="no-digit"),
        pytest.param({"password": "1234567890"}, "body.password", id="no-letter"),
        pytest.param(
            # 37 characters but 73 bytes: the limit is bcrypt's 72 *bytes*.
            {"password": "1" + "é" * 36},
            "body.password",
            id="over-72-bytes",
        ),
    ],
)
async def test_register_rejects_invalid_input_with_field_level_details(
    client: AsyncClient, body: dict, failing_field: str
):
    response = await _register(client, **body)

    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert isinstance(error["details"], list)
    for item in error["details"]:
        assert set(item) == {"field", "message", "type"}
    assert failing_field in {item["field"] for item in error["details"]}


@pytest.mark.parametrize("missing", ["email", "password"])
async def test_register_requires_email_and_password(client: AsyncClient, missing: str):
    body = {"email": "new.person@example.com", "password": VALID_PASSWORD}
    del body[missing]

    response = await client.post("/auth/register", json=body)

    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert f"body.{missing}" in {item["field"] for item in error["details"]}


async def test_register_accepts_a_password_of_exactly_8_characters(
    client: AsyncClient,
):
    response = await _register(client, password="abcdefg1")

    assert response.status_code == 201


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
async def test_login_returns_a_bearer_token(client: AsyncClient, user: AuthUser):
    response = await _login(client, user.email, DEFAULT_PASSWORD)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_expire_minutes * 60


async def test_login_token_authenticates_as_that_user(
    client: AsyncClient, user: AuthUser
):
    token = (await _login(client, user.email, DEFAULT_PASSWORD)).json()["access_token"]

    response = await client.get("/users/me", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["id"] == user.id


async def test_login_email_is_case_insensitive(client: AsyncClient, user: AuthUser):
    response = await _login(client, user.email.upper(), DEFAULT_PASSWORD)

    assert response.status_code == 200


async def test_register_then_login_then_access_a_protected_endpoint(
    client: AsyncClient,
):
    await _register(client, email="flow@example.com")

    login = await _login(client, "flow@example.com", VALID_PASSWORD)
    me = await client.get(
        "/users/me", headers=auth_headers(login.json()["access_token"])
    )

    assert me.status_code == 200
    assert me.json()["email"] == "flow@example.com"
    assert me.json()["role"] == "USER"


async def test_login_with_wrong_password_and_unknown_email_fail_identically(
    client: AsyncClient, user: AuthUser
):
    # Same status, code and message: the response must not reveal which
    # emails are registered.
    wrong_password = await _login(client, user.email, "WrongPassword1")
    unknown_email = await _login(client, "nobody@example.com", DEFAULT_PASSWORD)

    wrong_error = assert_error(wrong_password, 401, "INVALID_CREDENTIALS")
    unknown_error = assert_error(unknown_email, 401, "INVALID_CREDENTIALS")
    assert wrong_error["message"] == unknown_error["message"]


@pytest.mark.parametrize("missing", ["username", "password"])
async def test_login_requires_username_and_password(client: AsyncClient, missing: str):
    form = {"username": "user@example.com", "password": DEFAULT_PASSWORD}
    del form[missing]

    response = await client.post("/auth/login", data=form)

    assert_error(response, 422, "VALIDATION_ERROR")


async def test_login_expects_form_data_not_json(client: AsyncClient, user: AuthUser):
    response = await client.post(
        "/auth/login", json={"username": user.email, "password": DEFAULT_PASSWORD}
    )

    assert_error(response, 422, "VALIDATION_ERROR")
