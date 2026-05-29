from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserAuthProfile(BaseModel):
    id: int
    email: EmailStr
    role_id: int

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserAuthProfile


class RefreshTokenRequest(BaseModel):
    refresh_token: str
