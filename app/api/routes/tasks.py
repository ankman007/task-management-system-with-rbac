from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.api.deps import CurrentUser, DbSession, require_roles
from app.models import RoleName, TaskStatus, User
from app.schemas.common import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    UNAUTHORIZED_RESPONSE,
    ErrorResponse,
    Page,
)
from app.schemas.task import TaskAssign, TaskCreate, TaskRead, TaskStatusUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"], responses=UNAUTHORIZED_RESPONSE)

TaskId = Annotated[int, Path(gt=0, description="Task identifier")]
TaskManager = Annotated[User, Depends(require_roles(RoleName.ADMIN, RoleName.MANAGER))]
Admin = Annotated[User, Depends(require_roles(RoleName.ADMIN))]


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries documenting the given error status codes."""
    descriptions = {
        status.HTTP_400_BAD_REQUEST: "Status transition not allowed",
        status.HTTP_403_FORBIDDEN: "Not permitted for this task or role",
        status.HTTP_404_NOT_FOUND: "Task not found",
        status.HTTP_422_UNPROCESSABLE_CONTENT: "Validation error or unknown assignee",
    }
    return {
        code: {"model": ErrorResponse, "description": descriptions[code]}
        for code in codes
    }


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    responses=_errors(status.HTTP_403_FORBIDDEN, status.HTTP_422_UNPROCESSABLE_CONTENT),
)
async def create_task(
    body: TaskCreate, db: DbSession, current_user: TaskManager
) -> TaskRead:
    task = await task_service.create_task(db, body, current_user)
    return TaskRead.model_validate(task)


@router.get(
    "",
    response_model=Page[TaskRead],
    summary="List the tasks visible to the caller",
)
async def list_tasks(
    db: DbSession,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
) -> Page[TaskRead]:
    tasks, total = await task_service.list_tasks(
        db, current_user, page=page, size=size, status=task_status
    )
    return Page[TaskRead].create(
        [TaskRead.model_validate(t) for t in tasks], total, page, size
    )


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task",
    responses=_errors(status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
)
async def get_task(
    task_id: TaskId, db: DbSession, current_user: CurrentUser
) -> TaskRead:
    task = await task_service.get_task(db, task_id, current_user)
    return TaskRead.model_validate(task)


@router.patch(
    "/{task_id}/assign",
    response_model=TaskRead,
    summary="Assign or unassign a task",
    responses=_errors(
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    ),
)
async def assign_task(
    task_id: TaskId, body: TaskAssign, db: DbSession, current_user: TaskManager
) -> TaskRead:
    task = await task_service.assign_task(db, task_id, body.assigned_to, current_user)
    return TaskRead.model_validate(task)


@router.patch(
    "/{task_id}/status",
    response_model=TaskRead,
    summary="Change a task's status",
    responses=_errors(
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
    ),
)
async def update_task_status(
    task_id: TaskId, body: TaskStatusUpdate, db: DbSession, current_user: CurrentUser
) -> TaskRead:
    task = await task_service.update_task_status(db, task_id, body.status, current_user)
    return TaskRead.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a task",
    responses=_errors(status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
)
async def delete_task(task_id: TaskId, db: DbSession, current_user: Admin) -> None:
    await task_service.delete_task(db, task_id, current_user)
