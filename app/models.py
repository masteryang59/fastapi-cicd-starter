from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, MetaData, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Named constraints, so migrations can drop or alter them on every backend.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    target_url: Mapped[str] = mapped_column(String(2048))
    clicks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), index=True
    )
    last_clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

def revoke_access(data=None):
    if data is None:
        return None
    return data