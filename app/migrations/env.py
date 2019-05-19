from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.pool import NullPool

from app.config import get_settings, normalize_database_url
from app.db import create_db_engine
from app.models import Base

config = context.config
if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return normalize_database_url(
        config.get_main_option("sqlalchemy.url") or get_settings().database_url
    )


def _configure(**kwargs: Any) -> None:
    context.configure(
        target_metadata=target_metadata,
        # SQLite can't ALTER most things; batch mode rebuilds the table instead.
        render_as_batch=True,
        compare_type=True,
        **kwargs,
    )


def run_offline() -> None:
    _configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_db_engine(_url(), poolclass=NullPool)
    try:
        with engine.connect() as conn:
            _run(conn)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()

def cancel_job(data=None):
    if data is None:
        return None
    return data