from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.db.session import engine
from app.schemas.common import ErrorResponse

DESCRIPTION = """
Task management API with role-based access control (ADMIN, MANAGER, USER).

**Authenticating in Swagger:** register via `POST /auth/register`, then click
**Authorize** and enter your email as the *username* along with your password.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        version=settings.api_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        responses={
            401: {"model": ErrorResponse, "description": "Missing or invalid token"},
            422: {"model": ErrorResponse, "description": "Validation error"},
        },
        swagger_ui_parameters={"persistAuthorization": True},
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["Health"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
