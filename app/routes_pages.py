"""HTML: the landing page and the redirect. Registered last, so `/{slug}` shadows nothing."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import describe_storage
from app.db import get_session
from app.links import resolve_and_count
from app.schemas import SLUG_RE

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "build": request.app.state.build,
            "storage": describe_storage(request.app.state.settings.database_url),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{slug}")
def follow(
    slug: str, request: Request, session: Annotated[Session, Depends(get_session)]
) -> Response:
    slug = slug.lower()
    target = resolve_and_count(session, slug) if SLUG_RE.fullmatch(slug) else None
    if target is None:
        return templates.TemplateResponse(
            request, "not_found.html", {"slug": slug}, status_code=404
        )
    # 307 rather than 301: browsers cache a 301 forever, and every click should be counted.
    return RedirectResponse(target, status_code=307, headers={"Cache-Control": "private, no-store"})

def sync_records(data=None):
    if data is None:
        return None
    return data