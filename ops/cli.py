"""`python3 -m ops <command>`. Used by .github/workflows/deploy.yml, and works locally too."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence

from ops.awslambda import LambdaDeployer, LambdaTarget
from ops.cloudrun import CloudRunDeployer, CloudRunTarget
from ops.deploy import DeployError, DeployResult, Smoke, default_smoke
from ops.images import ImageError, copy_image
from ops.runner import CommandError, Runner, SubprocessRunner
from ops.smoke import run_smoke

# GitHub environment variables each target needs. infra/*/outputs.tf prints them.
REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "gcp": (
        "GCP_PROJECT_ID",
        "GCP_REGION",
        "GCP_WORKLOAD_IDENTITY_PROVIDER",
        "GCP_SERVICE_ACCOUNT",
        "GAR_REPOSITORY",
        "CLOUD_RUN_SERVICE",
    ),
    "aws": ("AWS_REGION", "AWS_ROLE_ARN", "ECR_REPOSITORY", "LAMBDA_FUNCTION"),
}


def missing_vars(target: str, env: Mapping[str, str]) -> list[str]:
    return [name for name in REQUIRED_VARS[target] if not env.get(name, "").strip()]


def github_output(name: str, value: str, env: Mapping[str, str] = os.environ) -> None:
    path = env.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def github_summary(markdown: str, env: Mapping[str, str] = os.environ) -> None:
    path = env.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown.rstrip() + "\n")


def error(message: str) -> None:
    # `::error::` becomes an annotation on the run page in GitHub Actions.
    prefix = "::error::" if os.environ.get("GITHUB_ACTIONS") == "true" else "error: "
    print(prefix + message, file=sys.stderr, flush=True)


def summarize(result: DeployResult, environment: str, image: str, sha: str) -> str:
    rows = [
        ("Environment", environment),
        ("Target", result.target),
        ("Commit", f"`{sha[:12]}`"),
        ("Image", f"`{image}`"),
        ("New version", f"`{result.version}`"),
        ("Previous", f"`{result.previous}`" if result.previous else "none"),
        ("URL", result.url),
    ]
    table = "\n".join(f"| {k} | {v} |" for k, v in rows)
    smoke = "\n".join(f"<pre>{r.summary()}</pre>" for r in result.smoke)
    return f"### Deployed to {environment}\n\n| | |\n| --- | --- |\n{table}\n\n{smoke}\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ops", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "check-config", help="fail early, with a clear message, if deploy variables are missing"
    )
    p.add_argument("--target", choices=sorted(REQUIRED_VARS), required=True)

    p = sub.add_parser("smoke", help="smoke-test a running deployment")
    p.add_argument("--url", required=True)
    p.add_argument("--expect-sha", help="fail unless /version reports this commit")
    p.add_argument(
        "--deadline", type=float, default=180, help="seconds to keep retrying (default 180)"
    )

    p = sub.add_parser("copy-image", help="copy an image to another registry, keeping its digest")
    p.add_argument("--source", required=True, help="e.g. ghcr.io/owner/repo:sha-<commit>")
    p.add_argument("--dest", required=True, help="destination repository, without a tag")
    p.add_argument("--tag", required=True)
    p.add_argument("--expect-sha", help="fail unless the image's revision label is this commit")

    p = sub.add_parser("deploy", help="blue/green deploy an image (by digest) and smoke-test it")
    p.add_argument("--target", choices=sorted(REQUIRED_VARS), required=True)
    p.add_argument("--image", required=True, help="registry/repo@sha256:...")
    p.add_argument("--expect-sha", required=True)
    p.add_argument("--environment", default=os.environ.get("DEPLOY_ENVIRONMENT", "unknown"))
    return parser


def main(
    argv: Sequence[str] | None = None, runner: Runner | None = None, smoke: Smoke | None = None
) -> int:
    args = build_parser().parse_args(argv)
    runner = runner or SubprocessRunner()
    smoke = smoke or default_smoke
    env = os.environ

    if args.command == "check-config":
        missing = missing_vars(args.target, env)
        if missing:
            error(
                f"DEPLOY_TARGET is {args.target}, but these variables aren't set for this "
                f"environment: {', '.join(missing)}. Add them under Settings > Environments."
            )
            return 2
        print(f"{args.target}: all {len(REQUIRED_VARS[args.target])} deploy variables are set")
        return 0

    if args.command == "smoke":
        report = run_smoke(args.url, args.expect_sha, deadline_s=args.deadline)
        print(report.summary())
        return 0 if report.ok else 1

    try:
        if args.command == "copy-image":
            pinned = copy_image(runner, args.source, args.dest, args.tag, args.expect_sha)
            print(pinned)
            github_output("image", pinned)
            return 0

        if args.command == "deploy":
            if "@sha256:" not in args.image:
                error("deploy takes an image pinned by digest (repo@sha256:...), not a tag")
                return 2
            if args.target == "gcp":
                gcp = CloudRunTarget(
                    env["GCP_PROJECT_ID"], env["GCP_REGION"], env["CLOUD_RUN_SERVICE"]
                )
                result = CloudRunDeployer(gcp, runner, smoke).deploy(args.image, args.expect_sha)
            else:
                aws = LambdaTarget(env["LAMBDA_FUNCTION"], env["AWS_REGION"])
                result = LambdaDeployer(aws, runner, smoke).deploy(args.image, args.expect_sha)
            github_output("url", result.url)
            github_output("version", result.version)
            github_output("previous", result.previous or "")
            github_summary(summarize(result, args.environment, args.image, args.expect_sha))
            print(f"Deployed {result.version} to {result.url}")
            return 0
    except (DeployError, ImageError, CommandError) as exc:
        error(str(exc))
        return 1
    except KeyError as exc:
        error(f"missing environment variable {exc.args[0]}; run `check-config` first")
        return 2
    raise AssertionError(f"unhandled command {args.command}")  # pragma: no cover

def extract_text(data=None):
    if data is None:
        return None
    return data

def extract_text(data=None):
    if data is None:
        return None
    return data