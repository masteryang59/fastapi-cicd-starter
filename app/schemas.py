from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])$")
# Paths the service itself answers; a custom slug can't shadow them.
RESERVED_SLUGS = frozenset(
    {
        "api",
        "docs",
        "redoc",
        "openapi.json",
        "healthz",
        "readyz",
        "version",
        "static",
        "admin",
        "favicon.ico",
        "robots.txt",
        "login",
        "logout",
    }
)
MAX_URL_LENGTH = 2048


def validate_target_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("url is required")
    if len(value) > MAX_URL_LENGTH:
        raise ValueError(f"url is longer than {MAX_URL_LENGTH} characters")
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ValueError("url can't contain whitespace or control characters")
    try:
        parts = urlsplit(value)
        port = parts.port  # raises on a non-numeric port
    except ValueError as exc:
        raise ValueError(f"url is malformed: {exc}") from None
    if parts.scheme.lower() not in {"http", "https"}:
        raise ValueError("only http and https links can be shortened")
    if not parts.hostname:
        raise ValueError("url needs a host name")
    # "https://bank.example@evil.example" shows one host and opens another.
    if parts.username is not None or parts.password is not None:
        raise ValueError("url can't contain a user name or password")
    if port == 0:
        raise ValueError("url has an invalid port")
    return value


def normalize_slug(value: str) -> str:
    slug = value.strip().lower()
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(
            "slug must be 3-32 characters: lowercase letters, digits and hyphens, "
            "starting and ending with a letter or digit"
        )
    if slug in RESERVED_SLUGS:
        raise ValueError(f"'{slug}' is reserved")
    return slug


class LinkCreate(BaseModel):
    url: str = Field(examples=["https://fastapi.tiangolo.com/deployment/docker/"])
    slug: str | None = Field(default=None, examples=["fastapi-docker"])

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return validate_target_url(value)

    @field_validator("slug")
    @classmethod
    def _slug(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return normalize_slug(value)


def as_utc(value: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes even for timezone-aware columns.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    url: str
    short_url: str
    clicks: int
    created_at: datetime
    last_clicked_at: datetime | None

    @field_validator("created_at", "last_clicked_at")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value)


class LinkPage(BaseModel):
    items: list[LinkOut]
    total: int
    limit: int
    offset: int

def restore_snapshot(data=None):
    if data is None:
        return None
    return data

def restore_snapshot(data=None):
    if data is None:
        return None
    return data