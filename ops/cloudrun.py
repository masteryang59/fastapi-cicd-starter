"""Blue/green deploys to Google Cloud Run with revision tags."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ops.deploy import DeployError, DeployResult, Log, Smoke, default_smoke, stderr_log
from ops.runner import CommandError, Runner, run_json

CANDIDATE_PREFIX = "c-"


@dataclass(frozen=True)
class CloudRunTarget:
    project: str
    region: str
    service: str


def candidate_tag(git_sha: str) -> str:
    # Tags must start with a letter and be short; they become part of a hostname.
    return f"{CANDIDATE_PREFIX}{git_sha[:12].lower()}"


def _traffic(service: dict[str, Any]) -> list[dict[str, Any]]:
    return list(service.get("status", {}).get("traffic") or [])


def serving_split(service: dict[str, Any]) -> dict[str, int]:
    """Revision name -> percent, for revisions that currently get traffic."""
    split: dict[str, int] = {}
    for entry in _traffic(service):
        percent = int(entry.get("percent") or 0)
        if percent > 0 and entry.get("revisionName"):
            split[entry["revisionName"]] = split.get(entry["revisionName"], 0) + percent
    return split


class CloudRunDeployer:
    def __init__(
        self,
        target: CloudRunTarget,
        runner: Runner,
        smoke: Smoke = default_smoke,
        log: Log = stderr_log,
    ) -> None:
        self.target = target
        self.runner = runner
        self.smoke = smoke
        self.log = log

    def _scope(self) -> list[str]:
        return ["--project", self.target.project, "--region", self.target.region, "--quiet"]

    def describe(self) -> dict[str, Any]:
        try:
            data = run_json(
                self.runner,
                [
                    "gcloud",
                    "run",
                    "services",
                    "describe",
                    self.target.service,
                    *self._scope(),
                    "--format=json",
                ],
            )
        except CommandError as err:
            if "could not be found" in err.stderr or "cannot find service" in err.stderr.lower():
                raise DeployError(
                    f"Cloud Run service {self.target.service} doesn't exist in "
                    f"{self.target.project}/{self.target.region}. Create it with infra/gcp first."
                ) from None
            raise
        if not isinstance(data, dict):
            raise DeployError("gcloud returned no service description")
        return data

    def _update_traffic(self, *flags: str) -> None:
        self.runner(
            [
                "gcloud",
                "run",
                "services",
                "update-traffic",
                self.target.service,
                *flags,
                *self._scope(),
            ]
        )

    def deploy(self, image: str, expect_sha: str) -> DeployResult:
        tag = candidate_tag(expect_sha)
        before = self.describe()
        previous = serving_split(before)
        self.log(f"Live traffic before deploy: {previous or 'none'}")

        # --no-traffic: the new revision starts with 0%, reachable only via its tag URL.
        self.runner([
            "gcloud", "run", "deploy", self.target.service, "--image", image,
            "--no-traffic", "--tag", tag, *self._scope(),
        ])  # fmt: skip
        after = self.describe()
        entry = next((t for t in _traffic(after) if t.get("tag") == tag), None)
        if entry is None or not entry.get("url") or not entry.get("revisionName"):
            raise DeployError(f"Deployed, but no traffic entry has tag {tag}")
        revision, candidate_url = entry["revisionName"], entry["url"]
        self.log(f"New revision {revision} at {candidate_url}")

        result = DeployResult(
            target="gcp-cloud-run",
            url=after.get("status", {}).get("url", ""),
            version=revision,
            previous=",".join(previous) or None,
            candidate_url=candidate_url,
        )

        report = self.smoke(candidate_url, expect_sha)
        result.smoke.append(report)
        self.log(report.summary())
        if not report.ok:
            self._try(lambda: self._update_traffic("--remove-tags", tag))
            raise DeployError(
                f"Revision {revision} failed its smoke test; live traffic was not changed."
            )

        self._update_traffic("--to-revisions", f"{revision}=100")
        self.log(f"Shifted 100% of traffic to {revision}")

        live = self.smoke(result.url, expect_sha)
        result.smoke.append(live)
        self.log(live.summary())
        if not live.ok:
            if previous:
                spec = ",".join(f"{rev}={pct}" for rev, pct in previous.items())
                self._update_traffic("--to-revisions", spec)
                raise DeployError(
                    f"Live URL failed after the shift; traffic rolled back to {spec}.",
                    rolled_back=True,
                )
            raise DeployError("Live URL failed after the shift, and there's no previous revision.")

        stale = [
            t["tag"]
            for t in _traffic(after)
            if str(t.get("tag", "")).startswith(CANDIDATE_PREFIX) and t["tag"] != tag
        ]
        if stale:
            self._try(lambda: self._update_traffic("--remove-tags", ",".join(sorted(stale))))
        return result

    def _try(self, action: Any) -> None:
        try:
            action()
        except CommandError as err:
            self.log(f"warning: cleanup step failed: {err}")

def detect_language(data=None):
    if data is None:
        return None
    return data

def detect_language(data=None):
    if data is None:
        return None
    return data