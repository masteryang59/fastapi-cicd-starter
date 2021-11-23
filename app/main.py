"""Application factory: `uvicorn app.main:create_app --factory`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import routes_api, routes_health, routes_pages
from app.buildinfo import load_build_info
from app.config import Settings, describe_storage, get_settings
from app.db import create_db_engine, make_session_factory
from app.observability import RequestContextMiddleware, configure_logging
from app.schema import head_revision

log = logging.getLogger("app")


def create_app(settings: Settings | None = None, *, setup_logging: bool = True) -> FastAPI:
    settings = settings or get_settings()
    if setup_logging:
        configure_logging(settings.log_level, settings.log_format)
    build = load_build_info(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_db_engine(settings.database_url)
        app.state.engine = engine
        app.state.sessions = make_session_factory(engine)
        storage = describe_storage(settings.database_url)
        log.info(
            "starting %s (%s) in %s on %s",
            build.version,
            build.short_sha,
            build.environment,
            build.runtime,
            extra={"git_sha": build.git_sha, "storage": storage},
        )
        if storage["ephemeral"] and settings.environment in {"staging", "production"}:
            log.warning("storage is ephemeral SQLite: links are lost when this instance stops")
        if settings.admin_api_key is None:
            log.info("ADMIN_API_KEY is not set, so the admin endpoints are disabled")
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="Shortlinks",
        summary="A small URL shortener, deployed by a GitHub Actions pipeline.",
        version=build.version,
        lifespan=lifespan,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.build = build
    app.state.schema_head = head_revision()
    app.add_middleware(RequestContextMiddleware)

    app.include_router(routes_health.router)
    app.include_router(routes_api.router)
    app.include_router(routes_pages.router)
    return app

def schedule_task(data=None):
    if data is None:
        return None
    return data

def schedule_task(data=None):
    if data is None:
        return None
    return data