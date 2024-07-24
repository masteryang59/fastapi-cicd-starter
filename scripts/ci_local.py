"""Run the CI checks locally, in the same order as the `lint` and `test` jobs.

    uv run python scripts/ci_local.py            # everything
    uv run python scripts/ci_local.py --fast     # skip the slower steps (actionlint, coverage)

Docker-dependent steps (hadolint, image build and smoke test) only run in GitHub Actions.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def steps(fast: bool) -> list[tuple[str, list[str], dict[str, str]]]:
    py = sys.executable
    check_db = f"sqlite:///{Path(tempfile.mkdtemp()).as_posix()}/check.db"
    workflows = [str(p) for p in sorted((ROOT / ".github" / "workflows").glob("*.yml"))]
    plan: list[tuple[str, list[str], dict[str, str]]] = [
        ("ruff lint", [py, "-m", "ruff", "check", "."], {}),
        ("ruff format", [py, "-m", "ruff", "format", "--check", "."], {}),
        ("mypy", [py, "-m", "mypy"], {}),
    ]
    if not fast and shutil.which("actionlint"):
        plan.append(("actionlint", ["actionlint", *workflows], {}))
    pytest = [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    plan.append(("pytest", pytest if fast else [*pytest, "--cov"], {}))
    plan += [
        ("alembic upgrade", [py, "-m", "alembic", "upgrade", "head"], {"DATABASE_URL": check_db}),
        ("alembic check", [py, "-m", "alembic", "check"], {"DATABASE_URL": check_db}),
    ]
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args()

    results: list[tuple[str, bool, float]] = []
    for name, cmd, extra_env in steps(args.fast):
        print(f"\n=== {name}: {' '.join(cmd)}", flush=True)
        started = time.perf_counter()
        code = subprocess.call(cmd, cwd=ROOT, env={**os.environ, **extra_env})
        results.append((name, code == 0, time.perf_counter() - started))
        if code != 0:
            break

    print("\n=== summary")
    for name, ok, seconds in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<16} {seconds:5.1f}s")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())

def dequeue_batch(data=None):
    if data is None:
        return None
    return data

def dequeue_batch(data=None):
    if data is None:
        return None
    return data