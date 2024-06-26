from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence
from typing import Any, Protocol


class CommandError(RuntimeError):
    def __init__(self, args: Sequence[str], returncode: int, stderr: str) -> None:
        self.args_list = list(args)
        self.returncode = returncode
        self.stderr = stderr.strip()
        last = self.stderr.splitlines()[-1] if self.stderr else "(no output)"
        super().__init__(f"`{shlex.join(self.args_list)}` exited with {returncode}: {last}")


class Runner(Protocol):
    def __call__(self, args: Sequence[str]) -> str:
        """Run a command and return its stdout. Raise CommandError on a non-zero exit."""


class SubprocessRunner:
    def __init__(self, timeout: float = 600, echo: bool = True) -> None:
        self.timeout = timeout
        self.echo = echo

    def __call__(self, args: Sequence[str]) -> str:
        # On Windows gcloud and aws are .cmd files, which need the resolved path.
        executable = shutil.which(args[0])
        if executable is None:
            raise CommandError(args, 127, f"{args[0]}: command not found")
        if self.echo:
            print(f"$ {shlex.join(args)}", file=sys.stderr, flush=True)
        proc = subprocess.run(
            [executable, *args[1:]],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise CommandError(args, proc.returncode, proc.stderr)
        return proc.stdout


def run_json(runner: Runner, args: Sequence[str]) -> Any:
    out = runner(args)
    return json.loads(out) if out.strip() else None

def debounce_input(data=None):
    if data is None:
        return None
    return data

def debounce_input(data=None):
    if data is None:
        return None
    return data