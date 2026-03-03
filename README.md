# SCOUT — Automated Assessment Testing Dashboard

SCOUT is a Django-based web application that orchestrates Playwright test execution, AI-powered content and visual analysis, and human review workflows for the NAEP (National Assessment of Educational Progress) assessment platform.

## Features

- **Test execution** — Run Playwright `.spec.js` scripts against any configured environment; track results, artifacts (traces, videos), and execution logs
- **AI analysis** — Content validation (spelling, homophone, grammar) and visual regression checks via pluggable AI providers (Azure AI Foundry, Ollama, or Mock)
- **Human review queue** — AI-flagged issues routed to reviewers; approve, dismiss, or file a bug
- **AI Test Builder** — Browser-based IDE with an AI chat assistant that writes and modifies Playwright scripts
- **Environment-scoped RBAC** — Admins see everything; regular users see only their assigned environments
- **Background task queue** — django-q2 handles test runs and AI processing without blocking the web process

## Requirements

- Python 3.12+
- Node.js 20+ (for Playwright script execution)
- PostgreSQL 14+
- `npx playwright` available on `PATH`

## Quickstart

```bash
# 1. Clone and enter the project
cd /mnt/h/Brost/SCOUT

# 2. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env — at minimum set DATABASE_URL and SECRET_KEY

# 4. Run migrations and create a superuser
python manage.py migrate
python manage.py createsuperuser

# 5. Start the development server
python manage.py runserver

# 6. In a separate terminal, start the task worker
source /mnt/h/Brost/SCOUT/.venv/bin/activate
python manage.py qcluster
```

The dashboard is available at `http://localhost:8000`. The Django admin is at `/django-admin/`.

## Docker

```bash
cp .env.example .env    # edit as needed
docker compose up -d
```

Three services start: `db` (PostgreSQL), `web` (Django + Gunicorn), and `worker` (django-q2 task worker). The `web` service runs `migrate` automatically on startup.

## Directory Structure

```
SCOUT/
├── manage.py
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
│
├── scout/                    # Django project config
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── core/                     # Shared models, auth, RBAC, admin
│   ├── models.py             # All ORM models
│   ├── admin.py              # Django Admin registrations
│   ├── mixins.py             # EnvironmentScopedMixin, LoginRequiredMixin
│   ├── context_processors.py # Sidebar nav injected into all templates
│   └── views.py              # Login / logout
│
├── dashboard/                # GET / — summary dashboard
├── runs/                     # /runs/ — test run list + detail
├── suites/                   # /suites/ — test suite CRUD + run trigger
├── items/                    # /items/ — item inventory
├── assessments/              # /assessments/ — assessment metadata
├── environments/             # /environments/ — deployment targets (admin only)
├── reviews/                  # /reviews/ — AI review queue
├── test_cases/               # /test-cases/ — script registry + save/dry-run
├── builder/                  # /builder/ — AI test builder IDE
├── admin_config/             # /admin-config/ — AI settings (admin only)
│
├── ai/                       # AI provider abstraction layer
│   ├── provider.py           # BaseProvider + get_provider() factory
│   ├── azure_foundry.py      # Azure OpenAI provider
│   ├── ollama.py             # Ollama (local LLM) provider
│   ├── mock.py               # Mock provider for testing
│   └── prompts.py            # Prompt templates
│
├── executor/
│   └── runner.py             # subprocess.Popen Playwright runner
│
├── tasks/
│   ├── run_tasks.py          # django-q2: execute_suite_run, execute_single_script
│   └── ai_tasks.py           # django-q2: process_ai_queue
│
└── templates/
    ├── base.html             # Bootstrap 5 sidebar layout
    ├── login.html
    ├── partials/             # table_controls.html, pagination.html
    ├── dashboard/
    ├── runs/
    ├── suites/
    ├── items/
    ├── assessments/
    ├── environments/
    ├── reviews/
    ├── test_cases/
    ├── builder/
    └── admin_config/
```

## Documentation

| File | Contents |
|------|----------|
| [docs/01-architecture.md](docs/01-architecture.md) | System diagram, component roles, data flow |
| [docs/02-models.md](docs/02-models.md) | Full ORM model reference |
| [docs/03-authentication-rbac.md](docs/03-authentication-rbac.md) | Auth system and environment-scoped RBAC |
| [docs/04-apps.md](docs/04-apps.md) | All Django apps — views, URLs, templates |
| [docs/05-ai-integration.md](docs/05-ai-integration.md) | AI providers, prompts, chat manager, tool calling |
| [docs/06-test-execution.md](docs/06-test-execution.md) | Playwright executor, run lifecycle, artifacts |
| [docs/07-task-queue.md](docs/07-task-queue.md) | django-q2 setup, task functions, scheduling |
| [docs/08-builder.md](docs/08-builder.md) | AI test builder, chat interface, code editor |
| [docs/09-api-reference.md](docs/09-api-reference.md) | All HTTP endpoints (HTML + JSON) |
| [docs/10-configuration.md](docs/10-configuration.md) | Environment variables and Django settings |
| [docs/11-deployment.md](docs/11-deployment.md) | Docker, production setup, operations |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web framework | Django 5.2 |
| Database | PostgreSQL 14+ via psycopg2 |
| Task queue | django-q2 (ORM broker — no Redis required) |
| AI inference | Azure AI Foundry / Ollama / Mock |
| Test runner | Playwright (Node.js), invoked via subprocess |
| Static files | WhiteNoise |
| Container | Docker + Docker Compose |
| Frontend | Bootstrap 5.3, Bootstrap Icons, vanilla JS |
