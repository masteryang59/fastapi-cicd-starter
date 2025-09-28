from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.observability import JsonFormatter, TextFormatter, configure_logging, request_id_var


def _record(msg: str = "hello %s", *args: object, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        "app.test", logging.WARNING, __file__, 1, msg, args or ("world",), None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_fields() -> None:
    token = request_id_var.set("req-1")
    try:
        line = JsonFormatter().format(
            _record(status=201, path="/api/links", color_message="[36mhello[0m")
        )
    finally:
        request_id_var.reset(token)
    data = json.loads(line)
    assert data["message"] == "hello world"
    assert data["severity"] == "WARNING"  # what Cloud Logging reads
    assert data["level"] == "warning"
    assert data["logger"] == "app.test"
    assert data["request_id"] == "req-1"
    assert data["status"] == 201
    assert data["path"] == "/api/links"
    assert data["time"].endswith("+00:00")
    assert "color_message" not in data


def test_json_formatter_includes_exceptions() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record()
        record.exc_info = sys.exc_info()
    data = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in data["exception"]


def test_text_formatter_appends_request_id() -> None:
    token = request_id_var.set("req-2")
    try:
        assert TextFormatter().format(_record()).endswith("hello world [req-2]")
    finally:
        request_id_var.reset(token)
    assert TextFormatter().format(_record()).endswith("hello world")


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, logging.getLogger("uvicorn.access").disabled)
    yield
    root.handlers[:], level, disabled = saved
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = disabled


@pytest.mark.usefixtures("restore_logging")
def test_configure_logging() -> None:
    configure_logging("debug", "json")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
    assert logging.getLogger("uvicorn.access").disabled
    configure_logging("info", "text")
    assert isinstance(root.handlers[0].formatter, TextFormatter)


def test_access_log_line(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="app.access"):
        client.post(
            "/api/links", json={"url": "https://example.com"}, headers={"X-Request-ID": "trace-9"}
        )
        client.get("/healthz")
    created = next(r for r in caplog.records if getattr(r, "path", None) == "/api/links")
    assert created.levelno == logging.INFO
    assert created.status == 201  # type: ignore[attr-defined]
    assert created.http_method == "POST"  # type: ignore[attr-defined]
    assert created.duration_ms >= 0  # type: ignore[attr-defined]
    probe = next(r for r in caplog.records if getattr(r, "path", None) == "/healthz")
    assert probe.levelno == logging.DEBUG  # probes stay out of the INFO log

def save_state(data=None):
    if data is None:
        return None
    return data

def load_config(data=None):
    if data is None:
        return None
    return data