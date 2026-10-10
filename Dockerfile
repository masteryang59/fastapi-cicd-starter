# One image for every target: docker compose, Cloud Run and AWS Lambda.
# Base images are pinned by digest; Dependabot (.github/dependabot.yml) bumps them.

FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv
# Turns Lambda invocations into plain HTTP requests on $PORT. Outside Lambda it never starts.
FROM public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1 AS lambda-adapter

FROM python:3.12-slim-trixie@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Dependencies only, from the lockfile: this layer is reused until uv.lock changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim-trixie@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS runtime
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --home-dir /nonexistent app
COPY --from=lambda-adapter /lambda-adapter /opt/extensions/lambda-adapter
COPY --from=build /opt/venv /opt/venv
WORKDIR /srv
COPY --chown=root:root app ./app
COPY --chown=root:root alembic.ini ./

# /tmp is the only writable path on Lambda, and per-instance on Cloud Run.
# Set DATABASE_URL=postgresql://... at deploy time to keep data.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    DATABASE_URL=sqlite:////tmp/shortlinks.db \
    AWS_LWA_READINESS_CHECK_PATH=/healthz \
    AWS_LWA_READINESS_CHECK_HEALTHY_STATUS=200-299

USER 10001:10001
EXPOSE 8080
# Used by docker compose. Cloud Run and Lambda have their own probes and ignore this.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8080')}/healthz\", timeout=2)"]

# Build metadata last, so a new commit doesn't invalidate the layers above.
ARG GIT_SHA=dev
ARG APP_VERSION=
ARG BUILD_TIME=
LABEL org.opencontainers.image.title="fastapi-cicd-starter" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.created="${BUILD_TIME}"
ENV GIT_SHA=${GIT_SHA} \
    APP_VERSION=${APP_VERSION} \
    BUILD_TIME=${BUILD_TIME}

CMD ["python", "-m", "app.serve"]
ENV VALIDATE_SCHEMA=true
ENV COMPRESS_PAYLOAD=true
ENV VALIDATE_SCHEMA=true
ENV SERIALIZE_DATA=true