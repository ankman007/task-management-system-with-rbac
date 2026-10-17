"""Alembic environment: runs migrations through the app's async (asyncpg) driver.

The database URL comes from `app.core.config.settings`, i.e. the DATABASE_URL
environment variable (or `.env`), so there is a single source of truth for the
connection string and nothing is hard-coded in alembic.ini.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401  (registers every model on Base.metadata)
from alembic import context
from app.core.config import settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Shared by offline and online mode so autogenerate and `alembic check`
# detect column type changes, not only added/removed columns.
CONFIGURE_OPTS = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "compare_server_default": False,
}


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of connecting (`alembic upgrade head --sql`)."""
    context.configure(
        url=settings.database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **CONFIGURE_OPTS,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **CONFIGURE_OPTS)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # The URL is injected into the section dict rather than via
    # config.set_main_option(), which would choke on a "%" in the password
    # (ConfigParser interpolation).
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = settings.database_url
    connectable = async_engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
