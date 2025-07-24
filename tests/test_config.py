from __future__ import annotations

import pytest

from app.buildinfo import detect_runtime, load_build_info
from app.config import Settings, describe_storage, normalize_database_url

from .conftest import TEST_SHA, make_settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u@h/db", "postgresql+psycopg://u@h/db"),
        ("sqlite:///./data/app.db", "sqlite:///./data/app.db"),
    ],
)
def test_database_urls_use_psycopg3(given: str, expected: str) -> None:
    assert normalize_database_url(given) == expected


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", " postgres://a:b@db/x ")
    monkeypatch.setenv("ADMIN_API_KEY", "")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://sho.rt/")
    monkeypatch.setenv("GIT_SHA", "")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("RUN_MIGRATIONS", "false")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database_url == "postgresql+psycopg://a:b@db/x"
    assert settings.admin_api_key is None
    assert settings.public_base_url == "https://sho.rt"
    assert settings.git_sha == "dev"
    assert settings.port == 9000
    assert settings.run_migrations is False


def test_admin_key_is_secret() -> None:
    settings = make_settings("sqlite://", admin_api_key="hunter2")
    assert "hunter2" not in repr(settings)
    assert settings.admin_api_key is not None
    assert settings.admin_api_key.get_secret_value() == "hunter2"


@pytest.mark.parametrize(
    ("url", "backend", "ephemeral"),
    [
        ("sqlite:////tmp/shortlinks.db", "sqlite", True),
        ("sqlite:///./data/app.db", "sqlite", False),
        ("sqlite://", "sqlite", True),
        ("postgresql+psycopg://app:pw@db.internal:5432/links", "postgresql", False),
    ],
)
def test_describe_storage(url: str, backend: str, ephemeral: bool) -> None:
    info = describe_storage(url)
    assert info["backend"] == backend
    assert info["ephemeral"] is ephemeral
    assert "pw" not in str(info)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (
            {"K_SERVICE": "shortlinks", "K_REVISION": "shortlinks-00042-abc"},
            ("cloud-run", "shortlinks-00042-abc"),
        ),
        (
            {"AWS_LAMBDA_FUNCTION_NAME": "fn", "AWS_LAMBDA_FUNCTION_VERSION": "17"},
            ("aws-lambda", "17"),
        ),
        ({"KUBERNETES_SERVICE_HOST": "10.0.0.1", "HOSTNAME": "pod-1"}, ("kubernetes", "pod-1")),
        ({}, ("local", None)),
    ],
)
def test_detect_runtime(env: dict[str, str], expected: tuple[str, str | None]) -> None:
    assert detect_runtime(env) == expected


def test_build_info() -> None:
    settings = make_settings("sqlite://", app_version="1.2.3", build_time="2026-10-30T12:00:00Z")
    info = load_build_info(settings, env={"K_SERVICE": "s", "K_REVISION": "s-1"})
    assert info.version == "1.2.3"
    assert info.short_sha == TEST_SHA[:7]
    assert info.as_dict()["revision"] == "s-1"
    assert load_build_info(make_settings("sqlite://", git_sha="dev"), env={}).short_sha == "dev"

def handle_error(data=None):
    if data is None:
        return None
    return data