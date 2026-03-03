# Deployment

## Processes

Three processes must run simultaneously:

| Process | Command | Role |
|---------|---------|------|
| **Web** | `gunicorn scout.wsgi:application` | HTTP server |
| **Worker** | `python manage.py qcluster` | Background tasks (test runs + AI queue) |
| **Database** | PostgreSQL | Persistent storage |

The web and worker processes must share:
- The same database
- Access to `PLAYWRIGHT_TESTS_DIR` and `PLAYWRIGHT_PROJECT_ROOT`
- The same `.env` (or equivalent environment variables)

---

## Docker Compose (Recommended)

```bash
# 1. Copy and edit configuration
cp .env.example .env
# Edit: DATABASE_URL, SECRET_KEY, AI_PROVIDER, PLAYWRIGHT_TESTS_DIR, etc.

# 2. Start all services
docker compose up -d

# 3. Check logs
docker compose logs -f web
docker compose logs -f worker

# 4. Create superuser (first run only)
docker compose exec web python manage.py createsuperuser
```

### `docker-compose.yml` services

| Service | Image | Role |
|---------|-------|------|
| `db` | `postgres:16-alpine` | PostgreSQL database |
| `web` | local build | Django + Gunicorn; runs `migrate` on startup |
| `worker` | local build | django-q2 worker (`qcluster`) |

### Volume mounts

| Volume | Purpose |
|--------|---------|
| `pgdata` | PostgreSQL data directory |
| `tests_dir` | Playwright test scripts (`PLAYWRIGHT_TESTS_DIR`) |
| `baselines` | Screenshot baselines |

For production, bind-mount the actual test scripts directory instead of using a named volume:

```yaml
# docker-compose.yml override
services:
  web:
    volumes:
      - /opt/scout/tests:/tests
      - /opt/scout/baselines:/baselines
  worker:
    volumes:
      - /opt/scout/tests:/tests
      - /opt/scout/baselines:/baselines
```

Set in `.env`:
```
PLAYWRIGHT_TESTS_DIR=/tests
PLAYWRIGHT_PROJECT_ROOT=/tests
```

---

## Dockerfile

```dockerfile
FROM python:3.12-slim

# System deps: libpq for psycopg2, Node.js 20 for Playwright execution
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg libpq-dev gcc \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput || true
RUN useradd -m scout && chown -R scout:scout /app
USER scout
EXPOSE 8000
CMD ["gunicorn", "scout.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--timeout", "120", "--access-logfile", "-"]
```

> Node.js is included in the image because the worker process spawns `npx playwright test` as a subprocess. Playwright itself is **not** installed in the image — it is expected to be present at `PLAYWRIGHT_PROJECT_ROOT` via the mounted volume (i.e., `npm install` has been run in the tests directory).

---

## Manual / Bare-Metal Deployment

```bash
# 1. Install system dependencies
sudo apt-get install python3.12 python3.12-venv libpq-dev nodejs npm

# 2. Create virtual environment
python3.12 -m venv /opt/scout/venv
source /opt/scout/venv/bin/activate

# 3. Install Python packages
pip install -r requirements.txt

# 4. Configure environment
cp .env.example /opt/scout/.env
# Edit /opt/scout/.env

# 5. Run migrations and collect static files
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser

# 6. Start web server (use systemd or supervisord in production)
gunicorn scout.wsgi:application --bind 0.0.0.0:8000 --workers 3

# 7. Start worker (separate terminal / systemd unit)
python manage.py qcluster
```

### systemd unit examples

**`/etc/systemd/system/scout-web.service`**
```ini
[Unit]
Description=SCOUT Web Server
After=network.target postgresql.service

[Service]
User=scout
WorkingDirectory=/opt/scout
EnvironmentFile=/opt/scout/.env
ExecStart=/opt/scout/venv/bin/gunicorn scout.wsgi:application \
    --bind 0.0.0.0:8000 --workers 3 --timeout 120 --access-logfile -
Restart=always

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/scout-worker.service`**
```ini
[Unit]
Description=SCOUT Background Worker
After=network.target postgresql.service

[Service]
User=scout
WorkingDirectory=/opt/scout
EnvironmentFile=/opt/scout/.env
ExecStart=/opt/scout/venv/bin/python manage.py qcluster
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable scout-web scout-worker
sudo systemctl start scout-web scout-worker
```

---

## First-Run Checklist

- [ ] `.env` configured (`SECRET_KEY`, `DATABASE_URL`, `AI_PROVIDER`, `PLAYWRIGHT_TESTS_DIR`)
- [ ] `python manage.py migrate` completed
- [ ] `python manage.py collectstatic` completed
- [ ] Superuser created via `python manage.py createsuperuser`
- [ ] Worker process running (`qcluster`)
- [ ] Node.js and `npx playwright` available in `PATH` (on the worker's host)
- [ ] `npm install` run in `PLAYWRIGHT_PROJECT_ROOT` (installs Playwright)
- [ ] AI schedule configured (see [docs/07-task-queue.md](07-task-queue.md))
- [ ] Login at `http://<host>/` works
- [ ] Django Admin accessible at `http://<host>/django-admin/`

---

## Reverse Proxy (Nginx example)

For TLS termination and to serve under a domain:

```nginx
server {
    listen 443 ssl;
    server_name scout.internal.example.com;

    ssl_certificate     /etc/ssl/scout.crt;
    ssl_certificate_key /etc/ssl/scout.key;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # WhiteNoise handles /static/ — but Nginx can serve it faster
    location /static/ {
        alias /opt/scout/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

Add to `.env` when behind a proxy:
```dotenv
ALLOWED_HOSTS=scout.internal.example.com
```

Also add to `settings.py` (or via env):
```python
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

---

## Upgrades

```bash
# Pull new code
git pull

# Install any new dependencies
pip install -r requirements.txt

# Apply new migrations
python manage.py migrate

# Collect updated static files
python manage.py collectstatic --noinput

# Restart services
sudo systemctl restart scout-web scout-worker
# or: docker compose up -d --build
```

---

## Backup

### Database

```bash
pg_dump -U scout scout > scout-$(date +%Y%m%d).sql
```

### Playwright artifacts

Back up `PLAYWRIGHT_PROJECT_ROOT/test-results/` and the baselines directory. These are not stored in PostgreSQL.

---

## Scaling

| Bottleneck | Solution |
|-----------|----------|
| Web throughput | Increase `--workers` in Gunicorn (1 worker per CPU core is typical) |
| Concurrent test runs | Increase `workers` in `Q_CLUSTER` settings; ensure the host has enough CPU/memory for parallel Playwright instances |
| AI throughput | Increase Ollama concurrency or provision a faster GPU; the AI task processor is I/O-bound |
| Database | Tune `conn_max_age` and PostgreSQL `max_connections`; consider PgBouncer for connection pooling |
