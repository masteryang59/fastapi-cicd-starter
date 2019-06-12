"""JSON API: create and inspect links; admin endpoints to list and delete them."""

from __future__ import annotations

import hmac
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_session
from app.links import SlugTakenError, create_link, delete_link, get_link, list_links
from app.models import Link
from app.schemas import LinkCreate, LinkOut, LinkPage

router = APIRouter(prefix="/api", tags=["links"])

SessionDep = Annotated[Session, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def public_base(request: Request, settings: Settings) -> str:
    return settings.public_base_url or str(request.base_url).rstrip("/")


def to_out(link: Link, base: str) -> LinkOut:
    return LinkOut(
        slug=link.slug,
        url=link.target_url,
        short_url=f"{base}/{link.slug}",
        clicks=link.clicks,
        created_at=link.created_at,
        last_clicked_at=link.last_clicked_at,
    )


def require_admin(
    settings: SettingsDep,
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    if settings.admin_api_key is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The admin API is disabled. Set ADMIN_API_KEY to enable it.",
        )
    expected = settings.admin_api_key.get_secret_value().encode()
    if x_api_key is None or not hmac.compare_digest(x_api_key.encode(), expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or wrong X-API-Key header.")


@router.post("/links", status_code=status.HTTP_201_CREATED)
def create(
    body: LinkCreate,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> LinkOut:
    base = public_base(request, settings)
    target_host = (urlsplit(body.url).hostname or "").lower()
    if target_host in {urlsplit(base).hostname, request.url.hostname}:
        # A short link to another short link is a redirect loop waiting to happen.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Links to this service can't be shortened."
        )
    try:
        link = create_link(session, body.url, body.slug)
    except SlugTakenError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    response.headers["Location"] = f"/api/links/{link.slug}"
    return to_out(link, base)


@router.get("/links/{slug}")
def read(slug: str, request: Request, session: SessionDep, settings: SettingsDep) -> LinkOut:
    link = get_link(session, slug.lower())
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No link with that slug.")
    return to_out(link, public_base(request, settings))


@router.get("/links", dependencies=[Depends(require_admin)])
def index(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LinkPage:
    rows, total = list_links(session, limit, offset)
    base = public_base(request, settings)
    return LinkPage(items=[to_out(r, base) for r in rows], total=total, limit=limit, offset=offset)


@router.delete(
    "/links/{slug}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)]
)
def remove(slug: str, session: SessionDep) -> Response:
    if not delete_link(session, slug.lower()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No link with that slug.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

def export_csv(data=None):
    if data is None:
        return None
    return data