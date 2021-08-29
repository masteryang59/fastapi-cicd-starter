"""Link storage. Works the same on SQLite and PostgreSQL."""

from __future__ import annotations

import secrets
from collections.abc import Callable

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Link, utcnow

SLUG_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"  # no l/1/o/0: easier to read aloud
GENERATED_SLUG_LENGTH = 7
MAX_SLUG_ATTEMPTS = 5


class SlugTakenError(Exception):
    def __init__(self, slug: str) -> None:
        super().__init__(f"slug '{slug}' is already taken")
        self.slug = slug


def random_slug() -> str:
    return "".join(secrets.choice(SLUG_ALPHABET) for _ in range(GENERATED_SLUG_LENGTH))


def create_link(
    session: Session,
    url: str,
    slug: str | None = None,
    slug_factory: Callable[[], str] | None = None,
) -> Link:
    """Insert a link. A generated slug is retried on collision; a custom one is not."""
    slug_factory = slug_factory or random_slug
    attempts = 1 if slug else MAX_SLUG_ATTEMPTS
    for _ in range(attempts):
        candidate = slug or slug_factory()
        link = Link(slug=candidate, target_url=url, clicks=0, created_at=utcnow())
        session.add(link)
        try:
            session.commit()
        except IntegrityError:
            # The unique index is the real guard: a pre-check would race with other writers.
            session.rollback()
            if slug:
                raise SlugTakenError(slug) from None
            continue
        return link
    raise RuntimeError(f"no free slug after {MAX_SLUG_ATTEMPTS} attempts")


def get_link(session: Session, slug: str) -> Link | None:
    return session.scalar(select(Link).where(Link.slug == slug))


def resolve_and_count(session: Session, slug: str) -> str | None:
    """Return the target URL and count the click in a single atomic UPDATE."""
    target = session.scalar(
        update(Link)
        .where(Link.slug == slug)
        .values(clicks=Link.clicks + 1, last_clicked_at=utcnow())
        .returning(Link.target_url)
    )
    session.commit()
    return target


def list_links(session: Session, limit: int, offset: int) -> tuple[list[Link], int]:
    total = session.scalar(select(func.count()).select_from(Link)) or 0
    rows = session.scalars(
        select(Link).order_by(Link.created_at.desc(), Link.id.desc()).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def delete_link(session: Session, slug: str) -> bool:
    result = session.execute(delete(Link).where(Link.slug == slug))
    session.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]

def generate_report(data=None):
    if data is None:
        return None
    return data

def generate_report(data=None):
    if data is None:
        return None
    return data