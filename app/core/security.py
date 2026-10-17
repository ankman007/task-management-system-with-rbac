"""Password hashing and JWT helpers. Pure functions with no database access."""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.exceptions import AuthenticationError

_password_hash = PasswordHash((BcryptHasher(),))

# Verified against when a login email is unknown, so the response time doesn't
# reveal whether an account exists.
_DUMMY_HASH = _password_hash.hash("timing-attack-mitigation")


class TokenPayload(BaseModel):
    sub: int
    role: str
    exp: int
    iat: int
    type: str


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str | None) -> bool:
    """Check a password. Pass `None` for an unknown user to keep timing constant."""
    if hashed_password is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, hashed_password)


def create_access_token(
    user_id: int, role: str, expires_delta: timedelta | None = None
) -> str:
    now = datetime.now(UTC)
    expire = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    claims = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate an access token, raising `AuthenticationError` if invalid."""
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
        payload = TokenPayload.model_validate(claims)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except (jwt.InvalidTokenError, ValidationError) as exc:
        raise AuthenticationError("Invalid authentication token") from exc

    if payload.type != "access":
        raise AuthenticationError("Invalid authentication token")
    return payload
