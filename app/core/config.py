"""Application settings, loaded from environment variables (and `.env` locally)."""

import json
from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Substrings of the example values shipped in .env.example / .env.dokploy.example.
PLACEHOLDER_MARKERS = ("change-me", "replace-with", "changeme")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    project_name: str = "Task Management API"
    api_version: str = "1.0.0"
    environment: Literal["local", "test", "production"] = "local"

    # Database. A plain `postgresql://` URL is accepted and upgraded to asyncpg.
    database_url: str = Field(
        default="postgresql+asyncpg://task_user:task_password@localhost:15432/task_db"
    )
    db_echo: bool = False
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    # JWT. PyJWT warns about HS256 keys shorter than 32 bytes.
    secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=1)

    # Comma-separated lists in the environment, e.g. "http://localhost:18080".
    # NoDecode stops pydantic-settings from requiring JSON for these fields.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Host headers the API answers to; "*" allows any (development only).
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    # Path prefix the reverse proxy serves the API under (e.g. "/api"). Routes
    # stay unprefixed; requests may arrive with or without it.
    root_path: str = ""
    docs_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg_driver(cls, value: str) -> str:
        for prefix in ("postgresql://", "postgres://", "postgresql+psycopg://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value.removeprefix(prefix)
        return value

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def _split_list(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.lstrip().startswith("["):
            return json.loads(value)
        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("root_path")
    @classmethod
    def _normalise_root_path(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value and not value.startswith("/"):
            raise ValueError("ROOT_PATH must start with '/', e.g. /api")
        return value

    @model_validator(mode="after")
    def _check_production_safety(self) -> Self:
        """Refuse to start in production with development-only settings."""
        if self.environment != "production":
            return self
        problems = []
        if any(marker in self.secret_key.lower() for marker in PLACEHOLDER_MARKERS):
            problems.append("SECRET_KEY is a placeholder; generate a random one")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            problems.append("ALLOWED_HOSTS must list the public host(s), not '*'")
        if "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must not be '*'")
        if problems:
            raise ValueError("Unsafe production settings: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # secret_key comes from the env


settings = get_settings()
