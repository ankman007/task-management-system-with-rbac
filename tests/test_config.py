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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", ""), ("/api", "/api"), ("/api/", "/api"), (" /api ", "/api")],
)
def test_root_path_is_normalised(
    env: pytest.MonkeyPatch, raw: str, expected: str
) -> None:
    env.setenv("ROOT_PATH", raw)
    assert _settings().root_path == expected


def test_root_path_must_be_absolute(env: pytest.MonkeyPatch) -> None:
    env.setenv("ROOT_PATH", "api")
    with pytest.raises(ValidationError, match="must start with"):
        _settings()


def test_allowed_hosts_accept_a_comma_separated_list(env: pytest.MonkeyPatch) -> None:
    env.setenv("ALLOWED_HOSTS", "a.example.com, b.example.com")
    assert _settings().allowed_hosts == ["a.example.com", "b.example.com"]


@pytest.fixture
def production(env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    env.setenv("ENVIRONMENT", "production")
    env.setenv("ALLOWED_HOSTS", "task-mgmt.example.com")
    return env


def test_valid_production_settings_load(production: pytest.MonkeyPatch) -> None:
    settings = _settings()
    assert settings.environment == "production"
    assert settings.allowed_hosts == ["task-mgmt.example.com"]


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("SECRET_KEY", "change-me-to-a-long-random-string-0123", "SECRET_KEY"),
        ("SECRET_KEY", "replace-with-a-long-random-string-0123", "SECRET_KEY"),
        ("ALLOWED_HOSTS", "*", "ALLOWED_HOSTS"),
        ("ALLOWED_HOSTS", "", "ALLOWED_HOSTS"),
        ("CORS_ORIGINS", "*", "CORS_ORIGINS"),
    ],
)
def test_unsafe_production_settings_refuse_to_load(
    production: pytest.MonkeyPatch, name: str, value: str, message: str
) -> None:
    production.setenv(name, value)
    with pytest.raises(ValidationError, match=message):
        _settings()


def test_development_tolerates_placeholders(env: pytest.MonkeyPatch) -> None:
    env.setenv("SECRET_KEY", "change-me-to-a-long-random-string-0123")
    assert _settings().allowed_hosts == ["*"]
