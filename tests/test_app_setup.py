"""How the app behaves behind a reverse proxy: /api prefix, trusted hosts, docs."""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import create_app
from tests.helpers import assert_error


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch):
    """Override settings, then build a fresh app that reads them."""

    def _configure(**overrides: object) -> FastAPI:
        for name, value in overrides.items():
            monkeypatch.setattr(settings, name, value)
        return create_app()

    return _configure


@pytest_asyncio.fixture
async def http():
    clients: list[AsyncClient] = []

    def _client(app: FastAPI, host: str = "test") -> AsyncClient:
        client = AsyncClient(
            transport=ASGITransport(app=app), base_url=f"http://{host}"
        )
        clients.append(client)
        return client

    yield _client
    for client in clients:
        await client.aclose()


@pytest.mark.parametrize("path", ["/api/health", "/health"])
async def test_routes_answer_with_or_without_the_api_prefix(configure, http, path: str):
    client = http(configure(root_path="/api"))

    response = await client.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_protected_routes_work_under_the_api_prefix(configure, http):
    client = http(configure(root_path="/api"))

    response = await client.get("/api/tasks")

    assert_error(response, 401, "UNAUTHORIZED")


async def test_openapi_advertises_the_prefix_so_swagger_calls_the_right_urls(
    configure, http
):
    client = http(configure(root_path="/api"))

    spec = (await client.get("/openapi.json")).json()
    docs = await client.get("/docs")

    assert spec["servers"] == [{"url": "/api"}]
    # Relative, so Swagger resolves it against /api/openapi.json -> /api/auth/login.
    flow = spec["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]
    assert flow["password"]["tokenUrl"] == "auth/login"
    assert "/api/openapi.json" in docs.text


async def test_unknown_host_headers_are_rejected_when_hosts_are_restricted(
    configure, http
):
    app = configure(allowed_hosts=["task-mgmt.example.com"])

    allowed = await http(app, "task-mgmt.example.com").get("/health")
    spoofed = await http(app, "evil.example.com").get("/health")

    assert allowed.status_code == 200
    assert spoofed.status_code == 400


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
async def test_the_container_healthcheck_host_is_always_allowed(
    configure, http, host: str
):
    app = configure(allowed_hosts=["task-mgmt.example.com"])

    response = await http(app, host).get("/health")

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_docs_can_be_disabled(configure, http, path: str):
    client = http(configure(docs_enabled=False))

    response = await client.get(path)

    assert_error(response, 404, "NOT_FOUND")


async def test_cors_allows_configured_origins_without_credentials(configure, http):
    client = http(configure(cors_origins=["https://app.example.com"]))

    response = await client.options(
        "/tasks",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert "access-control-allow-credentials" not in response.headers


async def test_cors_ignores_other_origins(configure, http):
    client = http(configure(cors_origins=["https://app.example.com"]))

    response = await client.get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
