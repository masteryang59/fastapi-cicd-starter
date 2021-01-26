# FastAPI CI/CD Starter

A small FastAPI service with a complete GitHub Actions pipeline: lint, type-check, test on SQLite and PostgreSQL, build one Docker image, and roll it out to staging and then production on **Google Cloud Run** or **AWS Lambda**, with no cloud keys stored in GitHub.

Most "CI/CD templates" stop at `docker push` and a `deploy` command. That's the easy part. The hard part is everything around it: knowing the thing you deployed is the thing you tested, not sending users to a revision that can't reach its database, getting back to the last good version in one click, and not leaving a long-lived cloud key in a repository secret. This starter does that work. CI builds the image **once**, smoke-tests that exact digest, and pushes it to GHCR. Each deploy copies the same digest (no rebuild) into Artifact Registry or ECR and starts it **next to** the live version with no traffic. The deploy then checks the new version on its own URL: is it up, is its database schema current, and does `/version` report the commit we built? Only then does it get 100% of traffic. If the live URL fails after the switch, the previous version is put back automatically. Cloud credentials come from GitHub's OIDC token, scoped to one repository and one GitHub environment, and production waits for a reviewer.

The service being deployed is a URL shortener (**Shortlinks**). It's small, but it's not a hello-world: it has a database, migrations, an admin API, input validation and a page to look at.

![The Shortlinks landing page after shortening a link, with the deployment card showing environment, commit, build time and storage](docs/screenshot.png)

*The screenshot is from a real local run of the container entrypoint (`python -m app.serve`, migrations then uvicorn), with the build metadata the pipeline would bake in. It was not taken on Cloud Run or Lambda: this project has not been deployed to a real cloud account (see [Limitations](#limitations)). The "This deployment" card is how you see which commit is live in each environment.*

## The pipeline

```mermaid
flowchart LR
    PR[Pull request] --> L
    M[Push to main] --> L
    subgraph CI [ci.yml]
        L[lint<br/>ruff · mypy --strict<br/>actionlint · pip-audit]
        T[test matrix<br/>py3.12 + 3.13 · SQLite<br/>py3.12 · PostgreSQL 17<br/>coverage ≥ 90% · alembic check]
        I[image<br/>hadolint · build once<br/>smoke-test the container<br/>push digest to GHCR]
        L --> I
        T --> I
    end
    M --> T
    PR --> T
    I -- main only --> S[deploy.yml<br/>staging]
    S --> P[deploy.yml<br/>production<br/>waits for a reviewer]
    D[Run workflow:<br/>any commit] -. rollback .-> S & P
```

| Job | What it does | Fails the build when |
| --- | --- | --- |
| **lint** | `uv sync --locked`, ruff lint and format, strict mypy, actionlint (with shellcheck on the runner), `pip-audit` on the exported lockfile | the lockfile is stale, code is unformatted or mistyped, a workflow is invalid, a runtime dependency has a known CVE |
| **test** | pytest on Python 3.12 and 3.13 against SQLite, and on 3.12 against a PostgreSQL 17 service container; then `alembic upgrade head && alembic check` | a test fails, coverage drops under 90%, or a model changed without a migration |
| **image** | hadolint; one `linux/amd64` build with the commit, version and build time baked in; runs the container with a **read-only root filesystem** (like Lambda) and smoke-tests it; on `main` pushes `ghcr.io/<repo>:sha-<commit>` and moves `:main` | the Dockerfile has issues, or the built container doesn't start, isn't ready, or reports the wrong commit |
| **deploy-staging** | calls `deploy.yml` with the GHCR digest | the new version fails its smoke test (traffic is never shifted) |
| **deploy-production** | the same digest, after staging succeeded; the `production` environment's protection rules apply (required reviewers, wait timer, branch rules) | the same |

On a pull request, the three CI jobs run and nothing is pushed. A newer push to the same PR cancels the older run. A run on `main` is never cancelled, because it might be halfway through a deploy.

### One deploy, step by step

```mermaid
sequenceDiagram
    participant GH as deploy.yml
    participant R as GHCR → AR / ECR
    participant C as Cloud Run / Lambda
    participant N as new version
    GH->>GH: check inputs and variables (python3 -m ops check-config)
    GH->>GH: OIDC → short-lived Google / AWS credentials
    GH->>R: skopeo copy --preserve-digests (refuse if the image's revision label ≠ commit)
    GH->>C: deploy by digest with 0% traffic<br/>(Cloud Run: --no-traffic --tag c-<sha> · Lambda: publish version, move `candidate` alias)
    GH->>N: smoke test the candidate URL: /healthz, /readyz, /version == commit, /
    alt candidate fails
        GH->>C: remove the tag, live traffic untouched → job fails
    else candidate passes
        GH->>C: 100% to the new version (Cloud Run traffic / Lambda `live` alias)
        GH->>C: smoke test the live URL
        alt live fails
            GH->>C: restore the previous traffic split / alias → job fails
        end
    end
```

All of this lives in [`ops/`](ops/), a small Python package that uses only the standard library. The deploy job runs it with the runner's own `python3`, with nothing to install, and you can run the same commands from a laptop. The workflow YAML only wires up credentials, which keeps the logic testable: the [tests](tests/ops/) drive it with in-memory fakes of `gcloud`, `aws` and `skopeo` that parse the real arguments.

- **Same bytes everywhere.** The image is built once. CI's smoke test runs the pushed digest. Deploys refer to `repo@sha256:…`, never a tag, and the copy into the cloud registry keeps the digest (and checks it afterwards). ECR tags are immutable, and `ops` refuses to re-point an existing tag at a different digest.
- **The right commit, not just a healthy one.** The smoke test compares `/version`'s `git_sha` with the commit being deployed. That catches a stale image, a wrong tag, or a traffic shift that hasn't propagated yet. Failing checks are retried with backoff for up to 3 minutes, which covers cold starts.
- **Ready means migrated.** `/readyz` checks the database **and** that its Alembic revision equals the migration head the code ships with. A revision whose migrations didn't run is never promoted. `/healthz` stays database-free, so a database blip doesn't make the platform kill every instance.
- **Migrations at startup, safely.** `python -m app.serve` runs `alembic upgrade head` before starting uvicorn. On PostgreSQL a session-level advisory lock makes concurrent instances wait for the first one (tested with four racing threads against real Postgres). Migrations must stay backwards compatible for one release, because the old revision keeps serving while the new one starts.
- **Lambda specifics.** The image includes the [AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter) as an extension, so the same uvicorn server runs unchanged on Lambda. It is inert everywhere else. Images are built with `provenance: false`, because Lambda rejects image indexes. `publish-version --code-sha256` makes the deploy fail if someone else changed the function in between.

### Security choices

- **No stored cloud credentials.** GCP uses Workload Identity Federation with an attribute condition on the repository, and the deployer can only be impersonated from jobs running in a named GitHub environment. AWS uses one IAM role per environment, whose trust policy requires `sub = repo:<owner>/<repo>:environment:<name>`. The staging role can't touch the production function.
- **Pinned everything.** Every action is pinned to a full commit SHA with a `# vX.Y.Z` comment. Base images (`python:3.12-slim-trixie`, `uv`, the Lambda adapter, Postgres, hadolint) are pinned by digest. Python dependencies are locked in `uv.lock` with hashes. [Dependabot](.github/dependabot.yml) keeps all four moving.
- **Least privilege by default.** Workflows default to `contents: read`. Only the `image` job can write packages, and only deploy jobs get `id-token: write`. Checkouts don't persist the token.
- **No script injection.** No `${{ }}` expression appears inside a `run:` script. Values go through `env:`, and the manual deploy's `git-sha` input is validated as 40 hex characters. A test enforces this.
- **Container.** Runs as UID 10001, has no build tools in the final stage, and works with a read-only root filesystem (only `/tmp` is written).

[tests/test_pipeline_config.py](tests/test_pipeline_config.py) checks these rules against the workflow files, so a later edit can't quietly undo them.

## The sample service

| Endpoint | |
| --- | --- |
| `GET /` | Landing page: shorten a link, and see which build is running where |
| `POST /api/links` | `{"url": "...", "slug": "optional"}` → `201` with the short URL. http(s) only, no `user:pass@`, no links to the service itself, slugs are 3–32 lowercase letters, digits and hyphens, and some are reserved |
| `GET /api/links/{slug}` | Link details and click count |
| `GET /{slug}` | `307` redirect (not `301`, so every click is counted) with one atomic `UPDATE … RETURNING` |
| `GET /api/links`, `DELETE /api/links/{slug}` | Admin API with an `X-API-Key` header. Disabled (`503`) unless `ADMIN_API_KEY` is set |
| `GET /healthz` · `/readyz` · `/version` | Liveness, readiness (database + schema revision) and build info |
| `GET /docs` | OpenAPI UI |

Logs are one JSON object per line, with `severity` for Cloud Logging, a request id (`X-Request-ID` is kept when valid and echoed back) and an access line per request with status and duration. Probe requests are logged at DEBUG.

## Tech stack

- **App:** Python 3.12, FastAPI 0.162, SQLAlchemy 2.1, Alembic, psycopg 3, pydantic-settings, Jinja2, uvicorn
- **Tooling:** uv (lockfile, CI cache, Docker build), ruff, mypy `--strict`, pytest + pytest-cov, actionlint, hadolint, pip-audit
- **CI/CD:** GitHub Actions (reusable workflow, environments, OIDC, concurrency groups), Docker Buildx with the GHA cache, GHCR, skopeo
- **Cloud:** Google Cloud Run + Artifact Registry + Workload Identity Federation, or AWS Lambda (container image + Lambda Web Adapter) + ECR + IAM OIDC. Terraform for both in [`infra/`](infra/)
- **Deploy tooling:** [`ops/`](ops/), standard-library Python (`python3 -m ops smoke | copy-image | deploy | check-config`)
- **Tests:** 163 pytest tests, no cloud account or network needed. They run against SQLite, or PostgreSQL when `DATABASE_URL` points at one

## Run it

### Locally

```bash
uv sync                                  # Python 3.12+, creates .venv from uv.lock
cp .env.example .env                     # optional
uv run python -m app.serve               # migrates data/app.db, serves http://127.0.0.1:8080
```

### Docker Compose (the production image + PostgreSQL)

```bash
docker compose up --build                # http://localhost:8080
```

The container runs with `read_only: true` and a tmpfs `/tmp`, the same constraint it has on Lambda.

### Tests and checks

```bash
uv run python scripts/ci_local.py        # the lint and test jobs, in CI order
uv run pytest                            # 163 tests, SQLite
DATABASE_URL=postgresql://user:pass@localhost:5432/test uv run pytest   # the same against PostgreSQL
uv run python -m ops smoke --url http://127.0.0.1:8080 --expect-sha dev # the deploy smoke test, by hand
```

A real smoke run against the local server (right commit, then wrong commit):

```text
$ python -S -m ops smoke --url http://127.0.0.1:8015 --expect-sha 3f9c2a7e5b8d14c6a0f2e9b7d3c1a5e8f4b6d2c9
PASS http://127.0.0.1:8015 (1 attempts, 0.1s)
  ok  healthz: HTTP 200
  ok  readyz: HTTP 200
  ok  version: git_sha 3f9c2a7e5b8d
  ok  home: HTTP 200 text/html; charset=utf-8

$ python -S -m ops smoke --url http://127.0.0.1:8015 --expect-sha 0000000000000000000000000000000000000000 --deadline 6
FAIL http://127.0.0.1:8015 (3 attempts, 5.1s)
  ok  healthz: HTTP 200
  ok  readyz: HTTP 200
  ERR version: running 3f9c2a7e5b8d, expected 000000000000
  ok  home: HTTP 200 text/html; charset=utf-8
```

## Turn on deploys

CI works as soon as the repository is pushed. Deploys stay off (with a notice on each `main` run) until you pick a target.

**1. GitHub environments.** Create `staging` and `production` under *Settings → Environments*. On `production`, add required reviewers, and limit deployment branches to `main`.

**2a. Google Cloud Run**

```bash
cd infra/gcp
cp terraform.tfvars.example terraform.tfvars   # project_id, region, github_repository
terraform init && terraform apply
terraform output -raw gh_commands | sh         # sets DEPLOY_TARGET=gcp and each environment's variables (needs gh)
```

This creates the Artifact Registry repository, a `shortlinks-<env>` Cloud Run service per environment (running Google's hello image until the first deploy), the runtime and deployer service accounts, and the Workload Identity pool and provider. After the first apply, the pipeline owns the image and the traffic split (`ignore_changes`), so later `terraform apply` runs don't roll anything back.

**2b. AWS Lambda.** Lambda can't create a function without an image, so the first apply is in two steps:

```bash
cd infra/aws
cp terraform.tfvars.example terraform.tfvars   # region, github_repository
terraform init
terraform apply -target=aws_ecr_repository.app
# Seed the repository once with any build of this image, e.g. from the first CI run on main:
aws ecr get-login-password | docker login --username AWS --password-stdin "$(terraform output -raw ecr_repository_url | cut -d/ -f1)"
skopeo copy docker://ghcr.io/<owner>/<repo>:main docker://$(terraform output -raw ecr_repository_url):bootstrap
terraform apply
terraform output -raw gh_commands | sh         # sets DEPLOY_TARGET=aws and each environment's variables
```

Per environment, this creates a function, a `live` and a `candidate` alias each with a public function URL, a log group with 14-day retention, and a deploy role that only that GitHub environment can assume.

**3. Keep data (optional).** Without a `DATABASE_URL`, each instance keeps links in SQLite under `/tmp`, so they disappear when it's replaced. The landing page says so. For real use, point it at PostgreSQL (Cloud SQL, RDS, Neon, Supabase…): `database_url_secrets` (a Secret Manager secret id) on GCP, `database_urls` on AWS.

### Variables the deploy job reads

| Target | Repository variable | Environment variables |
| --- | --- | --- |
| GCP | `DEPLOY_TARGET=gcp` | `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GAR_REPOSITORY`, `CLOUD_RUN_SERVICE` |
| AWS | `DEPLOY_TARGET=aws` | `AWS_REGION`, `AWS_ROLE_ARN`, `ECR_REPOSITORY`, `LAMBDA_FUNCTION` |

None of these are secrets. A missing variable fails the job before any cloud call, with a message naming it.

## Rolling back

*Actions → Deploy → Run workflow*, pick the environment, and paste the full commit SHA of the last good version. Its image (`ghcr.io/<repo>:sha-<commit>`) is already in GHCR, so there's no rebuild. It goes through the same candidate smoke test before it gets traffic. A failed deploy never needs this, because it either never got traffic or was reverted automatically.

## Project layout

```text
app/                    FastAPI service
  main.py               app factory (routers, middleware, lifespan)
  serve.py              container entrypoint: migrate, then uvicorn on $PORT
  routes_*.py           API, probes, HTML pages + redirect
  links.py              storage (atomic click counting, slug retry on collision)
  schema.py             Alembic helpers + advisory-locked upgrade
  migrations/           Alembic environment and versions
  observability.py      JSON logging, request-id middleware
ops/                    deploy tooling, standard library only
  smoke.py              /healthz, /readyz, /version == commit, /
  images.py             skopeo copy with digest checks
  cloudrun.py           tag-based blue/green with rollback
  awslambda.py          alias-based blue/green with rollback
  cli.py                python3 -m ops …
infra/gcp, infra/aws    Terraform for the one-time cloud setup
.github/workflows/      ci.yml (lint, test, image, deploy chain), deploy.yml (reusable + manual)
tests/                  app, migrations, ops (fake gcloud/aws/skopeo), pipeline-config rules
scripts/                ci_local.py, make_screenshot.py
```

## Limitations

These are honest gaps. Some of them come from what could be run on the machine this was built on.

- **Never run on GitHub, GCP or AWS.** The workflows pass actionlint and the config tests, every action is pinned to a SHA I resolved from its repository, and each `with:` input was checked against that commit's `action.yml`. But no workflow has run on GitHub Actions, and nothing has been deployed to a real Cloud Run service or Lambda function. The deploy logic is tested against fakes that model the CLIs' arguments and state, not the real services. Details like gcloud's exact error text for a missing service, or the traffic JSON shape, come from documentation, not a live account.
- **Docker was not available.** The Dockerfile has not been built. hadolint and the container smoke test only run in CI. The image digests are real (fetched from the registries), and the compose file is untested.
- **Terraform was not validated.** Downloading the terraform binary wasn't possible here, so `infra/` has never been through `terraform init/validate/plan`. Expect small fixes on first apply (for example, Google provider 8.x attribute changes).
- **Cloud-side assumptions.** `skopeo` is assumed to be on the `ubuntu-24.04` runner image, as it has been, and the `ops` CLI fails clearly if it isn't. Cloud Run tag URLs and the Lambda `candidate` URL are public, like the service. An org policy that forbids `allUsers` needs `public = false` and an authenticated smoke test, which isn't built.
- **GCP permissions are broader than AWS.** There's one deployer service account with project-level `roles/run.developer` for both environments. AWS has one role per environment.
- **Secrets on AWS go in Terraform state.** `database_urls` and `admin_api_keys` become plain Lambda environment variables. GCP reads them from Secret Manager instead. Moving AWS to Secrets Manager or SSM would need a fetch at startup.
- **SQLite in the cloud is a demo.** Without `DATABASE_URL`, each instance has its own throwaway database, so links created on one instance aren't visible on another. The app says so on the landing page and in the logs.
- **Not built:** rate limiting on `POST /api/links`, URL safety checks (malware/phishing lists), canary percentages between 0 and 100, container signing (cosign) and SBOM attestation (disabled, because Lambda rejects image indexes; they could be pushed as separate referrers).

## sort entries

Updated implementation details.

## verify token

Updated implementation details.

## sort entries

Updated implementation details.