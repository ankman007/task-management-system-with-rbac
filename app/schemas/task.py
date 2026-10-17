from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import TaskStatus
from app.schemas.common import RequestSchema


class TaskCreate(RequestSchema):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None
    assigned_to: int | None = Field(default=None, gt=0)

    @field_validator("due_date")
    @classmethod
    def _not_in_past(cls, value: date | None) -> date | None:
        if value is not None and value < date.today():
            raise ValueError("Due date cannot be in the past")
        return value


class TaskAssign(RequestSchema):
    # Required but nullable: an explicit `null` unassigns the task.
    assigned_to: int | None = Field(gt=0)


class TaskStatusUpdate(RequestSchema):
    status: TaskStatus


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    due_date: date | None
    assigned_to: int | None
    created_by: int
    created_at: datetime
    updated_at: datetime
