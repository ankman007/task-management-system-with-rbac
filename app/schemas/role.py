from pydantic import BaseModel, ConfigDict
from app.models.role import RoleName

class RoleBase(BaseModel):
    name: RoleName


class RoleCreate(RoleBase):
    pass 


class RoleUpdate(RoleBase):
    pass


class RoleResponse(RoleBase):
    id: int

    class Config:
        from_attributes = True