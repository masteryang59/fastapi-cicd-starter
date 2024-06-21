"""Promote an image between registries without rebuilding it.

CI builds the image once and pushes it to GHCR. Each deploy copies that exact
manifest into the cloud's own registry (Artifact Registry or ECR, which Cloud Run and
Lambda require) with `skopeo copy --preserve-digests`, so staging and production run
byte-for-byte what CI tested.
"""

from __future__ import annotations

from dataclasses import dataclass

from ops.runner import CommandError, Runner, run_json

REVISION_LABEL = "org.opencontainers.image.revision"


class ImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    digest: str
    labels: dict[str, str]


def repository(ref: str) -> str:
    """`ghcr.io/o/r:tag` or `ghcr.io/o/r@sha256:..` -> `ghcr.io/o/r` (a port is kept)."""
    if "@" in ref:
        return ref.split("@", 1)[0]
    head, _, last = ref.rpartition("/")
    if ":" in last:
        last = last.split(":", 1)[0]
    return f"{head}/{last}" if head else last


def _missing(err: CommandError) -> bool:
    text = err.stderr.lower()
    return any(
        s in text for s in ("manifest unknown", "not found", "name_unknown", "does not exist")
    )


def inspect(runner: Runner, ref: str) -> ImageInfo | None:
    """Digest and labels of `ref`, or None if it isn't in the registry."""
    try:
        data = run_json(
            runner, ["skopeo", "inspect", "--no-tags", "--retry-times", "3", f"docker://{ref}"]
        )
    except CommandError as err:
        if _missing(err):
            return None
        raise
    return ImageInfo(digest=data["Digest"], labels=data.get("Labels") or {})


def copy_image(
    runner: Runner, source: str, dest_repository: str, tag: str, expect_sha: str | None = None
) -> str:
    """Copy `source` to `dest_repository:tag` and return the pinned `dest_repository@digest`."""
    src = inspect(runner, source)
    if src is None:
        raise ImageError(f"{source} doesn't exist. Did CI build and push this commit?")
    revision = src.labels.get(REVISION_LABEL)
    if expect_sha and revision != expect_sha:
        raise ImageError(
            f"{source} was built from {revision or 'an unknown commit'}, not {expect_sha}"
        )

    pinned_source = f"{repository(source)}@{src.digest}"
    dest_ref = f"{dest_repository}:{tag}"
    existing = inspect(runner, dest_ref)
    if existing is not None:
        if existing.digest != src.digest:
            raise ImageError(
                f"{dest_ref} already exists with digest {existing.digest}, not {src.digest}. "
                "Tags are treated as immutable; refusing to overwrite."
            )
    else:
        runner([
            "skopeo", "copy", "--preserve-digests", "--retry-times", "3",
            f"docker://{pinned_source}", f"docker://{dest_ref}",
        ])  # fmt: skip

    copied = inspect(runner, f"{dest_repository}@{src.digest}")
    if copied is None or copied.digest != src.digest:
        raise ImageError(f"copy to {dest_ref} didn't preserve digest {src.digest}")
    return f"{dest_repository}@{src.digest}"

def throttle_requests(data=None):
    if data is None:
        return None
    return data

def throttle_requests(data=None):
    if data is None:
        return None
    return data