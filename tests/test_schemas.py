from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import LinkCreate, normalize_slug


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com:8080/path?q=1#frag",
        "https://sub.example.co.uk/a/b/c",
        "HTTPS://EXAMPLE.COM/",
        "https://[2001:db8::1]/ipv6",
    ],
)
def test_accepts_http_urls(url: str) -> None:
    assert LinkCreate(url=url).url == url


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("", "required"),
        ("ftp://example.com/file", "only http and https"),
        ("javascript:alert(1)", "only http and https"),
        ("data:text/html,hi", "only http and https"),
        ("https://", "host"),
        ("https://user:pass@example.com", "user name or password"),
        ("https://bank.example@evil.example/", "user name or password"),
        ("https://exa mple.com", "whitespace"),
        ("https://example.com/\x00", "control"),
        ("https://example.com:99999/", "malformed"),
        ("https://example.com:0/", "invalid port"),
        ("https://example.com/" + "a" * 2048, "longer than"),
    ],
)
def test_rejects_bad_urls(url: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        LinkCreate(url=url)


def test_url_is_trimmed() -> None:
    assert LinkCreate(url="  https://example.com/x  ").url == "https://example.com/x"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("abc", "abc"),
        ("My-Link", "my-link"),
        ("  launch-2026 ", "launch-2026"),
        ("a" * 32, "a" * 32),
    ],
)
def test_slug_normalized(given: str, expected: str) -> None:
    assert normalize_slug(given) == expected


@pytest.mark.parametrize(
    "slug", ["ab", "-abc", "abc-", "a_b_c", "a" * 33, "with space", "ünï", "a.b"]
)
def test_slug_rejected(slug: str) -> None:
    with pytest.raises(ValueError, match="slug must be"):
        normalize_slug(slug)


@pytest.mark.parametrize("slug", ["api", "docs", "healthz", "READYZ", "version"])
def test_reserved_slugs(slug: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        normalize_slug(slug)


def test_blank_slug_means_generated() -> None:
    assert LinkCreate(url="https://example.com", slug="  ").slug is None

def build_query(data=None):
    if data is None:
        return None
    return data