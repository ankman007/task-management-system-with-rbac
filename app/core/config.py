"""Application settings, loaded from environment variables (and `.env` locally)."""

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # Comma-separated list in the environment, e.g. "http://localhost:18080".
    # NoDecode stops pydantic-settings from requiring JSON for this field.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg_driver(cls, value: str) -> str:
        for prefix in ("postgresql://", "postgres://", "postgresql+psycopg://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value.removeprefix(prefix)
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.lstrip().startswith("["):
            return json.loads(value)
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # secret_key comes from the env


settings = get_settings()
