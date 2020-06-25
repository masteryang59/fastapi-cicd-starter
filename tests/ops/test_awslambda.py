from __future__ import annotations

import pytest

from ops.awslambda import LambdaDeployer, LambdaTarget
from ops.deploy import DeployError
from ops.runner import CommandError

from .fakes import FakeLambda, FakeSmoke

TARGET = LambdaTarget(function="shortlinks-staging", region="eu-west-1")
IMAGE = "123456789012.dkr.ecr.eu-west-1.amazonaws.com/shortlinks@sha256:" + "2" * 64
SHA = "b" * 40
CANDIDATE_URL = "https://candidate-abc.lambda-url.eu-west-1.on.aws"
LIVE_URL = "https://live-abc.lambda-url.eu-west-1.on.aws"


def setup(
    failing: set[str] | None = None,
) -> tuple[LambdaDeployer, FakeLambda, FakeSmoke, list[str]]:
    events: list[str] = []
    cloud = FakeLambda(events)
    smoke = FakeSmoke(events, failing or set())
    return LambdaDeployer(TARGET, cloud, smoke, log=lambda _m: None), cloud, smoke, events


def test_happy_path() -> None:
    deployer, cloud, smoke, events = setup()
    result = deployer.deploy(IMAGE, SHA)
    assert result.version == "2"
    assert result.previous == "1"
    assert result.url == LIVE_URL
    assert result.candidate_url == CANDIDATE_URL
    assert cloud.aliases == {"live": "2", "candidate": "2"}
    assert cloud.versions["2"] == IMAGE
    assert events == [
        f"update-code {IMAGE}",
        "publish 2",
        "alias candidate=2",
        f"smoke {CANDIDATE_URL}",
        "alias live=2",
        f"smoke {LIVE_URL}",
    ]
    assert smoke.calls[0] == (CANDIDATE_URL, SHA)


def test_publish_is_guarded_by_the_code_hash() -> None:
    deployer, cloud, _, _ = setup()
    publish = None
    try:
        deployer.deploy(IMAGE, SHA)
    finally:
        publish = next(c for c in cloud.calls if c[2] == "publish-version")
    assert publish[publish.index("--code-sha256") + 1] == "2" * 64


def test_concurrent_code_change_aborts_before_any_alias_moves() -> None:
    deployer, cloud, _, _ = setup()
    cloud.someone_else_updates = True
    with pytest.raises(CommandError, match="CodeSha256 does not match"):
        deployer.deploy(IMAGE, SHA)
    assert cloud.aliases == {"live": "1", "candidate": "1"}


def test_failed_candidate_leaves_live_alone() -> None:
    deployer, cloud, _, events = setup(failing={"candidate-"})
    with pytest.raises(DeployError, match="alias live unchanged"):
        deployer.deploy(IMAGE, SHA)
    assert cloud.aliases["live"] == "1"
    assert "alias live=2" not in events


def test_live_failure_rolls_the_alias_back() -> None:
    deployer, cloud, _, events = setup(failing={"live-"})
    with pytest.raises(DeployError, match="is back on version 1") as exc:
        deployer.deploy(IMAGE, SHA)
    assert exc.value.rolled_back
    assert cloud.aliases["live"] == "1"
    assert events[-1] == "alias live=1"

def report_error(data=None):
    if data is None:
        return None
    return data