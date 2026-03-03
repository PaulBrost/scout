# Task Queue

SCOUT uses [django-q2](https://django-q2.readthedocs.io/) for background task execution. All long-running work (test execution, AI analysis) is offloaded to a separate worker process so the web server never blocks.

---

## Why django-q2

- **No extra infrastructure** — uses PostgreSQL as the task broker via `orm: 'default'`; no Redis, RabbitMQ, or Celery required
- **Simple deployment** — one extra process: `python manage.py qcluster`
- **ORM integration** — tasks, results, and schedules are stored in Django-managed tables; visible in Django Admin

---

## Configuration (`scout/settings.py`)

```python
Q_CLUSTER = {
    'name': 'scout',
    'workers': 2,        # two worker threads per qcluster process
    'timeout': 300,      # 5 minutes max per task
    'retry': 360,        # retry timeout (must be > timeout)
    'queue_limit': 50,   # max queued tasks before throttling
    'bulk': 10,          # tasks fetched per DB poll
    'orm': 'default',    # use the default PostgreSQL connection
}
```

### Worker count

Two workers means two Playwright subprocesses can run concurrently. Increase `workers` if the host has enough CPU/memory for more parallel test execution. The AI queue processor (`process_ai_queue`) is fast and shares the pool.

### Timeout

Set to 300s (5 minutes). The Playwright executor also has its own per-script timeout (`SCOUT_SCRIPT_TIMEOUT`, default 180s). If a script takes longer than `SCOUT_SCRIPT_TIMEOUT`, the executor kills it gracefully; the 300s task timeout is a backstop for the entire task.

---

## Starting the Worker

```bash
python manage.py qcluster
```

In Docker, the `worker` service runs this command. It must have access to the same database and filesystem (Playwright tests directory) as the web process.

The worker will log to stdout. In production, redirect with:

```bash
python manage.py qcluster >> /var/log/scout/worker.log 2>&1
```

---

## Queuing Tasks

Tasks are queued from views using `django_q.tasks.async_task`:

```python
from django_q.tasks import async_task

# Queue a suite run (fire and forget)
async_task(
    'tasks.run_tasks.execute_suite_run',
    str(run_id),
    task_name=f'run-{run_id}'
)
```

The task function is specified as a dotted import path. Arguments follow positionally.

---

## Task Functions

### `tasks.run_tasks.execute_suite_run(run_id)`

Executes all scripts in a `TestRun`.

```
Input:  run_id (str UUID)
Effect: updates test_run_scripts + test_run rows in DB
Output: none (results written to DB)
```

Steps:
1. Query `test_run_scripts WHERE run_id = ?` for all script paths
2. If no scripts found → mark `TestRun.status = 'failed'`, return
3. Call `executor.runner.execute_run(run_id, script_paths)`
4. The executor updates DB rows as each script completes

### `tasks.run_tasks.execute_single_script(run_id, script_path)`

Ad-hoc execution for the "Run Script" button in the suite editor.

```
Input:  run_id (str UUID), script_path (str)
Effect: same as execute_suite_run but for one script
```

### `tasks.ai_tasks.process_ai_queue()`

Processes pending AI analysis records.

```
Input:  none
Effect: updates AIAnalysis rows; creates Review rows
```

Steps:
1. Fetch up to 10 `AIAnalysis` records with `status='pending'`
2. For each:
   - If `screenshot_path` is set → `provider.analyze_screenshot(b64)`
   - If text available → `provider.analyze_text(text, language)`
   - Otherwise → `status = 'skipped'`
3. Update `AIAnalysis`:
   - `status = 'completed'` (or `'error'` on exception)
   - `issues_found`, `issues` (JSON), `raw_response`, `model_used`, `duration_ms`

---

## Scheduling

django-q2 supports cron-like schedules via `Schedule` objects. To run the AI queue processor every 30 seconds, create a `Schedule` in the Django Admin or a data migration:

```python
from django_q.models import Schedule

Schedule.objects.get_or_create(
    func='tasks.ai_tasks.process_ai_queue',
    defaults={
        'schedule_type': Schedule.MINUTES,
        'minutes': 1,
        'repeats': -1,    # run forever
        'name': 'AI Queue Processor',
    }
)
```

Or via the Django Admin at `/django-admin/django_q/schedule/`.

---

## Monitoring

### Django Admin

Task queue state is visible at:

| URL | Contents |
|-----|----------|
| `/django-admin/django_q/ormq/` | Queued tasks waiting to run |
| `/django-admin/django_q/success/` | Successfully completed tasks |
| `/django-admin/django_q/failure/` | Failed tasks with traceback |
| `/django-admin/django_q/schedule/` | Scheduled (recurring) tasks |

### Task result inspection

Failed tasks include the full Python traceback. Check `/django-admin/django_q/failure/` if runs appear to queue but never complete.

---

## Common Issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Runs stuck in `running` indefinitely | Worker not running | Start `python manage.py qcluster` |
| Tasks queued but not executed | `Q_CLUSTER` misconfigured or DB connection issue | Check worker stdout for errors |
| Tasks timeout before scripts finish | `SCOUT_SCRIPT_TIMEOUT` > `Q_CLUSTER['timeout']` | Increase `timeout` in `Q_CLUSTER` |
| AI queue never processes | `process_ai_queue` schedule not created | Create a `Schedule` object in Django Admin |
| Worker crashes on Playwright errors | Uncaught exception in executor | Check `/django-admin/django_q/failure/`; usually a missing `node_modules` or bad script path |

---

## Running Without the Worker (Development)

For local development, you can run tasks synchronously in the web process using `sync_task` instead of `async_task`. This is not recommended for production as it blocks the request.

Alternatively, trigger `execute_suite_run` directly in a Django shell:

```python
python manage.py shell
>>> from tasks.run_tasks import execute_suite_run
>>> execute_suite_run('your-run-uuid-here')
```
