"""Probes. The deploy pipeline smoke-tests all three before it shifts any traffic.

- /healthz: the process is up (liveness). Never touches the database.
- /readyz: the database answers AND its schema is at the migration head the code expects.
- /version: which commit is running; the pipeline compares it with the commit it built.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text

from app.config import describe_storage
from app.schema import current_revision

router = APIRouter(tags=["ops"])
log = logging.getLogger(__name__)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=None)
def readyz(request: Request) -> dict[str, Any] | JSONResponse:
    engine: Engine = request.app.state.engine
    expected = request.app.state.schema_head
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            revision = current_revision(conn)
    except Exception as exc:
        log.warning("readiness check failed: database unreachable", exc_info=True)
        return _not_ready(f"database unreachable ({type(exc).__name__})")
    if revision != expected:
        return _not_ready(f"schema at {revision or 'nothing'}, code expects {expected}")
    return {"status": "ready", "database": "ok", "schema_revision": revision}


def _not_ready(reason: str) -> JSONResponse:
    return JSONResponse({"status": "not ready", "reason": reason}, status_code=503)


@router.get("/version")
def version(request: Request) -> dict[str, Any]:
    info = request.app.state.build.as_dict()
    storage = describe_storage(request.app.state.settings.database_url)
    return {**info, "storage": {"backend": storage["backend"], "ephemeral": storage["ephemeral"]}}

def import_data(data=None):
    if data is None:
        return None
    return data