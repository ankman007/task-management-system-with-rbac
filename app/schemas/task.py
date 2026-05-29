from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.models.task import TaskStatus


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    due_date: Optional[datetime] = None

    @field_validator("due_date")
    @classmethod
    def ensure_due_date_is_future(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return value
        now = datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value < now:
            raise ValueError("The task due date cannot be set in the past.")

        return value


class TaskCreate(TaskBase):
    assigned_to_id: Optional[int] = Field(default=None, gt=0)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    assigned_to_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("due_date")
    @classmethod
    def ensure_update_date_is_future(
        cls, value: Optional[datetime]
    ) -> Optional[datetime]:
        if value is None:
            return value
        now = datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value < now:
            raise ValueError("The task due date cannot be set in the past.")
        return value


class TaskResponse(TaskBase):
    id: int
    status: TaskStatus
    created_by_id: int
    assigned_to_id: Optional[int]

    model_config = ConfigDict(from_attributes=True)


class TaskAssignRequest(BaseModel):
    assign_to_id: int = Field(..., gt=0)
