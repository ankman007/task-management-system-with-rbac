"""Registration, credential checks and access-token issuing."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Role, RoleName, User
from app.schemas.auth import Token, UserRegister
from app.services import user_service


def _email_taken(email: str) -> ConflictError:
    return ConflictError(
        f"Email {email} is already registered", code="EMAIL_ALREADY_REGISTERED"
    )


def _invalid_credentials() -> AuthenticationError:
    # One message for unknown email and wrong password, so accounts can't be probed.
    return AuthenticationError(
        "Incorrect email or password", code="INVALID_CREDENTIALS"
    )


async def register_user(db: AsyncSession, data: UserRegister) -> User:
    """Create a USER account. Public registration can never grant a higher role."""
    if await user_service.get_user_by_email(db, data.email) is not None:
        raise _email_taken(data.email)

    role = await db.scalar(select(Role).where(Role.name == RoleName.USER))
    if role is None:
        raise AppException(
            "The USER role is missing; run the database migrations to seed roles",
            code="ROLES_NOT_SEEDED",
        )

    user = User(
        email=data.email, hashed_password=hash_password(data.password), role=role
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        # Another request registered the same email between our check and commit.
        await db.rollback()
        raise _email_taken(data.email) from exc

    # Load server-generated columns (created_at) and the joined role eagerly;
    # async sessions can't lazy-load them later.
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await user_service.get_user_by_email(db, email.strip().lower())
    # Always run a bcrypt check (against a dummy hash for unknown emails) so the
    # response time doesn't reveal whether the account exists.
    password_ok = verify_password(password, user.hashed_password if user else None)
    if user is None or not password_ok:
        raise _invalid_credentials()
    return user


async def login(db: AsyncSession, email: str, password: str) -> Token:
    user = await authenticate_user(db, email, password)
    return Token(
        access_token=create_access_token(user.id, user.role.name),
        expires_in=settings.access_token_expire_minutes * 60,
    )
