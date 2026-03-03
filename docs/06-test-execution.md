# Test Execution

SCOUT executes Playwright tests by spawning `npx playwright test` as a subprocess. All execution logic lives in `executor/runner.py`. The worker process calls it from django-q2 task functions in `tasks/run_tasks.py`.

---

## Run Lifecycle

```
[User or scheduler]
       │
       ▼
POST /suites/<id>/run/
  → Create TestRun (status='running')
  → Create TestRunScript per script (status='queued')
  → async_task('tasks.run_tasks.execute_suite_run', run_id)
       │
       ▼ (django-q2 worker picks up task)
execute_suite_run(run_id)
  → fetch script_paths from test_run_scripts
  → execute_run(run_id, script_paths)
       │
       ▼ (for each script)
execute_script(script_path)
  → update TestRunScript: status='running', started_at=now
  → subprocess.Popen(npx playwright test …)
  → capture stdout/stderr
  → parse JSON report
  → find artifacts (trace.zip, video)
  → update TestRunScript: status, duration_ms, error_message, logs, paths
       │
       ▼ (after all scripts)
  → compute summary {passed, failed, errors, total}
  → update TestRun: status='completed', summary, completed_at
```

---

## `execute_script` (`executor/runner.py`)

```python
def execute_script(script_path, project='', timeout=None, env_vars=None):
    ...
    return {
        "status": "passed" | "failed" | "error",
        "duration_ms": int,
        "error_message": str | None,
        "execution_log": str,       # full stdout
        "json_report": dict | None, # parsed Playwright JSON report
        "exit_code": int,
        "trace_path": str | None,   # relative path to trace.zip
        "video_path": str | None,   # relative path to video
    }
```

### Subprocess command

```bash
npx playwright test {full_path} --reporter=list,json
```

Environment variables set for the child process:
- All of `os.environ`
- `PLAYWRIGHT_JSON_OUTPUT_NAME` — set to a temp file so the JSON report is captured separately from stdout
- Any extras passed via `env_vars` argument

### Working directory

`subprocess.Popen` is called with `cwd=settings.PLAYWRIGHT_PROJECT_ROOT`. This ensures `node_modules`, `playwright.config.js`, and helper imports resolve correctly.

### Timeout

Default: `settings.SCOUT_SCRIPT_TIMEOUT` (from env var `SCOUT_SCRIPT_TIMEOUT`, default 180,000ms = 3 minutes).

On timeout, the subprocess is killed and the script result is `status='error'` with `error_message='Script timed out after {n}s'`.

### JSON report parsing

Playwright writes a JSON report when `--reporter=json` is used. The executor reads `PLAYWRIGHT_JSON_OUTPUT_NAME` to get the structured result. If the file doesn't exist (e.g., Playwright failed to start), `json_report` is `None` and the error is extracted from stdout/stderr.

### Error message extraction (`extract_error_message`)

1. Walk `json_report.suites → specs → tests → results` looking for `status: failed | timedOut`
2. Extract `error.message` from the first failing result
3. Fallback: scan stdout line-by-line for lines starting with `Error`, `AssertionError`, `expect(`
4. Truncate to 500 characters to keep DB rows manageable

### Artifact discovery (`find_artifacts`)

Scans `test-results/` within `PLAYWRIGHT_PROJECT_ROOT` for files matching the script's base name:

```python
test_results_dir / "**" / f"*{script_basename}*" / "trace.zip"
test_results_dir / "**" / f"*{script_basename}*" / "*.webm"
```

Returns relative paths so they can be stored in the DB and served later.

---

## `execute_run` (`executor/runner.py`)

Iterates scripts sequentially and keeps the DB in sync:

```python
for script_path in script_paths:
    # Update DB: status='running', started_at
    result = execute_script(script_path)
    # Update DB: status, duration_ms, error_message, execution_log, trace_path, video_path, completed_at

# Compute summary
summary = {
    "passed": n_passed,
    "failed": n_failed,
    "errors": n_errors,
    "total": len(script_paths)
}
# Update TestRun: status='completed', summary, completed_at
```

Scripts are run **sequentially**, not in parallel, to avoid browser resource contention.

---

## Django-Q2 Tasks (`tasks/run_tasks.py`)

### `execute_suite_run(run_id)`

Called by django-q2 when a suite run is queued.

```python
@async_task(task_name='execute_suite_run')
def execute_suite_run(run_id):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT script_path FROM test_run_scripts WHERE run_id=%s ORDER BY id',
            [run_id]
        )
        script_paths = [row[0] for row in cursor.fetchall()]
    if not script_paths:
        # Mark run as failed immediately
        ...
        return
    execute_run(str(run_id), script_paths)
```

### `execute_single_script(run_id, script_path)`

Ad-hoc execution — same mechanism but with a single script. Triggered by `POST /suites/run-script/`.

---

## Status Values

### TestRun.status

| Value | Meaning |
|-------|---------|
| `running` | Task queued or actively executing |
| `completed` | All scripts finished (some may have failed) |
| `failed` | Run could not complete (no scripts, task error) |
| `cancelled` | Manually cancelled (future feature) |

### TestRunScript.status

| Value | Meaning |
|-------|---------|
| `queued` | Created, not yet started |
| `running` | Subprocess active |
| `passed` | Exit code 0, no test failures |
| `failed` | One or more tests failed |
| `error` | Subprocess error, timeout, or unexpected exception |

---

## Playwright Configuration

SCOUT does not manage `playwright.config.js` — that file lives in `PLAYWRIGHT_PROJECT_ROOT` and is the responsibility of the test author. The executor simply runs whatever configuration Playwright finds there.

The `--project` flag can be passed via `project` argument to `execute_script` to target a specific Playwright project (browser profile).

### Recommended `playwright.config.js` settings for SCOUT compatibility

```js
import { defineConfig } from '@playwright/test';
export default defineConfig({
  reporter: [['list'], ['json', { outputFile: process.env.PLAYWRIGHT_JSON_OUTPUT_NAME }]],
  use: {
    trace: 'on-first-retry',
    video: 'on-first-retry',
  },
  outputDir: 'test-results/',
  timeout: 120_000,
});
```

---

## Viewing Results

- **Run list** (`/runs/`): Shows pass/fail summary per run
- **Run detail** (`/runs/<uuid>/`): Per-script status, duration, error message; "View Log" modal with full execution output
- **Artifacts**: `trace_path` and `video_path` fields in `TestRunScript` — serve via static files or a file endpoint (not yet implemented; paths are stored for future use)

---

## Security Note

The `execute_script` function constructs a command from `script_path`. The path is taken from the `TestSuiteScript.script_path` DB column, which is populated either:
- By the suite builder UI (user picks from a scanned list)
- By `test_cases/api_save` which validates the path is inside `PLAYWRIGHT_TESTS_DIR`

Always validate that resolved paths stay within `PLAYWRIGHT_TESTS_DIR` before writing or executing:

```python
full_path = (tests_dir / file_path).resolve()
if not str(full_path).startswith(str(tests_dir.resolve())):
    raise PermissionError("Access denied")
```
