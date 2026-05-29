import jwt
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from typing import Any, Union
import bcrypt


load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "hello_world")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


# Combined token generator with customizable expiration handles both roles
def create_token(subject: Union[str, Any], expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def generate_auth_tokens(user_id: int) -> dict:
    """Helper to generate both access and refresh tokens cleanly at once."""
    access_token = create_token(
        subject=user_id, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_token(
        subject=user_id, expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    return {"access_token": access_token, "refresh_token": refresh_token}
