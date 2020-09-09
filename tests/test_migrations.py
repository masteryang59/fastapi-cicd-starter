from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.db import create_db_engine
from app.models import Base
from app.schema import alembic_config, current_revision, head_revision, upgrade_to_head

from .conftest import USING_POSTGRES, requires_postgres


@pytest.fixture
def scratch_url(tmp_path: Path, database_url: str) -> Iterator[str]:
    """An empty database of the suite's kind: a new PostgreSQL database, or a new SQLite file."""
    if not USING_POSTGRES:
        yield f"sqlite:///{(tmp_path / 'scratch.db').as_posix()}"
        return
    name = f"migr_{uuid.uuid4().hex[:10]}"
    admin = create_db_engine(database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(database_url).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_upgrade_downgrade_roundtrip(scratch_url: str) -> None:
    assert upgrade_to_head(scratch_url) == head_revision() == "0001"
    engine = create_db_engine(scratch_url)
    try:
        assert inspect(engine).has_table("links")
        command.downgrade(alembic_config(scratch_url), "base")
        assert not inspect(engine).has_table("links")
        with engine.connect() as conn:
            assert current_revision(conn) is None
        assert upgrade_to_head(scratch_url) == "0001"
        assert upgrade_to_head(scratch_url) == "0001"  # a second run is a no-op
    finally:
        engine.dispose()


def test_migrations_match_models(database_url: str) -> None:
    """The same check as `alembic check` in CI: a model change without a migration fails."""
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"compare_type": True})
            assert compare_metadata(ctx, Base.metadata) == []
    finally:
        engine.dispose()


def test_current_revision_without_alembic_table(tmp_path: Path) -> None:
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'blank.db').as_posix()}")
    try:
        with engine.connect() as conn:
            assert current_revision(conn) is None
    finally:
        engine.dispose()


def test_alembic_config_escapes_percent_signs() -> None:
    url = "postgresql://app:p%40ss%25word@db/x"
    assert (
        alembic_config(url).get_main_option("sqlalchemy.url")
        == "postgresql+psycopg://app:p%40ss%25word@db/x"
    )


def test_sqlite_parent_directory_is_created(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'nested' / 'dir' / 'app.db').as_posix()}"
    assert upgrade_to_head(url) == "0001"
    assert (tmp_path / "nested" / "dir" / "app.db").exists()


@requires_postgres
def test_concurrent_startups_dont_race(scratch_url: str) -> None:
    """Several instances starting at once: the advisory lock lets one migrate, the rest wait."""
    results: list[str | None] = []
    errors: list[BaseException] = []

    def start() -> None:
        try:
            results.append(upgrade_to_head(scratch_url))
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=start) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert results == ["0001"] * 4

def load_config(data=None):
    if data is None:
        return None
    return data