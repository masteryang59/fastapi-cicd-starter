"""Smoke test a running deployment: is it up, ready, and running the commit we built?

Cold starts and traffic propagation take a few seconds, so failing checks are retried
until a deadline. A wrong commit is retried too: right after a traffic shift some
requests can still reach the old revision.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

USER_AGENT = "fastapi-cicd-starter-smoke/1"


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    content_type: str


Fetch = Callable[[str, float], HttpResponse]


def urllib_fetch(url: str, timeout: float) -> HttpResponse:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return HttpResponse(resp.status, resp.read(), resp.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as err:
        return HttpResponse(err.code, err.read(), err.headers.get("Content-Type", ""))


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class SmokeReport:
    url: str
    ok: bool = False
    attempts: int = 0
    elapsed: float = 0.0
    checks: list[Check] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [f"{status} {self.url} ({self.attempts} attempts, {self.elapsed:.1f}s)"]
        lines += [f"  {'ok ' if c.ok else 'ERR'} {c.name}: {c.detail}" for c in self.checks]
        return "\n".join(lines)


def _json(resp: HttpResponse) -> dict[str, object] | None:
    try:
        data = json.loads(resp.body)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def run_checks(base_url: str, expect_sha: str | None, fetch: Fetch, timeout: float) -> list[Check]:
    base = base_url.rstrip("/")
    checks: list[Check] = []

    def get(path: str) -> HttpResponse | str:
        try:
            return fetch(base + path, timeout)
        except (OSError, urllib.error.URLError) as exc:  # refused, DNS, TLS, timeout
            return f"request failed: {exc}"

    resp = get("/healthz")
    if isinstance(resp, str):
        checks.append(Check("healthz", False, resp))
    else:
        body = _json(resp) or {}
        ok = resp.status == 200 and body.get("status") == "ok"
        checks.append(Check("healthz", ok, f"HTTP {resp.status}"))

    resp = get("/readyz")
    if isinstance(resp, str):
        checks.append(Check("readyz", False, resp))
    else:
        body = _json(resp) or {}
        ok = resp.status == 200 and body.get("status") == "ready"
        detail = f"HTTP {resp.status}" + ("" if ok else f" {body.get('reason', '')}".rstrip())
        checks.append(Check("readyz", ok, detail))

    resp = get("/version")
    if isinstance(resp, str):
        checks.append(Check("version", False, resp))
    else:
        body = _json(resp) or {}
        running = str(body.get("git_sha", "?"))
        if resp.status != 200:
            checks.append(Check("version", False, f"HTTP {resp.status}"))
        elif expect_sha and running != expect_sha:
            checks.append(
                Check("version", False, f"running {running[:12]}, expected {expect_sha[:12]}")
            )
        else:
            checks.append(Check("version", True, f"git_sha {running[:12]}"))

    resp = get("/")
    if isinstance(resp, str):
        checks.append(Check("home", False, resp))
    else:
        ok = resp.status == 200 and resp.content_type.startswith("text/html")
        checks.append(Check("home", ok, f"HTTP {resp.status} {resp.content_type}".rstrip()))
    return checks


def run_smoke(
    base_url: str,
    expect_sha: str | None = None,
    *,
    deadline_s: float = 180,
    request_timeout_s: float = 10,
    fetch: Fetch = urllib_fetch,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> SmokeReport:
    report = SmokeReport(url=base_url)
    started = clock()
    delay = 2.0
    while True:
        report.attempts += 1
        report.checks = run_checks(base_url, expect_sha, fetch, request_timeout_s)
        report.ok = all(c.ok for c in report.checks)
        report.elapsed = clock() - started
        if report.ok or report.elapsed + delay > deadline_s:
            return report
        sleep(delay)
        delay = min(delay * 1.5, 10.0)


SmokeFn = Callable[[str, str | None], SmokeReport]

def queue_message(data=None):
    if data is None:
        return None
    return data

def queue_message(data=None):
    if data is None:
        return None
    return data