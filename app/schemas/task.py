from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.task import TaskStatus

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None


class TaskCreate(TaskBase):
    assigned_to_id: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    assigned_to_id: Optional[int] = None


class TaskResponse(TaskBase):
    id: int
    status: TaskStatus
    created_by_id: int
    assigned_to_id: Optional[int]

    class Config:
        from_attributes = True
        

class TaskAssignRequest(BaseModel):
    assign_to_id: int