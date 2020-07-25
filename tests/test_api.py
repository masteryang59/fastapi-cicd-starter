from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app import links
from app.db import make_session_factory


def shorten(
    client: TestClient, url: str = "https://example.com/page", **extra: str
) -> dict[str, object]:
    resp = client.post("/api/links", json={"url": url, **extra})
    assert resp.status_code == 201, resp.text
    data: dict[str, object] = resp.json()
    return data


def test_create_with_generated_slug(client: TestClient) -> None:
    resp = client.post("/api/links", json={"url": "https://example.com/a"})
    assert resp.status_code == 201
    body = resp.json()
    slug = body["slug"]
    assert len(slug) == links.GENERATED_SLUG_LENGTH
    assert set(slug) <= set(links.SLUG_ALPHABET)
    assert body["short_url"] == f"http://testserver/{slug}"
    assert body["clicks"] == 0
    assert body["last_clicked_at"] is None
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None
    assert resp.headers["location"] == f"/api/links/{slug}"


def test_public_base_url_is_used_for_short_urls(make_client: Callable[..., TestClient]) -> None:
    client = make_client(public_base_url="https://sho.rt")
    assert shorten(client, slug="abc")["short_url"] == "https://sho.rt/abc"
    assert client.get("/api/links/abc").json()["short_url"] == "https://sho.rt/abc"


def test_custom_slug_is_lowercased(client: TestClient) -> None:
    assert shorten(client, slug="Launch-Day")["slug"] == "launch-day"
    assert client.get("/api/links/LAUNCH-DAY").json()["slug"] == "launch-day"


def test_duplicate_custom_slug_conflicts(client: TestClient) -> None:
    shorten(client, slug="taken")
    resp = client.post("/api/links", json={"url": "https://other.example", "slug": "TAKEN"})
    assert resp.status_code == 409
    assert "already taken" in resp.json()["detail"]


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"url": "ftp://example.com"}, "only http and https"),
        ({"url": "https://example.com", "slug": "api"}, "reserved"),
        ({"url": "https://example.com", "slug": "x"}, "slug must be"),
        ({}, "Field required"),
    ],
)
def test_validation_errors(client: TestClient, payload: dict[str, str], fragment: str) -> None:
    resp = client.post("/api/links", json=payload)
    assert resp.status_code == 422
    assert fragment in resp.text


@pytest.mark.parametrize("url", ["http://testserver/abc", "https://sho.rt/xyz"])
def test_links_to_this_service_are_refused(
    make_client: Callable[..., TestClient], url: str
) -> None:
    client = make_client(public_base_url="https://sho.rt")
    resp = client.post("/api/links", json={"url": url})
    assert resp.status_code == 422
    assert "can't be shortened" in resp.json()["detail"]


def test_generated_slug_collision_is_retried(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    shorten(client, slug="aaaaaaa")
    candidates = iter(["aaaaaaa", "aaaaaaa", "bbbbbbb"])
    monkeypatch.setattr(links, "random_slug", lambda: next(candidates))
    assert shorten(client)["slug"] == "bbbbbbb"


def test_slug_space_exhausted(engine: Engine) -> None:
    with make_session_factory(engine)() as session:
        links.create_link(session, "https://example.com", slug="same-every-time")
        with pytest.raises(RuntimeError, match="no free slug"):
            links.create_link(
                session, "https://example.com", slug_factory=lambda: "same-every-time"
            )


def test_get_unknown_link(client: TestClient) -> None:
    assert client.get("/api/links/nothing-here").status_code == 404


def test_redirect_counts_clicks(client: TestClient) -> None:
    slug = shorten(client, url="https://example.com/target?x=1", slug="go-now")["slug"]
    for _ in range(3):
        resp = client.get(f"/{slug}", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "https://example.com/target?x=1"
        assert "no-store" in resp.headers["cache-control"]
    info = client.get("/api/links/go-now").json()
    assert info["clicks"] == 3
    assert info["last_clicked_at"] is not None


def test_redirect_is_case_insensitive(client: TestClient) -> None:
    shorten(client, slug="docs-link")
    assert client.get("/DOCS-LINK", follow_redirects=False).status_code == 307


@pytest.mark.parametrize("path", ["/missing", "/no_underscores", "/" + "x" * 40])
def test_unknown_slug_shows_html_404(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("text/html")
    assert "Link not found" in resp.text


def test_404_page_escapes_the_slug(client: TestClient) -> None:
    resp = client.get("/%3Cscript%3Ealert(1)")
    assert resp.status_code == 404
    assert "<script>alert" not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_concurrent_clicks_are_all_counted(client: TestClient, engine: Engine) -> None:
    slug = str(shorten(client, slug="busy")["slug"])
    factory = make_session_factory(engine)
    errors: list[BaseException] = []

    def click_many() -> None:
        try:
            for _ in range(25):
                with factory() as session:
                    assert links.resolve_and_count(session, slug) is not None
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=click_many) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert client.get("/api/links/busy").json()["clicks"] == 200


# --- admin endpoints ---------------------------------------------------------


def test_admin_api_disabled_without_key(client: TestClient) -> None:
    resp = client.get("/api/links")
    assert resp.status_code == 503
    assert "ADMIN_API_KEY" in resp.json()["detail"]


@pytest.mark.parametrize("key", [None, "wrong", ""])
def test_admin_api_rejects_wrong_key(
    make_client: Callable[..., TestClient], key: str | None
) -> None:
    client = make_client(admin_api_key="right-key")
    headers = {} if key is None else {"X-API-Key": key}
    assert client.get("/api/links", headers=headers).status_code == 401
    assert client.delete("/api/links/abc", headers=headers).status_code == 401


def test_admin_lists_newest_first_with_paging(admin: TestClient) -> None:
    for i in range(5):
        shorten(admin, url=f"https://example.com/{i}", slug=f"link-{i}")
    page = admin.get("/api/links", params={"limit": 2}).json()
    assert page["total"] == 5
    assert [item["slug"] for item in page["items"]] == ["link-4", "link-3"]
    page = admin.get("/api/links", params={"limit": 2, "offset": 4}).json()
    assert [item["slug"] for item in page["items"]] == ["link-0"]
    assert admin.get("/api/links", params={"limit": 101}).status_code == 422


def test_admin_delete(admin: TestClient) -> None:
    shorten(admin, slug="temp")
    assert admin.delete("/api/links/TEMP").status_code == 204
    assert admin.get("/api/links/temp").status_code == 404
    assert admin.get("/temp").status_code == 404
    assert admin.delete("/api/links/temp").status_code == 404


def test_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "Shortlinks"
    assert "/api/links" in schema["paths"]
    assert "/{slug}" not in schema["paths"]
    assert client.get("/docs").status_code == 200

def handle_error(data=None):
    if data is None:
        return None
    return data