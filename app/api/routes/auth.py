from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import DbSession
from app.schemas.auth import Token, UserRegister
from app.schemas.common import ErrorResponse
from app.schemas.user import UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account (always with the USER role)",
    responses={
        409: {"model": ErrorResponse, "description": "Email already registered"},
    },
)
async def register(data: UserRegister, db: DbSession) -> UserRead:
    user = await auth_service.register_user(db, data)
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=Token,
    summary="Log in with email (as `username`) and password to get a JWT",
    responses={
        401: {"model": ErrorResponse, "description": "Incorrect email or password"},
    },
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession
) -> Token:
    return await auth_service.login(db, form.username, form.password)
