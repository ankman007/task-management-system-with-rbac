"""Create (or promote) the first ADMIN account.

Usage::

    python -m scripts.seed_admin

Reads FIRST_ADMIN_EMAIL and FIRST_ADMIN_PASSWORD from the environment (or
`.env`). The script is idempotent and safe to run on every container start:

* both variables unset     -> nothing to do, exit 0 (bootstrapping is optional);
* only one of them set     -> configuration error, exit 1;
* the email already exists -> leave the account alone: never change its
  password or its role. An existing non-admin account is NOT promoted,
  because anyone could have registered that email through the public
  /auth/register endpoint before the first deploy; promote it explicitly
  with PATCH /users/{id}/role instead;
* otherwise                -> create the account with the ADMIN role.

With ENVIRONMENT=production the example values from .env.example and
.env.dokploy.example are rejected (exit 1), so a deploy can't go live with
well-known credentials.

The roles themselves are created by migration 0002, so run
`alembic upgrade head` first.
"""

import asyncio
import logging
import sys

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PLACEHOLDER_MARKERS
from app.core.security import hash_password
from app.db.session import async_session_factory, engine
from app.models import Role, RoleName, User
from app.schemas.auth import UserRegister

logger = logging.getLogger("seed_admin")


class SeedAdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "local"
    first_admin_email: str | None = None
    first_admin_password: str | None = None

    @field_validator("first_admin_email", "first_admin_password", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        # `FIRST_ADMIN_EMAIL=` in an env file means "not configured".
        if isinstance(value, str) and not value.strip():
            return None
        return value


# The example credentials shipped in .env.example.
_EXAMPLE_VALUES = frozenset({"admin@example.com", "Admin12345"})


class SeedError(Exception):
    """A problem the operator has to fix; reported without a traceback."""


def load_credentials(config: SeedAdminSettings | None = None) -> UserRegister | None:
    """Return validated credentials, or None if seeding is not configured."""
    config = config or SeedAdminSettings()
    email, password = config.first_admin_email, config.first_admin_password

    if email is None and password is None:
        return None
    if email is None or password is None:
        missing = "FIRST_ADMIN_EMAIL" if email is None else "FIRST_ADMIN_PASSWORD"
        raise SeedError(
            f"{missing} is not set. Set both FIRST_ADMIN_EMAIL and "
            "FIRST_ADMIN_PASSWORD, or neither to skip admin seeding."
        )
    if config.environment == "production":
        for name, value in (
            ("FIRST_ADMIN_EMAIL", email),
            ("FIRST_ADMIN_PASSWORD", password),
        ):
            if value in _EXAMPLE_VALUES or any(
                marker in value.lower() for marker in PLACEHOLDER_MARKERS
            ):
                raise SeedError(
                    f"{name} is still the example value; set a real one for production."
                )

    # Same rules as POST /auth/register (email format, lower-casing, password
    # length and complexity), so the admin can log in through the normal flow.
    try:
        return UserRegister(email=email, password=password)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors()
        )
        raise SeedError(f"Invalid first admin credentials: {problems}") from None


async def ensure_admin(session: AsyncSession, credentials: UserRegister) -> None:
    admin_role = await session.scalar(select(Role).where(Role.name == RoleName.ADMIN))
    if admin_role is None:
        raise SeedError(
            "The ADMIN role does not exist. Run `alembic upgrade head` first."
        )

    user = await session.scalar(select(User).where(User.email == credentials.email))
    if user is None:
        session.add(
            User(
                email=credentials.email,
                hashed_password=hash_password(credentials.password),
                role_id=admin_role.id,
            )
        )
        await session.commit()
        logger.info("Created admin account %s", credentials.email)
    elif user.role_id != admin_role.id:
        logger.warning(
            "Account %s already exists with role %s; not promoting it. "
            "If it is yours, have an admin call PATCH /users/%d/role.",
            user.email,
            user.role.name,
            user.id,
        )
    else:
        logger.info("Admin account %s already exists; nothing to do", user.email)


async def run(credentials: UserRegister) -> None:
    try:
        async with async_session_factory() as session:
            try:
                await ensure_admin(session, credentials)
            except IntegrityError:
                # Another process (e.g. a second API replica starting at the
                # same time) inserted the same email between our SELECT and
                # INSERT. Retry once: the account now exists, so this run
                # only verifies/promotes it.
                await session.rollback()
                await ensure_admin(session, credentials)
    finally:
        await engine.dispose()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s"
    )
    try:
        credentials = load_credentials()
        if credentials is None:
            logger.info(
                "FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD not set; "
                "skipping admin seeding"
            )
            return 0
        asyncio.run(run(credentials))
    except SeedError as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
