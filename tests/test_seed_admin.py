"""scripts/seed_admin.py: idempotent first-ADMIN bootstrap."""

import logging

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import RoleName, User
from app.schemas.auth import UserRegister
from scripts.seed_admin import (
    SeedAdminSettings,
    SeedError,
    ensure_admin,
    load_credentials,
)

EMAIL = "Root@Example.com"
PASSWORD = "Bootstrap123"


def _config(**values: str | None) -> SeedAdminSettings:
    return SeedAdminSettings(_env_file=None, **values)  # type: ignore[call-arg]


async def _find(db_session: AsyncSession, email: str) -> User | None:
    return await db_session.scalar(
        select(User)
        .where(User.email == email)
        .execution_options(populate_existing=True)
    )


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def test_seeding_is_skipped_when_both_variables_are_unset():
    assert load_credentials(_config()) is None


def test_blank_values_count_as_unset():
    assert (
        load_credentials(_config(first_admin_email=" ", first_admin_password=""))
        is None
    )


@pytest.mark.parametrize(
    "values",
    [{"first_admin_email": EMAIL}, {"first_admin_password": PASSWORD}],
    ids=["password-missing", "email-missing"],
)
def test_setting_only_one_variable_is_an_error(values: dict[str, str]):
    with pytest.raises(SeedError, match="is not set"):
        load_credentials(_config(**values))


@pytest.mark.parametrize(
    ("email", "password"),
    [("not-an-email", PASSWORD), (EMAIL, "short1"), (EMAIL, "lettersonly")],
)
def test_credentials_follow_the_registration_rules(email: str, password: str):
    with pytest.raises(SeedError, match="Invalid first admin credentials"):
        load_credentials(
            _config(first_admin_email=email, first_admin_password=password)
        )


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (EMAIL, "Admin12345"),
        ("admin@example.com", PASSWORD),
        ("replace-with-your-email@example.com", PASSWORD),
        (EMAIL, "replace-with-a-strong-password-1"),
    ],
    ids=["env-example-password", "env-example-email", "dokploy-email", "dokploy-pwd"],
)
def test_example_credentials_are_rejected_in_production(email: str, password: str):
    config = _config(
        environment="production",
        first_admin_email=email,
        first_admin_password=password,
    )

    with pytest.raises(SeedError, match="example value"):
        load_credentials(config)


def test_real_credentials_are_accepted_in_production():
    config = _config(
        environment="production",
        first_admin_email=EMAIL,
        first_admin_password=PASSWORD,
    )

    assert load_credentials(config) is not None


def test_the_example_password_is_allowed_for_local_development():
    config = _config(first_admin_email=EMAIL, first_admin_password="Admin12345")

    credentials = load_credentials(config)

    assert credentials is not None
    assert credentials.email == EMAIL.lower()


# --------------------------------------------------------------------------- #
# ensure_admin
# --------------------------------------------------------------------------- #
async def test_creates_the_admin_when_the_account_does_not_exist(
    db_session: AsyncSession,
):
    await ensure_admin(db_session, UserRegister(email=EMAIL, password=PASSWORD))

    user = await _find(db_session, EMAIL.lower())
    assert user is not None
    assert user.role.name == RoleName.ADMIN
    assert verify_password(PASSWORD, user.hashed_password)


async def test_running_again_changes_nothing_not_even_the_password(
    db_session: AsyncSession,
):
    await ensure_admin(db_session, UserRegister(email=EMAIL, password=PASSWORD))
    original_hash = (await _find(db_session, EMAIL.lower())).hashed_password

    await ensure_admin(db_session, UserRegister(email=EMAIL, password="Different456"))

    user = await _find(db_session, EMAIL.lower())
    assert user.hashed_password == original_hash
    assert user.role.name == RoleName.ADMIN
    accounts = await db_session.scalar(
        select(func.count()).select_from(User).where(User.email == EMAIL.lower())
    )
    assert accounts == 1


async def test_an_existing_non_admin_account_is_never_promoted(
    db_session: AsyncSession, make_user, caplog: pytest.LogCaptureFixture
):
    # Someone registered the bootstrap email through /auth/register first.
    squatter = await make_user(RoleName.USER, email=EMAIL.lower())

    with caplog.at_level(logging.WARNING, logger="seed_admin"):
        await ensure_admin(db_session, UserRegister(email=EMAIL, password=PASSWORD))

    user = await _find(db_session, EMAIL.lower())
    assert user.id == squatter.id
    assert user.role.name == RoleName.USER
    assert "not promoting" in caplog.text
