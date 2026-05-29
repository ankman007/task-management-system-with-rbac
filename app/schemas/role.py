from pydantic import BaseModel, ConfigDict
from app.models.role import RoleName


class RoleResponse(BaseModel):
    id: int
    name: RoleName

    model_config = ConfigDict(from_attributes=True)
