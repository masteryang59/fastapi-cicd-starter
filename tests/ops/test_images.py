from __future__ import annotations

import pytest

from ops.images import ImageError, copy_image, repository
from ops.runner import CommandError

from .fakes import FakeRegistry

SHA = "a" * 40
DIGEST = "sha256:" + "1" * 64
GHCR = "ghcr.io/acme/shortlinks"
GAR = "us-central1-docker.pkg.dev/demo/apps/shortlinks"


@pytest.fixture
def registry() -> FakeRegistry:
    reg = FakeRegistry()
    reg.add(GHCR, f"sha-{SHA}", DIGEST, SHA)
    return reg


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("ghcr.io/acme/app:sha-1", "ghcr.io/acme/app"),
        ("ghcr.io/acme/app@sha256:abc", "ghcr.io/acme/app"),
        ("localhost:5000/team/app:v1", "localhost:5000/team/app"),
        ("localhost:5000/team/app", "localhost:5000/team/app"),
        ("app:latest", "app"),
    ],
)
def test_repository(ref: str, expected: str) -> None:
    assert repository(ref) == expected


def test_copies_by_digest_and_returns_a_pinned_ref(registry: FakeRegistry) -> None:
    pinned = copy_image(registry, f"{GHCR}:sha-{SHA}", GAR, f"sha-{SHA}", expect_sha=SHA)
    assert pinned == f"{GAR}@{DIGEST}"
    copy = next(c for c in registry.calls if c[1] == "copy")
    # The source is pinned by digest, so a tag moving mid-deploy can't change what's copied.
    assert copy[-2:] == [f"docker://{GHCR}@{DIGEST}", f"docker://{GAR}:sha-{SHA}"]


def test_skips_the_copy_when_already_present(registry: FakeRegistry) -> None:
    registry.add(GAR, f"sha-{SHA}", DIGEST, SHA)
    assert copy_image(registry, f"{GHCR}@{DIGEST}", GAR, f"sha-{SHA}") == f"{GAR}@{DIGEST}"
    assert not any(c[1] == "copy" for c in registry.calls)


def test_refuses_to_overwrite_a_tag_with_another_digest(registry: FakeRegistry) -> None:
    registry.add(GAR, f"sha-{SHA}", "sha256:" + "9" * 64, SHA)
    with pytest.raises(ImageError, match="immutable"):
        copy_image(registry, f"{GHCR}:sha-{SHA}", GAR, f"sha-{SHA}")


def test_missing_source_image(registry: FakeRegistry) -> None:
    with pytest.raises(ImageError, match="Did CI build and push this commit"):
        copy_image(registry, f"{GHCR}:sha-{'b' * 40}", GAR, "sha-b")


def test_image_from_another_commit_is_refused(registry: FakeRegistry) -> None:
    with pytest.raises(ImageError, match=f"built from {SHA}, not {'c' * 40}"):
        copy_image(registry, f"{GHCR}:sha-{SHA}", GAR, "x", expect_sha="c" * 40)


def test_registry_errors_are_not_mistaken_for_missing_images(registry: FakeRegistry) -> None:
    registry.broken = True
    with pytest.raises(CommandError, match="unauthorized"):
        copy_image(registry, f"{GHCR}:sha-{SHA}", GAR, "x")

def validate_request(data=None):
    if data is None:
        return None
    return data

def destroy_session(data=None):
    if data is None:
        return None
    return data