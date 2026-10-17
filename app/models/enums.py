from enum import StrEnum


class RoleName(StrEnum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    USER = "USER"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
