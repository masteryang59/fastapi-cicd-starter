from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app import serve
from app.config import get_settings


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[dict[str, Any]]:
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'serve.db').as_posix()}")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    calls: dict[str, Any] = {}
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kw: calls.update(app=app, **kw))
    migrated: list[str] = []
    real_upgrade = serve.upgrade_to_head
    monkeypatch.setattr(
        serve, "upgrade_to_head", lambda url: migrated.append(url) or real_upgrade(url)
    )
    calls["migrated"] = migrated
    get_settings.cache_clear()
    yield calls
    get_settings.cache_clear()
    root.handlers[:], level = saved
    root.setLevel(level)


def test_serve_migrates_then_starts_uvicorn(env: dict[str, Any], tmp_path: Path) -> None:
    serve.main()
    assert env["migrated"] == [f"sqlite:///{(tmp_path / 'serve.db').as_posix()}"]
    assert (tmp_path / "serve.db").exists()
    assert env["app"] == "app.main:create_app"
    assert env["factory"] is True
    assert (env["host"], env["port"], env["workers"]) == ("0.0.0.0", 9123, 2)
    assert env["proxy_headers"] is True
    assert env["access_log"] is False


def test_serve_can_skip_migrations(env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_MIGRATIONS", "false")
    get_settings.cache_clear()
    serve.main()
    assert env["migrated"] == []
    assert env["app"] == "app.main:create_app"

def run_migration(data=None):
    if data is None:
        return None
    return data