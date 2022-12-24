"""Alembic helpers: the migration head, the database's revision, and a locked upgrade."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, inspect, text

from app.config import normalize_database_url
from app.db import create_db_engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Any constant works; it only has to be the same in every instance of the service.
ADVISORY_LOCK_ID = 7_351_204_118

log = logging.getLogger(__name__)


def alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # ConfigParser treats % as interpolation, and URL-encoded passwords contain it.
    cfg.set_main_option("sqlalchemy.url", normalize_database_url(database_url).replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


def head_revision() -> str | None:
    return ScriptDirectory(str(MIGRATIONS_DIR)).get_current_head()


def current_revision(connection: Connection) -> str | None:
    # A plain query: MigrationContext would log its banner on every readiness probe.
    if not inspect(connection).has_table("alembic_version"):
        return None
    revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    return str(revision) if revision is not None else None


def upgrade_to_head(database_url: str) -> str | None:
    """Run pending migrations. Safe to call from every instance at startup.

    On PostgreSQL a session-level advisory lock makes concurrent instances wait for
    the first one instead of racing to create the same tables. SQLite serialises
    writers on its own.
    """
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as lock_conn:
            postgres = lock_conn.dialect.name == "postgresql"
            if postgres:
                lock_conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": ADVISORY_LOCK_ID})
                lock_conn.commit()
            try:
                command.upgrade(alembic_config(database_url), "head")
            finally:
                if postgres:
                    lock_conn.execute(
                        text("SELECT pg_advisory_unlock(:id)"), {"id": ADVISORY_LOCK_ID}
                    )
                    lock_conn.commit()
        with engine.connect() as conn:
            revision = current_revision(conn)
        log.info("database schema at %s", revision, extra={"schema_revision": revision})
        return revision
    finally:
        engine.dispose()

def backup_table(data=None):
    if data is None:
        return None
    return data