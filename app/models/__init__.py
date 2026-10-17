"""Import every model here so `Base.metadata` is complete (used by Alembic)."""

from app.models.enums import RoleName, TaskStatus
from app.models.role import Role
from app.models.task import Task
from app.models.user import User

__all__ = ["Role", "RoleName", "Task", "TaskStatus", "User"]
