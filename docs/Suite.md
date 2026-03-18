# Test Suites

## Overview

A **Test Suite** groups multiple Playwright test scripts together so they can be run as a single unit. Suites are scoped to an environment and can be run manually on demand or scheduled to run automatically on a recurring basis.

## Data Model

### `test_suites`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `name` | TEXT | Required, displayed in list and runs |
| `description` | TEXT | Optional |
| `environment_id` | UUID FK | Links to `environments`, determines which scripts are available |
| `created_by_id` | INT FK | Links to `auth_user`, used for RBAC scoping |
| `schedule` | JSONB | Schedule configuration (see Scheduling below), nullable |
| `browser_profiles` | JSONB | Currently unused, defaults to `[]` |
| `created_at` | TIMESTAMPTZ | Auto-set |
| `updated_at` | TIMESTAMPTZ | Auto-updated |

### `test_suite_scripts`

| Column | Type | Notes |
|--------|------|-------|
| `id` | AUTO | Primary key |
| `suite_id` | UUID FK | Links to `test_suites` (CASCADE) |
| `script_path` | TEXT | Path to the test script file |
| `browser` | TEXT | Default `chromium`. Each script can have its own browser. |
| `viewport` | TEXT | Default `1920x1080` |
| `added_at` | TIMESTAMPTZ | Order-preserving timestamp |

**Unique constraint**: `(suite_id, script_path, browser, viewport)` — the same script can appear multiple times in a suite with different browser/viewport combinations.

## Key Files

| File | Purpose |
|------|---------|
| `core/models.py` | TestSuite, TestSuiteScript, TestRun models |
| `suites/views.py` | All suite views — CRUD, run, scheduling APIs |
| `suites/urls.py` | URL routing under `/suites/` |
| `templates/suites/list.html` | Suite list page with pagination, search, run/delete buttons |
| `templates/suites/detail.html` | Suite editor — details, scripts, schedule card |
| `tasks/run_tasks.py` | `execute_suite_run()` and `execute_scheduled_suite()` |

## Running a Suite

### Manual Run ("Run Now")

1. User clicks **Run Now** on the suite detail or list page
2. Frontend POSTs to `/suites/<suite_id>/run/`
3. Backend (`suite_run` view):
   - Fetches suite scripts from `test_suite_scripts`
   - Merges `ai_config` from all scripts (OR logic — if any script has text or visual analysis enabled, the run enables it)
   - Creates a `test_runs` record with `trigger_type='dashboard'`
   - Creates `test_run_scripts` records for each script (status `queued`)
   - Spawns a background thread via `core.utils.spawn_background_task()`
4. Background thread calls `tasks.run_tasks.execute_suite_run(run_id)`
5. That calls `executor.runner.execute_run()` which runs each script via `npx playwright test`
6. Post-execution pipeline runs (baseline comparison, AI analysis, email notifications)

### Execution Flow

```
suite_run() view
  └─> spawn_background_task()
        └─> execute_suite_run(run_id)
              ├─> executor.runner.execute_run(run_id, script_paths)
              └─> _run_post_execution(run_id)
                    ├─> _compare_against_baselines()
                    ├─> dispatch_post_execution()  (AI analysis)
                    └─> send_run_notifications()   (email)
```

## Scheduling

### How It Works

Suite scheduling uses **django-q2's Schedule model** for reliable task dispatch. The `qcluster` management command (which must be running) checks for due schedules and executes them.

When a user saves a schedule:
1. Schedule config is stored in the suite's `schedule` JSONB field
2. A `django_q.models.Schedule` record is created/updated to fire `tasks.run_tasks.execute_scheduled_suite(suite_id)`
3. When the schedule fires, `execute_scheduled_suite` creates a new `test_runs` record (with `trigger_type='scheduled'`) and runs it through the same pipeline as manual runs

### Schedule JSON Structure

```json
{
  "enabled": true,
  "pattern": "weekly",
  "time": "09:00",
  "timezone": "America/New_York",
  "interval_hours": null,
  "days_of_week": [0, 2, 4],
  "day_of_month": null,
  "once_date": null,
  "end_date": "2026-06-01",
  "next_run": "2026-03-19T09:00:00-04:00",
  "dq_schedule_id": 12,
  "created_by_id": 5
}
```

### Recurrence Patterns

| Pattern | django-q2 Type | Config Fields |
|---------|---------------|---------------|
| `once` | `Schedule.ONCE` | `once_date`, `time` |
| `hourly` | `Schedule.MINUTES` | `interval_hours` (1,2,4,6,8,12), `time` (start time) |
| `daily` | `Schedule.DAILY` | `time` |
| `weekly` | `Schedule.CRON` | `days_of_week` (0=Mon..6=Sun), `time` |
| `monthly` | `Schedule.MONTHLY` | `day_of_month` (1-28), `time` |

All times are stored and evaluated in the user's timezone.

### End Date Handling

If `end_date` is set, `execute_scheduled_suite` checks it before creating a run. If the date has passed, it:
1. Sets `schedule.enabled = false` in the suite
2. Deletes the django-q Schedule record
3. Skips execution

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/suites/<id>/schedule/` | POST | Create or update a schedule |
| `/suites/<id>/schedule/delete/` | POST | Remove a schedule |

### Cleanup

When a suite is deleted, the delete handler also removes the associated django-q Schedule record (looked up via `schedule.dq_schedule_id`).

## RBAC / Access Control

- **Environment scoping**: Users only see suites linked to their assigned environments
- **User scoping**: Non-admin users only see suites they created or system-created suites (`created_by_id IS NULL`)
- **Admin users**: See all suites across all environments
- **Impersonation**: Admin users impersonating a non-admin see that user's view

## Suite List View

The list page (`/suites/`) shows:
- Suite name (with clock icon if scheduled)
- Environment name
- Script count
- Last run time and status (via lateral join to `test_runs`)
- Actions: Edit, Run, Delete

Supports pagination, search, and column sorting.

## Suite Detail View

The detail page (`/suites/<id>/`) has three sections:

1. **Suite Details** — name, description, environment selector, assessment/item filters (for narrowing the available scripts list)
2. **Suite Scripts** — table of added scripts with browser/viewport per entry, add/remove via modal
3. **Schedule** — recurrence configuration card (only shown for existing suites)

The "Add Scripts" modal loads available scripts for the selected environment (with optional assessment/item filtering) and lets users batch-add them with a default browser/viewport.

## Trigger Types in test_runs

| `trigger_type` | Source |
|---------------|--------|
| `dashboard` | Manual "Run Now" from UI |
| `manual` | Ad-hoc single script run |
| `scheduled` | Automated scheduled run |
| `baseline` | Baseline generation run |
| `api` | External API trigger |
