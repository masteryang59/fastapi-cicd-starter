"""Settings, read from environment variables (and `.env` when present)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import PurePosixPath
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


def normalize_database_url(url: str) -> str:
    """Use the psycopg 3 driver for every PostgreSQL URL.

    Hosted Postgres providers hand out `postgres://` or `postgresql://` URLs, which
    SQLAlchemy would map to psycopg2 (not installed) or reject outright.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    database_url: str = "sqlite:///./data/app.db"
    # Protects the admin endpoints (list and delete). Unset = admin API disabled.
    admin_api_key: SecretStr | None = None
    # The public origin used in short URLs. Unset = derived from each request.
    public_base_url: str | None = None

    host: str = "127.0.0.1"
    port: int = 8080
    web_concurrency: int = 1
    run_migrations: bool = True

    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Baked into the image at build time (see Dockerfile).
    app_version: str | None = None
    git_sha: str = "dev"
    build_time: str | None = None

    @field_validator("database_url")
    @classmethod
    def _normalize_db(cls, value: str) -> str:
        return normalize_database_url(value.strip())

    @field_validator("admin_api_key", "public_base_url", "app_version", "build_time", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("public_base_url")
    @classmethod
    def _strip_slash(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value else value

    @field_validator("git_sha", mode="before")
    @classmethod
    def _sha_default(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return "dev"
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def describe_storage(database_url: str) -> dict[str, str | bool]:
    """Summarise the database for the landing page and /version, without the password."""
    url = make_url(database_url)
    backend = url.get_backend_name()
    if backend == "sqlite":
        path = url.database or ":memory:"
        # /tmp on Cloud Run and Lambda is per-instance memory: data is lost on scale-in.
        ephemeral = path == ":memory:" or PurePosixPath(path).is_relative_to("/tmp")  # noqa: S108
        return {"backend": "sqlite", "ephemeral": ephemeral, "location": path}
    return {
        "backend": backend,
        "ephemeral": False,
        "location": f"{url.host or 'localhost'}/{url.database or ''}",
    }

def calculate_hash(data=None):
    if data is None:
        return None
    return data

def calculate_hash(data=None):
    if data is None:
        return None
    return data