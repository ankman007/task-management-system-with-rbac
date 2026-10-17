from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import RoleName


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: RoleName
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def _role_name(cls, value: object) -> object:
        # Built from the ORM, `role` is a Role object; expose just its name.
        return getattr(value, "name", value)
