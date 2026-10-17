from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import RequestSchema

# bcrypt only uses the first 72 bytes of a password; reject longer ones rather
# than silently truncating them.
_BCRYPT_MAX_BYTES = 72


class UserRegister(RequestSchema):
    email: EmailStr
    password: str = Field(min_length=8, max_length=_BCRYPT_MAX_BYTES)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        if len(value.encode()) > _BCRYPT_MAX_BYTES:
            raise ValueError(f"Password must be at most {_BCRYPT_MAX_BYTES} bytes")
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one letter and one digit")
        return value


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
