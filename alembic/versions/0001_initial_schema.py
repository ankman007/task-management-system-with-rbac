"""Initial schema: roles, users and tasks.

Revision ID: 0001
Revises:
Create Date: 2026-10-17

Constraint and index names follow the naming convention in app/db/base.py
(op.f() marks a name as already final), so `alembic check` reports no drift.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# create_type=False: the types are created/dropped explicitly below, so they
# are not implicitly re-created by create_table() or left behind on downgrade.
role_name = postgresql.ENUM(
    "ADMIN", "MANAGER", "USER", name="role_name", create_type=False
)
task_status = postgresql.ENUM(
    "PENDING", "IN_PROGRESS", "COMPLETED", name="task_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    role_name.create(bind, checkfirst=True)
    task_status.create(bind, checkfirst=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", role_name, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_users_role_id_roles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_role_id"), "users", ["role_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", task_status, server_default="PENDING", nullable=False
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"],
            ["users.id"],
            name=op.f("fk_tasks_assigned_to_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_tasks_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"])
    # Composite indexes back the "my tasks, newest first" visibility queries;
    # their leading columns also cover the assigned_to / created_by FKs.
    op.create_index(
        op.f("ix_tasks_assigned_to_created_at"),
        "tasks",
        ["assigned_to", "created_at"],
    )
    op.create_index(
        op.f("ix_tasks_created_by_created_at"),
        "tasks",
        ["created_by", "created_at"],
    )
    op.create_index(op.f("ix_tasks_created_at_id"), "tasks", ["created_at", "id"])


def downgrade() -> None:
    # Dropping a table drops its indexes and constraints with it.
    op.drop_table("tasks")
    op.drop_table("users")
    op.drop_table("roles")

    bind = op.get_bind()
    task_status.drop(bind, checkfirst=True)
    role_name.drop(bind, checkfirst=True)
