from pydantic import BaseModel, EmailStr
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str
    role_id: int


class UserResponse(UserBase):
    id: int
    role_id: int
    
    class Config:
        from_attributes = True