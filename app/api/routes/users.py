from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, DbSession, require_roles
from app.models import RoleName, User
from app.schemas.common import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    UNAUTHORIZED_RESPONSE,
    ErrorResponse,
    Page,
)
from app.schemas.user import UserRead, UserRoleUpdate
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


@router.patch(
    "/{user_id}/role",
    response_model=UserRead,
    summary="Change a user's role (ADMIN only)",
    responses={
        403: {"model": ErrorResponse, "description": "Caller is not an ADMIN"},
        404: {"model": ErrorResponse, "description": "User not found"},
        409: {
            "model": ErrorResponse,
            "description": "Would remove the last remaining ADMIN",
        },
    },
)
async def change_user_role(
    user_id: Annotated[int, Path(gt=0, description="User identifier")],
    body: UserRoleUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(require_roles(RoleName.ADMIN))],
) -> UserRead:
    user = await user_service.change_user_role(db, user_id, body.role, current_user)
    return UserRead.model_validate(user)
