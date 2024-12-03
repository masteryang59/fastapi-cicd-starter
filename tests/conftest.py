"""Shared fixtures.

The suite runs against SQLite by default. With DATABASE_URL pointing at PostgreSQL (as
in the CI `postgres` leg) every database test runs against PostgreSQL instead.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.config import Settings, normalize_database_url
from app.db import create_db_engine
from app.main import create_app
from app.schema import upgrade_to_head

TEST_SHA = "0123456789abcdef0123456789abcdef01234567"
_ENV_URL = os.environ.get("DATABASE_URL", "")
USING_POSTGRES = _ENV_URL.startswith(("postgres://", "postgresql"))

requires_postgres = pytest.mark.skipif(not USING_POSTGRES, reason="DATABASE_URL is not PostgreSQL")


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    if USING_POSTGRES:
        url = normalize_database_url(_ENV_URL)
    else:
        url = f"sqlite:///{(tmp_path_factory.mktemp('db') / 'test.db').as_posix()}"
    upgrade_to_head(url)
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    eng = create_db_engine(database_url)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _clean_links(request: pytest.FixtureRequest) -> Iterator[None]:
    yield
    if "engine" in request.fixturenames:
        eng: Engine = request.getfixturevalue("engine")
        with eng.begin() as conn:
            conn.execute(text("DELETE FROM links"))


def make_settings(database_url: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": database_url,
        "environment": "test",
        "log_format": "text",
        "git_sha": TEST_SHA,
        "admin_api_key": None,
        "public_base_url": None,
        "app_version": None,
        "build_time": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def make_client(engine: Engine, database_url: str) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def factory(**overrides: Any) -> TestClient:
        app = create_app(make_settings(database_url, **overrides), setup_logging=False)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()


@pytest.fixture
def admin(make_client: Callable[..., TestClient]) -> TestClient:
    c = make_client(admin_api_key="s3cret-admin-key")
    c.headers["X-API-Key"] = "s3cret-admin-key"
    return c


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LiveServer:
    """The real app under uvicorn on a free port, for the smoke-test and deploy tests."""

    def __init__(self, settings: Settings) -> None:
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(
            create_app(settings, setup_logging=False),
            host="127.0.0.1",
            port=self.port,
            log_config=None,
            access_log=False,
            lifespan="on",
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> LiveServer:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("uvicorn didn't start")
            time.sleep(0.02)
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def live_server(database_url: str, engine: Engine) -> Iterator[LiveServer]:
    with LiveServer(make_settings(database_url)) as server:
        yield server


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent

def trace_request(data=None):
    if data is None:
        return None
    return data

def trace_request(data=None):
    if data is None:
        return None
    return data