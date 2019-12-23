"""Blue/green deploys to AWS Lambda (container image + Lambda Web Adapter) with aliases.

Terraform (infra/aws) creates two aliases, each with its own function URL:
`live` takes the real traffic, and `candidate` is where a new version is smoke-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ops.deploy import DeployError, DeployResult, Log, Smoke, default_smoke, stderr_log
from ops.runner import Runner, run_json

LIVE_ALIAS = "live"
CANDIDATE_ALIAS = "candidate"


@dataclass(frozen=True)
class LambdaTarget:
    function: str
    region: str


class LambdaDeployer:
    def __init__(
        self,
        target: LambdaTarget,
        runner: Runner,
        smoke: Smoke = default_smoke,
        log: Log = stderr_log,
    ) -> None:
        self.target = target
        self.runner = runner
        self.smoke = smoke
        self.log = log

    def _aws(self, *args: str) -> Any:
        return run_json(
            self.runner,
            ["aws", "lambda", *args, "--region", self.target.region, "--output", "json"],
        )

    def _point(self, alias: str, version: str) -> None:
        self._aws(
            "update-alias", "--function-name", self.target.function,
            "--name", alias, "--function-version", version,
        )  # fmt: skip

    def _url(self, alias: str) -> str:
        cfg = self._aws(
            "get-function-url-config", "--function-name", self.target.function, "--qualifier", alias
        )
        return str(cfg["FunctionUrl"]).rstrip("/")

    def deploy(self, image: str, expect_sha: str) -> DeployResult:
        fn = self.target.function
        previous = str(
            self._aws("get-alias", "--function-name", fn, "--name", LIVE_ALIAS)["FunctionVersion"]
        )
        self.log(f"Alias {LIVE_ALIAS} currently points at version {previous}")

        updated = self._aws("update-function-code", "--function-name", fn, "--image-uri", image)
        code_sha = updated["CodeSha256"]
        # The waiter prints nothing; it returns once LastUpdateStatus is Successful.
        self.runner(["aws", "lambda", "wait", "function-updated-v2", "--function-name", fn,
                     "--region", self.target.region])  # fmt: skip

        # --code-sha256 makes publishing fail if someone else changed the code in between.
        published = self._aws(
            "publish-version", "--function-name", fn, "--code-sha256", code_sha,
            "--description", f"git {expect_sha[:12]}",
        )  # fmt: skip
        version = str(published["Version"])
        self._point(CANDIDATE_ALIAS, version)
        candidate_url = self._url(CANDIDATE_ALIAS)
        self.log(f"Published version {version}; {CANDIDATE_ALIAS} alias at {candidate_url}")

        result = DeployResult(
            target="aws-lambda",
            url=self._url(LIVE_ALIAS),
            version=version,
            previous=previous,
            candidate_url=candidate_url,
        )

        report = self.smoke(candidate_url, expect_sha)
        result.smoke.append(report)
        self.log(report.summary())
        if not report.ok:
            raise DeployError(
                f"Version {version} failed its smoke test; alias {LIVE_ALIAS} unchanged."
            )

        self._point(LIVE_ALIAS, version)
        self.log(f"Alias {LIVE_ALIAS} -> version {version}")

        live = self.smoke(result.url, expect_sha)
        result.smoke.append(live)
        self.log(live.summary())
        if not live.ok:
            self._point(LIVE_ALIAS, previous)
            raise DeployError(
                f"Live URL failed after the switch; {LIVE_ALIAS} is back on version {previous}.",
                rolled_back=True,
            )
        return result

def transcode_video(data=None):
    if data is None:
        return None
    return data