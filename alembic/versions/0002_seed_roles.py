"""Seed the fixed set of roles (ADMIN, MANAGER, USER).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17

Roles are reference data the application cannot run without (registration
assigns USER), so they ship as a data migration rather than a runtime seed.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Hard-coded rather than imported from app.models.enums: a migration must keep
# meaning the same thing even if the application enum changes later. They are
# constants, so they are inlined as SQL literals (no bind parameters), which
# also keeps offline mode (`alembic upgrade head --sql`) working.
ROLES = ("ADMIN", "MANAGER", "USER")
_ROLE_VALUES = ", ".join(f"('{role}')" for role in ROLES)
_ROLE_LIST = ", ".join(f"'{role}'" for role in ROLES)


def upgrade() -> None:
    # ON CONFLICT makes this safe to run against a database where the roles
    # were already created by hand or by an earlier seed script.
    op.execute(
        sa.text(
            f"INSERT INTO roles (name) VALUES {_ROLE_VALUES} "
            "ON CONFLICT (name) DO NOTHING"
        )
    )


def downgrade() -> None:
    # Only delete roles that no user references. users.role_id is
    # ON DELETE RESTRICT, so an unconditional DELETE would abort the downgrade
    # as soon as any account exists; skipping referenced roles instead lets
    # the downgrade succeed without destroying user data. (Downgrading on to
    # base drops the tables anyway.)
    op.execute(
        sa.text(
            f"DELETE FROM roles WHERE name IN ({_ROLE_LIST}) "
            "AND NOT EXISTS (SELECT 1 FROM users WHERE users.role_id = roles.id)"
        )
    )
