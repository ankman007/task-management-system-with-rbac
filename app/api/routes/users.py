from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, require_roles
from app.models import RoleName
from app.schemas.common import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    UNAUTHORIZED_RESPONSE,
    Page,
)
from app.schemas.user import UserRead
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"], responses=UNAUTHORIZED_RESPONSE)


@router.get("/me", response_model=UserRead, summary="Get the current user")
async def read_current_user(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get(
    "",
    response_model=Page[UserRead],
    summary="List users (to pick an assignee)",
    dependencies=[Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER))],
)
async def list_users(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Page[UserRead]:
    users, total = await user_service.list_users(db, page=page, size=size)
    return Page[UserRead].create(
        [UserRead.model_validate(u) for u in users], total, page, size
    )
