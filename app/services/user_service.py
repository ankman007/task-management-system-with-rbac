"""User lookups and role management."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Role, RoleName, User


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def list_users(
    db: AsyncSession, *, page: int, size: int
) -> tuple[list[User], int]:
    total = await db.scalar(select(func.count()).select_from(User)) or 0
    result = await db.execute(
        select(User).order_by(User.id).offset((page - 1) * size).limit(size)
    )
    return list(result.scalars().all()), total


async def change_user_role(
    db: AsyncSession, user_id: int, new_role: RoleName, actor: User
) -> User:
    """Give a user a different role (ADMIN only).

    The last remaining ADMIN can't be demoted, so the system can never be left
    without anyone able to manage roles. Setting the current role is a no-op.
    """
    if actor.role.name != RoleName.ADMIN:
        raise PermissionDeniedError("Only admins can change user roles")

    # Lock every ADMIN row, in id order, before anything else. Concurrent role
    # changes then queue here instead of each counting admins the other is
    # about to demote, and the fixed order rules out deadlocks.
    admin_ids = (
        await db.scalars(
            select(User.id)
            .join(User.role)
            .where(Role.name == RoleName.ADMIN)
            .order_by(User.id)
            .with_for_update(of=User)
        )
    ).all()
    # The caller's role was read before the lock; a concurrent request may have
    # demoted them since. Only a currently locked ADMIN row counts.
    if actor.id not in admin_ids:
        raise PermissionDeniedError("Only admins can change user roles")

    # populate_existing: the target may be the caller, already loaded in this
    # session; refresh it with the row as locked rather than a stale copy.
    target = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(of=User)
        .execution_options(populate_existing=True)
    )
    if target is None:
        raise NotFoundError(f"User {user_id} not found")
    if target.role.name == new_role:
        return target

    if target.role.name == RoleName.ADMIN and len(admin_ids) <= 1:
        raise ConflictError(
            "Cannot remove the ADMIN role from the last remaining admin",
            code="LAST_ADMIN",
        )

    target.role = await db.scalar(select(Role).where(Role.name == new_role))
    await db.commit()
    return target
