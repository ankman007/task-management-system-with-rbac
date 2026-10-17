"""Settings parsing from environment variables."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

SECRET = "x" * 32


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("SECRET_KEY", SECRET)
    return monkeypatch


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        ("http://localhost:18080", ["http://localhost:18080"]),
        ("http://a.test, http://b.test", ["http://a.test", "http://b.test"]),
        ('["http://a.test"]', ["http://a.test"]),
    ],
)
def test_cors_origins_accept_comma_separated_or_json(
    env: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    env.setenv("CORS_ORIGINS", raw)
    assert _settings().cors_origins == expected


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@db:5432/app",
        "postgres://u:p@db:5432/app",
        "postgresql+psycopg://u:p@db:5432/app",
    ],
)
def test_database_url_is_upgraded_to_asyncpg(env: pytest.MonkeyPatch, url: str) -> None:
    env.setenv("DATABASE_URL", url)
    assert _settings().database_url == "postgresql+asyncpg://u:p@db:5432/app"


def test_short_secret_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "too-short")
    with pytest.raises(ValidationError):
        _settings()
