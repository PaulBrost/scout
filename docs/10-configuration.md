# Configuration

All configuration is managed through environment variables, loaded via `python-decouple` from a `.env` file in the project root.

Copy the example file to get started:

```bash
cp .env.example .env
```

---

## Required Variables

These must be set in production. The defaults are only suitable for local development.

| Variable | Example | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `django-insecure-…` | Django secret key. Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DATABASE_URL` | `postgresql://scout:pass@localhost:5432/scout` | PostgreSQL connection URL |

---

## Django Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `django-insecure-dev-key-change-in-production` | Must be changed in production |
| `DEBUG` | `True` | Set to `False` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of allowed host headers |
| `DATABASE_URL` | `postgresql://scout:scout@localhost:5432/scout` | Full PostgreSQL connection string |

---

## AI Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_PROVIDER` | `mock` | Which AI provider to use: `mock`, `azure`, or `ollama` |
| `MOCK_AI_MODE` | `clean` | Mock mode: `clean` (no issues), `issues` (simulated issues), `error` (raises exception) |

### Azure AI Foundry (`AI_PROVIDER=azure`)

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_ENDPOINT` | — | Azure OpenAI resource endpoint, e.g. `https://my-resource.openai.azure.com` |
| `AZURE_API_KEY` | — | Azure OpenAI API key |
| `AZURE_TEXT_DEPLOYMENT` | `gpt-4o` | Deployment name for text analysis and chat |
| `AZURE_VISION_DEPLOYMENT` | `gpt-4o` | Deployment name for vision analysis (can be same as text if using GPT-4o) |
| `AZURE_API_VERSION` | `2024-02-01` | API version string |

### Ollama (`AI_PROVIDER=ollama`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `localhost:11434` | Host and port of the Ollama server (no `http://` prefix) |
| `OLLAMA_TEXT_MODEL` | `qwen2.5:14b` | Model name for text analysis and chat |
| `OLLAMA_VISION_MODEL` | `gemma3:12b` | Model name for screenshot analysis |

Ensure the models are pulled before use:
```bash
ollama pull qwen2.5:14b
ollama pull gemma3:12b
```

---

## Playwright / Test Execution

| Variable | Default | Description |
|----------|---------|-------------|
| `PLAYWRIGHT_TESTS_DIR` | `…/ETS/SCOUT/poc/tests` | Absolute path to the directory containing `.spec.js` files. The executor resolves all script paths relative to this directory. |
| `PLAYWRIGHT_PROJECT_ROOT` | `…/ETS/SCOUT/poc` | Absolute path to the Playwright project root (where `playwright.config.js` and `node_modules` live). This is the `cwd` for subprocess execution. |
| `SCOUT_SCRIPT_TIMEOUT` | `180000` | Per-script execution timeout in **milliseconds** (default: 3 minutes). Scripts that exceed this are killed. |
| `SCOUT_MOCK` | `0` | Set to `1` to skip actual Playwright execution and return mock results. Useful for testing the dashboard without Node.js. |

---

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_AUTH` | `True` | If `False`, authentication is disabled and all views are public. **Never set to `False` in production.** |

---

## Full `.env.example`

```dotenv
# ── Django ───────────────────────────────────────────────────────────
SECRET_KEY=django-insecure-replace-this-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL=postgresql://scout:scout@localhost:5432/scout

# ── AI Provider ───────────────────────────────────────────────────────
# Options: mock | azure | ollama
AI_PROVIDER=mock
MOCK_AI_MODE=clean    # clean | issues | error

# Azure AI Foundry (used when AI_PROVIDER=azure)
AZURE_ENDPOINT=https://your-resource.openai.azure.com
AZURE_API_KEY=your-api-key-here
AZURE_TEXT_DEPLOYMENT=gpt-4o
AZURE_VISION_DEPLOYMENT=gpt-4o
AZURE_API_VERSION=2024-02-01

# Ollama local LLM (used when AI_PROVIDER=ollama)
OLLAMA_HOST=localhost:11434
OLLAMA_TEXT_MODEL=qwen2.5:14b
OLLAMA_VISION_MODEL=gemma3:12b

# ── Playwright ────────────────────────────────────────────────────────
PLAYWRIGHT_TESTS_DIR=/absolute/path/to/tests
PLAYWRIGHT_PROJECT_ROOT=/absolute/path/to/playwright-project
SCOUT_SCRIPT_TIMEOUT=180000
SCOUT_MOCK=0

# ── Auth ──────────────────────────────────────────────────────────────
DASHBOARD_AUTH=True
```

---

## Settings Reference (`scout/settings.py`)

### Database

```python
_database_url = config('DATABASE_URL', default='postgresql://scout:scout@localhost:5432/scout')
DATABASES = {
    'default': dj_database_url.parse(_database_url, conn_max_age=600)
}
```

`conn_max_age=600` keeps database connections open for 10 minutes, reducing connection overhead.

### Static files

```python
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

WhiteNoise serves compressed, cache-busted static files directly from Gunicorn — no Nginx needed for static files.

Run `python manage.py collectstatic` to gather static files into `staticfiles/` before the first deployment.

### django-q2

```python
Q_CLUSTER = {
    'name': 'scout',
    'workers': 2,
    'timeout': 300,
    'retry': 360,
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',
}
```

See [docs/07-task-queue.md](07-task-queue.md) for tuning guidance.

### Installed apps

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_q',
    # SCOUT apps
    'core', 'dashboard', 'runs', 'suites', 'items', 'reviews',
    'assessments', 'environments', 'test_cases', 'builder', 'admin_config',
]
```

---

## Environment-Specific Notes

### Local development

```dotenv
DEBUG=True
AI_PROVIDER=mock
SCOUT_MOCK=0
PLAYWRIGHT_TESTS_DIR=/path/to/your/tests
```

### Production (on-premise)

```dotenv
DEBUG=False
SECRET_KEY=<strong-random-key>
ALLOWED_HOSTS=scout.internal.example.com
DATABASE_URL=postgresql://scout:<strong-password>@db-host:5432/scout
AI_PROVIDER=ollama
OLLAMA_HOST=ollama-server:11434
PLAYWRIGHT_TESTS_DIR=/app/tests
PLAYWRIGHT_PROJECT_ROOT=/app
```

In production:
- Set `DEBUG=False`
- Use a strong `SECRET_KEY` (at least 50 random characters)
- Configure `ALLOWED_HOSTS` to the actual hostname
- Use a dedicated PostgreSQL user with a strong password
- Run behind a reverse proxy (Nginx/Caddy) for TLS termination
