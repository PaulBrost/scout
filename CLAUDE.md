# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Activate the venv (same one for all terminals)
source .venv/bin/activate

# Run dev server
python manage.py runserver

# Run background task worker (separate terminal, same venv)
python manage.py qcluster

# Apply migrations after model changes
python manage.py makemigrations
python manage.py migrate

# Collect static files (required for WhiteNoise in production)
python manage.py collectstatic --noinput

# Create superuser
python manage.py createsuperuser
```

No test suite exists yet. Testing is manual via the running application.

## Architecture Overview

SCOUT is a Django 5.2 app that orchestrates Playwright test execution against NAEP assessment environments, runs AI-powered content/visual analysis on results, and routes flagged issues to human reviewers.

### Three-process architecture
1. **Web** (`runserver` / gunicorn) — serves HTML views and JSON APIs
2. **Worker** (`qcluster`) — django-q2 background tasks for test execution and AI analysis; uses PostgreSQL as the broker (no Redis)
3. **PostgreSQL** — single database for app data and task queue

### Key data flow
```
User triggers suite run → async_task('tasks.run_tasks.execute_suite_run', run_id)
  → Worker picks up task → executor/runner.py calls `npx playwright test` via subprocess
  → Results saved to test_run_scripts / test_results tables
  → AI analysis queued → ai/provider.py dispatches to Azure/Ollama/Mock
  → Issues flagged → Reviews created for human triage
```

### All models live in `core/models.py`

Models use custom `db_table` names (e.g., `'test_runs'`, `'ai_analyses'`). Key relationships:
- **Environment** ←M2M via UserEnvironment→ **User** (RBAC)
- **TestSuite** → **TestSuiteScript** (scripts in a suite)
- **TestRun** → **TestRunScript** (execution results per script)
- **TestRun** → **TestResult** → **AIAnalysis** → **Review**
- **Assessment** → **Item** (content hierarchy)
- Item FK fields use `to_field='item_id'` (text identifier), not the numeric PK

### Environment-scoped RBAC

Non-admin users only see data linked to their assigned environments. This is enforced in two ways:
- **CBV**: `EnvironmentScopedMixin` in `core/mixins.py` — provides `get_user_environment_ids()` and `apply_env_filter(qs)`
- **FBV**: `get_user_env_ids(user)` standalone function — returns `None` for admins (meaning "all"), or a list of UUIDs

Most list views build raw SQL with `connection.cursor()` and inject `WHERE environment_id = ANY(%s::uuid[])` clauses for scoping. This is intentional — the codebase favors raw SQL over ORM querysets in views.

### AI provider layer (`ai/`)

Factory pattern via `get_provider()` in `ai/provider.py` — returns a singleton `BaseProvider` subclass based on `settings.AI_PROVIDER`:
- `'azure'` → `AzureFoundryProvider` (Azure OpenAI REST API)
- `'ollama'` → `OllamaProvider` (local LLM)
- `'mock'` → `MockProvider` (returns canned responses; mode controlled by `MOCK_AI_MODE`: `clean`, `issues`, or `error`)

Provider interface: `analyze_text()`, `analyze_screenshot()`, `compare_text()`, `generate_test()`, `chat_completion()`, `health_check()`

### AI Test Builder (`builder/`)

`builder/chat_manager.py` manages multi-turn conversations with tool calling. The AI can invoke tools like `update_code`, `read_file`, `list_helpers`, etc. Tools are defined in the `ai_tools` DB table and can be toggled via admin config.

## Conventions

- **Config**: All settings from env vars via `python-decouple`. See `.env.example` for available variables.
- **URLs**: Each Django app has its own `urls.py`, included in `scout/urls.py`. URL prefix matches app name (e.g., `/runs/`, `/suites/`). Exception: `/test-cases/` maps to `test_cases` app.
- **Templates**: All in top-level `templates/` dir, organized by app. Every page extends `templates/base.html` (Bootstrap 5 sidebar layout). Reusable partials in `templates/partials/`.
- **Static files**: `static/css/` and `static/js/`, served by WhiteNoise middleware.
- **Views**: Mix of function-based (most common, using raw SQL) and class-based (using mixins). JSON API endpoints live alongside HTML views, typically prefixed `api_`.
- **Task queuing**: `from django_q.tasks import async_task` then `async_task('tasks.module.function_name', arg)`.
- **UUIDs**: Most primary keys are UUIDs. Serialize with `default=str` in `JsonResponse`.
- **Admin-only views**: Use `AdminRequiredMixin` (CBV) or check `request.user.is_staff` (FBV). Admin sections: environments, admin-config, django-admin.
- **Context processor**: `core.context_processors.nav_context` injects `nav_environments` and `is_admin` into every template.
