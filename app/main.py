from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.deps import TOKEN_PATH
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

# The container healthcheck calls the API directly on localhost.
_INTERNAL_HOSTS = ("localhost", "127.0.0.1")


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
            422: {"model": ErrorResponse, "description": "Validation error"},
        },
        swagger_ui_parameters={"persistAuthorization": True},
        root_path=settings.root_path,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    if "*" not in settings.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[*settings.allowed_hosts, *_INTERNAL_HOSTS],
        )
    if settings.cors_origins:
        # Auth is a bearer header, not a cookie, so credentials stay disabled.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    register_exception_handlers(app)
    app.include_router(api_router)
    _prefix_swagger_token_url(app)

    @app.get("/health", tags=["Health"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _prefix_swagger_token_url(app: FastAPI) -> None:
    """Point Swagger's Authorize at the login route as the browser reaches it.

    Swagger UI resolves the OAuth2 tokenUrl against the page URL (/docs), so
    behind a proxy prefix it must include ROOT_PATH (e.g. /api/auth/login).
    Routes also answer without the prefix, so the URL works either way.
    """
    generate = app.openapi

    def openapi() -> dict:
        if app.openapi_schema is None:
            schema = generate()
            flows = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]
            flows["flows"]["password"]["tokenUrl"] = settings.root_path + TOKEN_PATH
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


app = create_app()
