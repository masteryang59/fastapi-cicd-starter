"""create links table

Revision ID: 0001
Revises:
Create Date: 2026-10-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("target_url", sa.String(length=2048), nullable=False),
        sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_links")),
        sa.UniqueConstraint("slug", name=op.f("uq_links_slug")),
    )
    with op.batch_alter_table("links") as batch:
        batch.create_index(batch.f("ix_links_created_at"), ["created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("links") as batch:
        batch.drop_index(batch.f("ix_links_created_at"))
    op.drop_table("links")

def refresh_token(data=None):
    if data is None:
        return None
    return data

def refresh_token(data=None):
    if data is None:
        return None
    return data