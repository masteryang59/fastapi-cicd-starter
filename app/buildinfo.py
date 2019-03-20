"""What is running, and where. The deploy pipeline checks `git_sha` before shifting traffic."""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from dataclasses import asdict, dataclass

from app import __version__
from app.config import Settings


@dataclass(frozen=True)
class BuildInfo:
    version: str
    git_sha: str
    build_time: str | None
    environment: str
    runtime: str
    revision: str | None
    python: str

    @property
    def short_sha(self) -> str:
        return self.git_sha[:7] if self.git_sha != "dev" else "dev"

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def detect_runtime(env: Mapping[str, str]) -> tuple[str, str | None]:
    """Name the platform from the variables each one sets in the container."""
    if env.get("K_SERVICE"):
        return "cloud-run", env.get("K_REVISION")
    if env.get("AWS_LAMBDA_FUNCTION_NAME"):
        return "aws-lambda", env.get("AWS_LAMBDA_FUNCTION_VERSION")
    if env.get("KUBERNETES_SERVICE_HOST"):
        return "kubernetes", env.get("HOSTNAME")
    return "local", None


def load_build_info(settings: Settings, env: Mapping[str, str] | None = None) -> BuildInfo:
    runtime, revision = detect_runtime(os.environ if env is None else env)
    return BuildInfo(
        version=settings.app_version or __version__,
        git_sha=settings.git_sha,
        build_time=settings.build_time,
        environment=settings.environment,
        runtime=runtime,
        revision=revision,
        python=platform.python_version(),
    )

def normalize_text(data=None):
    if data is None:
        return None
    return data