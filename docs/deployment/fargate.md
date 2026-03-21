# AWS Fargate Deployment Guide

## Current Architecture

SCOUT runs as a three-process Docker Compose setup:

- **Web** (`gunicorn`) — serves HTML views and JSON APIs
- **Worker** (`qcluster`) — django-q2 background tasks for test execution and AI analysis
- **Nginx** — reverse proxy and static file server

PostgreSQL is the only external dependency (used for both app data and task queue broker — no Redis).

## Target Architecture on Fargate

```
                    ┌─────────────┐
                    │     ALB     │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
      ┌───────┴───────┐        ┌───────┴───────┐
      │  Web (Fargate) │        │ Worker (Fargate)│
      │  gunicorn × 3  │        │  qcluster × 2  │
      └───────┬───────┘        └───────┬───────┘
              │                         │
              ├─── EFS (archive) ───────┤
              │                         │
              └─── RDS PostgreSQL ──────┘
```

## ECS Task Definitions

Two ECS services from the same Docker image:

| Service | Command | CPU/Memory | Scaling |
|---------|---------|------------|---------|
| **web** | `gunicorn scout.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 300` | 1 vCPU / 2GB | Auto-scale behind ALB |
| **worker** | `python manage.py qcluster` | 2 vCPU / 4GB | Fixed 1 task (serialized execution) |

The worker needs more resources because it spawns Playwright/Chromium subprocesses.

## What Needs to Change

### 1. Persistent Storage

Test artifacts (screenshots, traces, videos) are stored on local disk via `shutil.copy2()` to `SCOUT_ARCHIVE_DIR`. Fargate containers have ephemeral storage.

**Recommended: EFS (zero code changes)**

Mount an EFS volume to both web and worker tasks at `/app/media/archive`. The application code stays the same — it's just a filesystem mount.

Alternative: S3 (more scalable, requires replacing file I/O in `executor/runner.py` and `tasks/post_execution.py` with boto3 calls).

### 2. Database → RDS

- RDS PostgreSQL instance (or Aurora Serverless)
- Point `DATABASE_URL` to it
- Add `conn_max_age=600` to `scout/settings.py` for connection reuse
- Consider a PgBouncer sidecar if scaling beyond ~4 workers (django-q2 polls the DB frequently)

### 3. Load Balancer + Static Files

- **ALB** in front of the web service (replaces nginx for proxying)
- **Static files** options:
  - S3 + CloudFront for `/static/` (best performance)
  - Or keep WhiteNoise (already configured) — serves static files from the web container directly. Simpler, works fine at modest scale.

### 4. Secrets Management

Replace `.env` file with:
- **AWS Secrets Manager** for sensitive values: `DATABASE_URL`, `AZURE_AI_API_KEY`, `EMAIL_HOST_PASSWORD`, `SECRET_KEY`
- **ECS task environment variables** for non-sensitive config: `DEBUG`, `ALLOWED_HOSTS`, `SCOUT_SCRIPT_TIMEOUT`, `AI_PROVIDER`

### 5. Migrations

Run as a one-off ECS task before deploying new versions:
```bash
python manage.py migrate --noinput
```
Or keep it in the web container entrypoint (current approach in docker-compose).

### 6. Playwright in Fargate

- The Dockerfile already installs Node.js 20.x + Playwright + Chromium with OS deps
- Chromium sandbox may need `--no-sandbox` flag — verify in Fargate's execution environment
- `npm install` runs in worker startup to ensure Playwright project deps are available

## What Doesn't Change

- **Dockerfile** — works as-is
- **All application code** — no changes needed if using EFS
- **Django-Q2 with PostgreSQL** — works fine with RDS
- **AI provider integration** — Azure OpenAI calls are HTTP, no AWS dependencies
- **Environment-driven config** — all settings already come from env vars

## Key File Paths in Container

| Setting | Container Path | Env Var |
|---------|---------------|---------|
| Archive storage | `/app/media/archive` | `SCOUT_ARCHIVE_DIR` |
| Playwright project | `/playwright-project` | `PLAYWRIGHT_PROJECT_ROOT` |
| Test scripts | `/playwright-project/tests` | `PLAYWRIGHT_TESTS_DIR` |
| Static files | `/app/staticfiles` | (Django STATIC_ROOT) |

## Environment Variables Required

### Essential
```bash
SECRET_KEY=<random-string>
DATABASE_URL=postgresql://user:pass@rds-host:5432/scout
DEBUG=False
ALLOWED_HOSTS=your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
PLAYWRIGHT_PROJECT_ROOT=/playwright-project
PLAYWRIGHT_TESTS_DIR=/playwright-project/tests
SCOUT_ARCHIVE_DIR=/app/media/archive
SCOUT_SCRIPT_TIMEOUT=660000
```

### AI Provider (optional)
```bash
AI_PROVIDER=azure
AZURE_AI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_AI_API_KEY=<key>
AZURE_AI_TEXT_DEPLOYMENT=gpt-4o
AZURE_AI_VISION_DEPLOYMENT=gpt-4o
AZURE_AI_API_VERSION=2024-02-01
```

### Email (optional)
```bash
EMAIL_HOST=smtp.office365.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<email>
EMAIL_HOST_PASSWORD=<password>
```

## Effort Estimate

| Task | Effort |
|------|--------|
| EFS + RDS + ECS infrastructure (Terraform/CDK) | 1-2 days |
| Code changes (zero if EFS, ~2-3 days if S3) | 0-3 days |
| CI/CD pipeline (ECR push + ECS deploy) | 0.5 day |
| Testing (Playwright in Fargate, end-to-end) | 1 day |
| **Total** | **2.5-6.5 days** |

## Notes

- The worker task should be fixed at 1 instance — test execution is serialized (Playwright `workers: 1` in config, and the assessment server cannot handle concurrent sessions)
- Database connection pooling becomes important with RDS — django-q2 workers hold connections open for polling
- The `Q_CLUSTER` timeout is set to 3600s (1 hour) to accommodate multi-script suite runs
- Production database is named `scout`, non-prod environments use `scout_dev`
