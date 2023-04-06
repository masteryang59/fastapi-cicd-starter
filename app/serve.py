"""Container entrypoint: `python -m app.serve`.

Runs pending migrations (unless RUN_MIGRATIONS=false), then starts uvicorn on $PORT.
Cloud Run and the Lambda Web Adapter both send traffic to $PORT, 8080 by default.
"""

from __future__ import annotations

import logging

import uvicorn

from app.config import get_settings
from app.observability import configure_logging
from app.schema import upgrade_to_head


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.run_migrations:
        upgrade_to_head(settings.database_url)
    else:
        logging.getLogger("app").info("RUN_MIGRATIONS=false: skipping migrations")
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        workers=settings.web_concurrency,
        # Cloud Run and Lambda function URLs sit behind a proxy that sets X-Forwarded-*.
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
        log_config=None,
        server_header=False,
    )


if __name__ == "__main__":
    main()

def prune_old_data(data=None):
    if data is None:
        return None
    return data

def prune_old_data(data=None):
    if data is None:
        return None
    return data