"""Task use cases and the RBAC rules that govern them.

Who can see a task is defined once, in `_VISIBLE_VIA`, and applied two ways:
`_visibility_filter` turns it into a SQL WHERE clause for listing, and
`_can_view` evaluates it against an already-loaded task. Every other
permission builds on visibility, so the list and the single-task endpoints
can never disagree.

The service enforces the full permission matrix itself; route-level role
gates are only a coarse first filter.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from sqlalchemy import ColumnElement, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import (
    InvalidStatusTransitionError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableEntityError,
)
from app.models import RoleName, Task, TaskStatus, User
from app.schemas.task import TaskCreate
from app.services import user_service

ALLOWED_TRANSITIONS: Final[Mapping[TaskStatus, frozenset[TaskStatus]]] = (
    MappingProxyType(
        {
            TaskStatus.PENDING: frozenset(
                {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED}
            ),
            TaskStatus.IN_PROGRESS: frozenset(
                {TaskStatus.PENDING, TaskStatus.COMPLETED}
            ),
            # A completed task can be reopened, but never sent back to PENDING.
            TaskStatus.COMPLETED: frozenset({TaskStatus.IN_PROGRESS}),
        }
    )
)

# The task columns that make a task visible to a role when they equal the
# caller's id. `None` means the role sees every task.
_OwnerColumns = tuple[InstrumentedAttribute[int | None], ...]
_VISIBLE_VIA: Final[Mapping[RoleName, _OwnerColumns | None]] = MappingProxyType(
    {
        RoleName.ADMIN: None,
        RoleName.MANAGER: (Task.created_by, Task.assigned_to),
        RoleName.USER: (Task.assigned_to,),
    }
)

# Roles allowed to create tasks and (re)assign the tasks they can see.
_TASK_MANAGER_ROLES: Final = frozenset({RoleName.ADMIN, RoleName.MANAGER})


def _visibility_filter(user: User) -> ColumnElement[bool]:
    """SQL condition selecting exactly the tasks `user` may see."""
    columns = _VISIBLE_VIA[user.role.name]
    if columns is None:
        return true()
    return or_(*(column == user.id for column in columns))


def _can_view(user: User, task: Task) -> bool:
    """Python twin of `_visibility_filter`, for a task that is already loaded."""
    columns = _VISIBLE_VIA[user.role.name]
    if columns is None:
        return True
    return any(getattr(task, column.key) == user.id for column in columns)


def _can_assign(user: User, task: Task) -> bool:
    return user.role.name in _TASK_MANAGER_ROLES and _can_view(user, task)


def _can_change_status(user: User, task: Task) -> bool:
    # Anyone who can see a task may move it through its workflow.
    return _can_view(user, task)


def _can_delete(user: User) -> bool:
    return user.role.name == RoleName.ADMIN


async def _get_task_or_404(
    db: AsyncSession, task_id: int, *, for_update: bool = False
) -> Task:
    task = await db.get(Task, task_id, with_for_update=for_update)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    return task


async def _ensure_assignee_exists(db: AsyncSession, user_id: int | None) -> None:
    if user_id is not None and await user_service.get_user_by_id(db, user_id) is None:
        raise UnprocessableEntityError(
            f"Assignee {user_id} does not exist",
            code="ASSIGNEE_NOT_FOUND",
            details={"assigned_to": user_id},
        )


async def _commit(db: AsyncSession, task: Task) -> Task:
    # Task uses eager_defaults, so created_at/updated_at are already loaded via
    # RETURNING, and expire_on_commit=False keeps them readable after commit.
    await db.commit()
    return task


async def create_task(db: AsyncSession, data: TaskCreate, creator: User) -> Task:
    """Create a task owned by `creator` (ADMIN or MANAGER)."""
    if creator.role.name not in _TASK_MANAGER_ROLES:
        raise PermissionDeniedError("Only admins and managers can create tasks")
    await _ensure_assignee_exists(db, data.assigned_to)

    task = Task(**data.model_dump(), created_by=creator.id)
    db.add(task)
    return await _commit(db, task)


async def list_tasks(
    db: AsyncSession,
    user: User,
    *,
    page: int,
    size: int,
    status: TaskStatus | None = None,
) -> tuple[list[Task], int]:
    """Return one page of the tasks visible to `user`, newest first, and the total."""
    conditions = [_visibility_filter(user)]
    if status is not None:
        conditions.append(Task.status == status)

    total = await db.scalar(select(func.count()).select_from(Task).where(*conditions))
    result = await db.scalars(
        select(Task)
        .where(*conditions)
        .order_by(Task.created_at.desc(), Task.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(result.all()), total or 0


async def get_task(db: AsyncSession, task_id: int, user: User) -> Task:
    """Return a task the caller can see (404 if missing, 403 if not visible)."""
    task = await _get_task_or_404(db, task_id)
    if not _can_view(user, task):
        raise PermissionDeniedError("You do not have access to this task")
    return task


async def assign_task(
    db: AsyncSession, task_id: int, assignee_id: int | None, user: User
) -> Task:
    """Assign a task to a user, or unassign it when `assignee_id` is None."""
    task = await _get_task_or_404(db, task_id, for_update=True)
    if not _can_assign(user, task):
        raise PermissionDeniedError("You are not allowed to assign this task")
    await _ensure_assignee_exists(db, assignee_id)

    task.assigned_to = assignee_id
    return await _commit(db, task)


async def update_task_status(
    db: AsyncSession, task_id: int, new_status: TaskStatus, user: User
) -> Task:
    """Move a task to `new_status` if the caller may and the transition is allowed."""
    task = await _get_task_or_404(db, task_id, for_update=True)
    if not _can_change_status(user, task):
        raise PermissionDeniedError("You are not allowed to update this task")

    allowed = ALLOWED_TRANSITIONS[task.status]
    if new_status not in allowed:
        raise InvalidStatusTransitionError(
            f"Cannot change status from {task.status} to {new_status}",
            details={
                "from": task.status,
                "to": new_status,
                "allowed": sorted(allowed),
            },
        )

    task.status = new_status
    return await _commit(db, task)


async def delete_task(db: AsyncSession, task_id: int, user: User) -> None:
    """Delete a task (ADMIN only)."""
    task = await _get_task_or_404(db, task_id)
    if not _can_delete(user):
        raise PermissionDeniedError("Only admins can delete tasks")
    await db.delete(task)
    await db.commit()
