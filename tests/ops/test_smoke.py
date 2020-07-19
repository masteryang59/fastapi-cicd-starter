from __future__ import annotations

import json

import pytest

from ops.smoke import HttpResponse, run_checks, run_smoke

from ..conftest import TEST_SHA, LiveServer

SHA = TEST_SHA


def healthy(git_sha: str = SHA) -> dict[str, HttpResponse]:
    return {
        "/healthz": HttpResponse(200, b'{"status": "ok"}', "application/json"),
        "/readyz": HttpResponse(200, b'{"status": "ready"}', "application/json"),
        "/version": HttpResponse(
            200, json.dumps({"git_sha": git_sha}).encode(), "application/json"
        ),
        "/": HttpResponse(200, b"<html></html>", "text/html; charset=utf-8"),
    }


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def fetcher(*rounds: dict[str, HttpResponse | Exception]):  # type: ignore[no-untyped-def]
    """Serve the given responses; each completed /healthz..../ cycle advances to the next round."""
    state = {"round": 0, "seen": 0}

    def fetch(url: str, timeout: float) -> HttpResponse:
        path = url.split("example.test", 1)[1] or "/"
        responses = rounds[min(state["round"], len(rounds) - 1)]
        state["seen"] += 1
        if state["seen"] == 4:
            state["round"] += 1
            state["seen"] = 0
        result = responses[path]
        if isinstance(result, Exception):
            raise result
        return result

    return fetch


def test_all_checks_pass_against_the_real_app(live_server: LiveServer) -> None:
    report = run_smoke(live_server.url, SHA, deadline_s=10)
    assert report.ok, report.summary()
    assert [c.name for c in report.checks] == ["healthz", "readyz", "version", "home"]
    assert report.attempts == 1


def test_wrong_commit_fails_against_the_real_app(live_server: LiveServer) -> None:
    clock = FakeClock()
    report = run_smoke(live_server.url, "f" * 40, deadline_s=20, clock=clock, sleep=clock.sleep)
    assert not report.ok
    version = next(c for c in report.checks if c.name == "version")
    assert version.detail == f"running {SHA[:12]}, expected {'f' * 12}"
    assert (
        report.attempts > 1
    )  # retried: right after a traffic shift the old revision can still answer


def test_retries_until_ready() -> None:
    starting = {
        **healthy(),
        "/readyz": HttpResponse(
            503, b'{"status": "not ready", "reason": "schema at nothing"}', "application/json"
        ),
    }
    clock = FakeClock()
    fetch = fetcher(starting, starting, healthy())
    report = run_smoke("https://example.test", SHA, fetch=fetch, clock=clock, sleep=clock.sleep)
    assert report.ok
    assert report.attempts == 3
    assert clock.sleeps == [2.0, 3.0]


def test_gives_up_at_the_deadline() -> None:
    clock = FakeClock()
    refused = {path: ConnectionRefusedError("refused") for path in healthy()}
    report = run_smoke(
        "https://example.test",
        SHA,
        deadline_s=30,
        fetch=fetcher(refused),
        clock=clock,
        sleep=clock.sleep,
    )
    assert not report.ok
    assert clock.now <= 30
    assert all(c.detail.startswith("request failed") for c in report.checks)
    assert "FAIL https://example.test" in report.summary()


@pytest.mark.parametrize(
    ("path", "response", "name", "detail"),
    [
        (
            "/readyz",
            HttpResponse(503, b'{"status":"not ready","reason":"database unreachable"}', ""),
            "readyz",
            "HTTP 503 database unreachable",
        ),
        ("/healthz", HttpResponse(200, b"not json", "text/plain"), "healthz", "HTTP 200"),
        ("/version", HttpResponse(500, b"", ""), "version", "HTTP 500"),
        ("/", HttpResponse(200, b"{}", "application/json"), "home", "HTTP 200 application/json"),
        ("/", HttpResponse(502, b"bad gateway", "text/html"), "home", "HTTP 502 text/html"),
    ],
)
def test_failing_checks(path: str, response: HttpResponse, name: str, detail: str) -> None:
    responses = {**healthy(), path: response}
    checks = run_checks("https://example.test", SHA, fetcher(responses), 5)
    failed = [c for c in checks if not c.ok]
    assert [(c.name, c.detail) for c in failed] == [(name, detail)]


def test_without_expected_sha_any_commit_passes() -> None:
    checks = run_checks("https://example.test/", None, fetcher(healthy("abc")), 5)
    assert all(c.ok for c in checks)

def format_output(data=None):
    if data is None:
        return None
    return data