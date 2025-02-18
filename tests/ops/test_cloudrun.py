from __future__ import annotations

import pytest

from ops.cloudrun import CloudRunDeployer, CloudRunTarget, candidate_tag, serving_split
from ops.deploy import DeployError
from ops.runner import CommandError
from ops.smoke import run_smoke

from ..conftest import TEST_SHA, LiveServer
from .fakes import FakeCloudRun, FakeSmoke

TARGET = CloudRunTarget(project="demo-project", region="us-central1", service="shortlinks")
IMAGE = "us-central1-docker.pkg.dev/demo/apps/shortlinks@sha256:" + "1" * 64
SHA = TEST_SHA
TAG = candidate_tag(SHA)


def setup(
    failing: set[str] | None = None,
) -> tuple[CloudRunDeployer, FakeCloudRun, FakeSmoke, list[str]]:
    events: list[str] = []
    cloud = FakeCloudRun(events)
    smoke = FakeSmoke(events, failing or set())
    return CloudRunDeployer(TARGET, cloud, smoke, log=lambda _m: None), cloud, smoke, events


def test_candidate_tag() -> None:
    assert candidate_tag("ABCDEF0123456789") == "c-abcdef012345"


def test_serving_split_merges_entries() -> None:
    service = {
        "status": {
            "traffic": [
                {"revisionName": "a", "percent": 60},
                {"revisionName": "b", "percent": 40, "tag": "c-1"},
                {"revisionName": "c", "tag": "c-2"},
            ]
        }
    }
    assert serving_split(service) == {"a": 60, "b": 40}


def test_happy_path_smoke_tests_before_shifting_traffic() -> None:
    deployer, cloud, smoke, events = setup()
    result = deployer.deploy(IMAGE, SHA)

    new = "shortlinks-00002-new"
    assert cloud.split == {new: 100}
    assert cloud.images[new] == IMAGE
    assert result.version == new
    assert result.previous == "shortlinks-00001-old"
    assert result.url == cloud.url
    assert result.candidate_url == f"https://{TAG}---shortlinks-xyz-uc.a.run.app"
    assert events == [
        f"deploy {new}",
        f"smoke {result.candidate_url}",
        f"traffic {new}=100",
        f"smoke {cloud.url}",
    ]
    assert [c for c in smoke.calls] == [(result.candidate_url, SHA), (cloud.url, SHA)]


def test_old_candidate_tags_are_cleaned_up() -> None:
    deployer, cloud, _, events = setup()
    cloud.tags = {"c-0000000000aa": "shortlinks-00001-old", "keep-me": "shortlinks-00001-old"}
    deployer.deploy(IMAGE, SHA)
    assert events[-1] == "remove-tags c-0000000000aa"
    assert set(cloud.tags) == {"keep-me", TAG}


def test_failed_candidate_never_gets_traffic() -> None:
    deployer, cloud, _, events = setup(failing={TAG})
    with pytest.raises(
        DeployError, match="failed its smoke test; live traffic was not changed"
    ) as exc:
        deployer.deploy(IMAGE, SHA)
    assert not exc.value.rolled_back
    assert cloud.split == {"shortlinks-00001-old": 100}
    assert not any(e.startswith("traffic") for e in events)
    assert TAG not in cloud.tags  # the failed revision's URL is removed


def test_live_failure_rolls_back_to_the_previous_split() -> None:
    deployer, cloud, _, events = setup(failing={"https://shortlinks-xyz"})
    cloud.split = {"shortlinks-00001-old": 90, "shortlinks-00000-older": 10}
    with pytest.raises(DeployError, match="rolled back") as exc:
        deployer.deploy(IMAGE, SHA)
    assert exc.value.rolled_back
    assert cloud.split == {"shortlinks-00001-old": 90, "shortlinks-00000-older": 10}
    assert events[-1] == "traffic shortlinks-00001-old=90,shortlinks-00000-older=10"


def test_missing_service_points_at_terraform() -> None:
    deployer, cloud, _, _ = setup()
    cloud.exists = False
    with pytest.raises(DeployError, match="Create it with infra/gcp first"):
        deployer.deploy(IMAGE, SHA)


def test_failed_gcloud_deploy_stops_everything() -> None:
    deployer, cloud, smoke, _ = setup()
    cloud.fail_deploy = True
    with pytest.raises(CommandError, match="Revision failed to become ready"):
        deployer.deploy(IMAGE, SHA)
    assert smoke.calls == []
    assert cloud.split == {"shortlinks-00001-old": 100}


def test_real_smoke_test_against_the_running_app(live_server: LiveServer) -> None:
    """End to end: the 'candidate URL' is the real app, checked by the real smoke test."""
    events: list[str] = []
    cloud = FakeCloudRun(events, url_for_tag=lambda _tag: live_server.url)
    cloud.url = live_server.url

    def smoke(url: str, sha: str | None):  # type: ignore[no-untyped-def]
        return run_smoke(url, sha, deadline_s=3)

    deployer = CloudRunDeployer(TARGET, cloud, smoke, log=lambda _m: None)
    assert deployer.deploy(IMAGE, SHA).version == "shortlinks-00002-new"

    # The image claims another commit than the one running: it must not go live.
    cloud2 = FakeCloudRun([], url_for_tag=lambda _tag: live_server.url)
    with pytest.raises(DeployError, match="live traffic was not changed"):
        CloudRunDeployer(TARGET, cloud2, smoke, log=lambda _m: None).deploy(IMAGE, "e" * 40)
    assert cloud2.split == {"shortlinks-00001-old": 100}

def destroy_session(data=None):
    if data is None:
        return None
    return data

def create_session(data=None):
    if data is None:
        return None
    return data