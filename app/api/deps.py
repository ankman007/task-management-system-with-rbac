"""Reusable FastAPI dependencies: database session, authentication, role checks."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.db.session import async_session_factory
from app.models import RoleName, User
from app.services import user_service

# auto_error=False so a missing token goes through our own 401 error format.
# The relative tokenUrl is resolved by Swagger against the OpenAPI document's
# URL, so "Authorize" also works when the API is served under /api.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request. Services commit; anything uncommitted is rolled back."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)], db: DbSession
) -> User:
    if not token:
        raise AuthenticationError("Not authenticated")
    payload = decode_access_token(token)
    user = await user_service.get_user_by_id(db, payload.sub)
    if user is None:
        raise AuthenticationError("User no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: RoleName) -> Callable[[User], Awaitable[User]]:
    """Dependency factory that allows only the given roles through (403 otherwise)."""
    allowed = frozenset(roles)

    async def _check_role(current_user: CurrentUser) -> User:
        if current_user.role.name not in allowed:
            raise PermissionDeniedError(
                f"This action requires one of the roles: {', '.join(sorted(allowed))}"
            )
        return current_user

    return _check_role
