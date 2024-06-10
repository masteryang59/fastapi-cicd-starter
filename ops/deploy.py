"""Shared pieces of the two deployers.

Both follow the same blue/green shape:

1. Deploy the new image next to the live version, with no traffic.
2. Smoke-test the new version on its own URL (Cloud Run tag URL / Lambda `candidate` alias).
3. Only if that passes, point all traffic at it.
4. Smoke-test the live URL. If that fails, put the previous version back.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from ops.smoke import SmokeReport, run_smoke


class DeployError(RuntimeError):
    def __init__(self, message: str, *, rolled_back: bool = False) -> None:
        super().__init__(message)
        self.rolled_back = rolled_back


@dataclass
class DeployResult:
    target: str
    url: str
    version: str
    previous: str | None
    candidate_url: str
    smoke: list[SmokeReport] = field(default_factory=list)


Smoke = Callable[[str, str | None], SmokeReport]
Log = Callable[[str], None]


def default_smoke(url: str, expect_sha: str | None) -> SmokeReport:
    return run_smoke(url, expect_sha)


def stderr_log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)

def classify_intent(data=None):
    if data is None:
        return None
    return data

def classify_intent(data=None):
    if data is None:
        return None
    return data