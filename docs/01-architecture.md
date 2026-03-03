# Architecture

## Overview

SCOUT is a Django monolith backed by PostgreSQL. It has three runtime processes:

| Process | Command | Role |
|---------|---------|------|
| **Web** | `gunicorn scout.wsgi:application` | Handles all HTTP requests; renders templates; accepts API calls |
| **Worker** | `python manage.py qcluster` | Executes background tasks (Playwright runs, AI analysis queue) |
| **Database** | PostgreSQL | Persistent storage for all state |

Playwright test scripts remain as Node.js `.spec.js` files. The worker spawns `npx playwright test` as a subprocess — no Node.js server is required in the Python stack.

---

## Component Diagram

```
Browser
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Django Web Process                        │
│                                                                   │
│  /                dashboard/views.py    ─────┐                   │
│  /runs/           runs/views.py               │                  │
│  /suites/         suites/views.py             │  Raw SQL          │
│  /items/          items/views.py              │  (connection      │
│  /reviews/        reviews/views.py            │   .cursor())      │
│  /builder/        builder/views.py            │                   │
│  /test-cases/     test_cases/views.py         │                   │
│  /assessments/    assessments/views.py        │                   │
│  /environments/   environments/views.py ──────┤                   │
│  /admin-config/   admin_config/views.py ──────┤                   │
│                                               ▼                   │
│                                    ┌──────────────────┐           │
│                                    │   PostgreSQL DB  │           │
│  POST /builder/api/chat/           └──────────────────┘           │
│     │                                       ▲                     │
│     ▼                                       │                     │
│  builder/chat_manager.py                    │                     │
│     │                                       │                     │
│     ▼                                       │                     │
│  ai/provider.py                             │                     │
│  (AzureFoundry | Ollama | Mock)             │                     │
│                                             │                     │
│  POST /suites/{id}/run/ ──────────────────► django_q.async_task   │
└──────────────────────────────────────────── │ ───────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     django-q2 Worker Process                     │
│                                                                   │
│  tasks/run_tasks.py                                               │
│    execute_suite_run(run_id)                                      │
│      │                                                            │
│      ▼                                                            │
│    executor/runner.py                                             │
│      │  subprocess.Popen(npx playwright test …)                  │
│      │                                                            │
│      ▼                                                            │
│    Node.js / Playwright ─── assessment app under test ──►        │
│      │                                                            │
│      ▼                                                            │
│    JSON report + trace.zip + video ──► DB update                 │
│                                                                   │
│  tasks/ai_tasks.py                                                │
│    process_ai_queue()  (periodic, every 30s)                      │
│      │                                                            │
│      ▼                                                            │
│    ai/provider.py ─── Azure / Ollama / Mock                       │
│      │                                                            │
│      ▼                                                            │
│    AIAnalysis + Review records updated                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Test Run

```
User                  Web process               Worker               Playwright
────                  ───────────               ──────               ──────────
Click "Run Suite" ──► POST /suites/{id}/run/
                      Create TestRun (running)
                      Create TestRunScripts (queued)
                      async_task(execute_suite_run) ──►
                                                 fetch script paths
                                                 execute_run()
                                                 for each script:
                                                   execute_script() ──► npx playwright test
                                                                        return JSON report
                                                   update TestRunScript (passed/failed)
                                                 update TestRun (completed, summary)
Poll /api/runs/latest/ ◄─────────────── status updates in DB
```

### AI Analysis

```
Worker (periodic)           AI Provider              DB
─────────────────           ───────────              ──
process_ai_queue()
  fetch pending AIAnalysis
  for each analysis:
    load screenshot_path
    provider.analyze_screenshot(b64) ──►
                            returns issues JSON
                                                     update AIAnalysis (completed)
                                                     create Review (pending)
```

### Builder Chat

```
User (browser)             Web process              AI Provider
──────────────             ───────────              ───────────
type message ──────────────► POST /builder/api/chat/
                              load AIConversation from DB
                              build_system_prompt()
                              provider.chat_completion() ──►
                                                     stream response
                              parse_tool_calls()
                              execute_tool() (if any)
                              save conversation to DB
                              return {response, codeUpdate} ◄───────
update code panel ◄────────
```

---

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `core` | ORM models, authentication, RBAC mixins, Django admin registration, sidebar context |
| `dashboard` | Homepage stats, trend data, AI flag count |
| `runs` | Test run list/detail, per-script result inspection |
| `suites` | Suite CRUD, script picker, run trigger |
| `items` | Item inventory, linked scripts |
| `assessments` | Assessment metadata, item sub-lists |
| `environments` | Deployment target config (admin only) |
| `reviews` | AI review queue, approve/dismiss/bug actions |
| `test_cases` | Script registry, file save, syntax dry-run |
| `builder` | Split-panel AI IDE: chat + code editor |
| `admin_config` | System prompt, tool toggles, provider settings (admin only) |
| `ai` | Provider abstraction: Azure / Ollama / Mock |
| `executor` | subprocess.Popen Playwright runner, artifact discovery |
| `tasks` | django-q2 task functions for async execution |

---

## Key Design Decisions

### Raw SQL over ORM
Most list views use `connection.cursor()` with raw SQL. This makes pagination (`LIMIT/OFFSET`), complex joins, and aggregation explicit and avoids N+1 query traps. ORM is used only for simple single-object lookups and inserts.

### PostgreSQL as task broker
django-q2 is configured with `orm: 'default'` — it uses the existing PostgreSQL database as its task queue broker. No Redis, RabbitMQ, or additional infrastructure is needed.

### No Node.js server
Playwright tests run as Node.js processes but there is no persistent Node.js server. Each test execution spawns a short-lived `npx playwright test` subprocess, captures its output, and exits. The Python web process never talks to a Node server.

### AI is advisory
AI analysis results create `Review` records that require human action (approve / dismiss / file bug). No test is auto-failed based solely on AI output.

### Conversations stored in DB
The AI chat manager stores conversation history (`AIConversation.messages` as a `JSONField`) in PostgreSQL rather than in server memory. This means conversations survive server restarts and work correctly with multiple Gunicorn workers.
