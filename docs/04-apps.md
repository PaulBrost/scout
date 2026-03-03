# Django Apps

Each app owns its own `views.py`, `urls.py`, and templates. All templates live in `templates/<app_name>/`.

---

## dashboard

**Purpose:** Landing page showing system health at a glance.

**URL prefix:** `/` (no prefix — mounted at root)

### Views

| View | Route | Description |
|------|-------|-------------|
| `index` | `GET /` | Dashboard summary page |
| `api_trend` | `GET /api/trend/?limit=10` | JSON array of last N runs with status + summary |
| `api_ai_flags` | `GET /api/ai-flags/` | JSON count of pending AI reviews |

### Template: `dashboard/index.html`

- Stats cards: active environments, total items, pending reviews, last run status
- Recent runs table (last 5): status badge, suite name, trigger type, passed/failed counts, timestamp
- Auto-refreshes every 30s via `setInterval` + `fetch(/api/runs/latest/)`

---

## runs

**Purpose:** View test run history and inspect per-script results.

**URL prefix:** `/runs/`

### Views

| View | Route | Description |
|------|-------|-------------|
| `index` | `GET /runs/` | Paginated, sortable run list |
| `detail` | `GET /runs/<uuid>/` | Run summary + all script results |
| `script_detail` | `GET /runs/<uuid>/script/<uuid>/` | Single script result as JSON (used by modal) |
| `api_list` | `GET /api/runs/list/` | JSON paginated list |
| `api_latest` | `GET /api/runs/latest/` | JSON: most recent run |

### Query parameters (index)

| Param | Default | Description |
|-------|---------|-------------|
| `page` | 1 | Page number |
| `page_size` | 25 | Rows per page; options: 10, 25, 50, 100 |
| `sort` | `started` | Sort column: `started`, `status`, `trigger`, `suite` |
| `dir` | `desc` | `asc` or `desc` |
| `status` | (all) | Filter: `running`, `completed`, `failed`, `cancelled` |
| `search` | (none) | Searches suite name and notes |

### Templates

- `runs/list.html` — status filter tabs, sortable table, pagination
- `runs/detail.html` — run header (status, suite, duration, summary), script results table, log modal

---

## suites

**Purpose:** Create and manage test suites; trigger runs.

**URL prefix:** `/suites/`

### Views

| View | Route | Method | Description |
|------|-------|--------|-------------|
| `index` | `/suites/` | GET | Paginated suite list (env-scoped) |
| `suite_new` | `/suites/new/` | GET | Create new suite form |
| `suite_detail` | `/suites/<uuid>/` | GET | Edit suite form |
| `suite_create` | `/suites/api/create/` | POST JSON | Create suite + script associations |
| `suite_update` | `/suites/api/update/<uuid>/` | POST JSON | Replace suite + scripts |
| `suite_delete` | `/suites/api/delete/<uuid>/` | POST JSON | Delete suite |
| `suite_run` | `/suites/<uuid>/run/` | POST JSON | Create TestRun + queue task |
| `run_script` | `/suites/run-script/` | POST JSON | Ad-hoc single-script run |
| `api_list` | `/suites/api/list/` | GET | JSON paginated list |

### `suite_run` body

```json
{
  "browser_profiles": ["Desktop Chrome"],
  "notes": "Optional run notes"
}
```

Response:

```json
{"runId": "<uuid>", "status": "running", "scripts": 5}
```

### Templates

- `suites/list.html` — suite table with "Run" button per row; run triggers via fetch
- `suites/detail.html` — suite metadata form, script picker (checkboxes), JS CRUD calls

---

## items

**Purpose:** Browse the item inventory.

**URL prefix:** `/items/`

### Views

| View | Route | Description |
|------|-------|-------------|
| `index` | `GET /items/` | Paginated, sortable item list (env-scoped) |
| `detail` | `GET /items/<int>/` | Item metadata + associated test scripts |
| `api_list` | `GET /items/api/list/` | JSON list |

### Query parameters (index)

| Param | Description |
|-------|-------------|
| `search` | Searches `item_id` and `title` |
| `assessment` | Filter by assessment ID |
| `sort` | `item_id`, `title`, `category`, `tier` |
| `dir` | `asc` / `desc` |
| `page`, `page_size` | Standard pagination |

### Templates

- `items/list.html` — sortable table with assessment filter dropdown
- `items/detail.html` — item fields, linked scripts table with "Edit in Builder" links

---

## assessments

**Purpose:** Browse assessments and see their item lists.

**URL prefix:** `/assessments/`

### Views

| View | Route | Description |
|------|-------|-------------|
| `index` | `GET /assessments/` | Paginated list (env-scoped) |
| `detail` | `GET /assessments/<str>/` | Assessment metadata + item sub-table |
| `api_list` | `GET /assessments/api/list/` | JSON list |

### Templates

- `assessments/list.html` — sortable by name, subject, grade, environment; search box
- `assessments/detail.html` — details card + items table; "AI Builder" button to open builder pre-loaded with this assessment

---

## environments

**Purpose:** Manage deployment targets. **Admin only.**

**URL prefix:** `/environments/`

### Views

| View | Route | Method | Description |
|------|-------|--------|-------------|
| `index` | `/environments/` | GET | List all environments with assessment counts |
| `environment_new` | `/environments/new/` | GET | Create form |
| `environment_edit` | `/environments/<uuid>/edit/` | GET | Edit form |
| `environment_create` | `/environments/create/` | POST | Create environment |
| `environment_update` | `/environments/<uuid>/update/` | POST | Update environment |
| `environment_delete` | `/environments/<uuid>/delete/` | POST | Delete (cascades) |

### Form fields

| Field | Description |
|-------|-------------|
| `name` | Display name |
| `base_url` | Root URL for test navigation |
| `auth_type` | `password_only` / `username_password` / `none` |
| `username` | Stored in `credentials` JSON |
| `password` | Stored in `credentials` JSON (leave blank to keep existing) |
| `notes` | Optional |
| `is_default` | Checkbox — marks this as the default environment |

### Templates

- `environments/list.html` — table with auth type, assessment count, default badge, edit/delete buttons
- `environments/edit.html` — create/edit form

---

## reviews

**Purpose:** Human review queue for AI-flagged issues.

**URL prefix:** `/reviews/`

### Views

| View | Route | Method | Description |
|------|-------|--------|-------------|
| `index` | `/reviews/` | GET | Paginated queue (default: pending only) |
| `review_action` | `/reviews/action/` | POST JSON | Approve / dismiss / file bug |
| `api_list` | `/reviews/api/list/` | GET | JSON paginated list |

### `review_action` body

```json
{
  "reviewId": "<uuid>",
  "action": "approve | dismiss | bug_filed",
  "notes": "optional reviewer note",
  "bugUrl": "https://jira.example.com/…"
}
```

### Filter tabs

The list view has tabs for: `Pending` (default) · `Approved` · `Dismissed` · `Bug Filed` · `All`.

### Templates

- `reviews/list.html` — status tabs, table with analysis type + issue count, action buttons (Approve / Dismiss / Bug) that call `reviewAction()` via fetch and remove the row on success

---

## test_cases

**Purpose:** Registry and management of `.spec.js` test scripts.

**URL prefix:** `/test-cases/`

### Views

| View | Route | Method | Description |
|------|-------|--------|-------------|
| `index` | `/test-cases/` | GET | Paginated merged list (filesystem + DB) |
| `api_save` | `/test-cases/api/save/` | POST JSON | Write file to disk + register in DB |
| `api_dry_run` | `/test-cases/api/dry-run/` | POST JSON | Syntax check via `node --check` |
| `api_associate` | `/test-cases/api/associate/` | POST JSON | Update script metadata (item/category) |
| `api_list` | `/test-cases/api/list/` | GET | JSON list (used by builder dropdowns) |

### `api_save` body

```json
{
  "path": "relative/path/to/script.spec.js",
  "content": "// Playwright test code…"
}
```

The path is validated to be within `PLAYWRIGHT_TESTS_DIR` (directory traversal prevention).

### `api_associate` body

```json
{
  "scriptPath": "items/vh123456.spec.js",
  "itemId": "VH123456",
  "assessmentId": "M4-2024-A",
  "category": "visual_regression",
  "description": "Visual regression for item VH123456"
}
```

Uses `INSERT … ON CONFLICT … DO UPDATE` — safe to call repeatedly.

### Source classification

Each script in the list is tagged as either:
- **`registered`** — has a row in the `test_scripts` DB table
- **`filesystem`** — discovered by scanning `PLAYWRIGHT_TESTS_DIR` but not yet in DB

### Templates

- `test_cases/list.html` — table with category filter chips, source badges, "Edit in Builder" links

---

## builder

**Purpose:** Browser-based AI-assisted Playwright script editor.

**URL prefix:** `/builder/`

See [docs/08-builder.md](08-builder.md) for full details.

### Views (summary)

| View | Route | Description |
|------|-------|-------------|
| `builder_view` | `GET /builder/` | Split-panel IDE |
| `api_chat` | `POST /builder/api/chat/` | AI chat turn |
| `api_save` | `POST /builder/api/save/` | Save generated script |

---

## admin_config

**Purpose:** Runtime AI configuration. **Admin only.**

**URL prefix:** `/admin-config/`

### Views

| View | Route | Method | Description |
|------|-------|--------|-------------|
| `ai_settings` | `/admin-config/ai/` | GET | AI settings dashboard |
| `update_prompt` | `/admin-config/ai/prompt/` | POST | Update system prompt |
| `toggle_tool` | `/admin-config/ai/tools/<id>/toggle/` | POST JSON | Toggle tool enabled/disabled |
| `update_settings` | `/admin-config/ai/settings/` | POST | Save max turns + tool calling flag |

### Template: `admin_config/ai_settings.html`

Three sections:
1. **System Prompt** — `<textarea>` with full prompt; saved to `AISetting(key='system_prompt')`
2. **Provider** — shows current `AI_PROVIDER`, max turns, tool calling toggle
3. **AI Tools** — table of all `AITool` rows with live toggle switches (fetch on change)

---

## URL Summary

The root `scout/urls.py` wires everything together:

```python
path('django-admin/', admin.site.urls)
path('login/',        core.views.login_view)
path('logout/',       core.views.logout_view)
path('',              include('dashboard.urls'))     # /
path('runs/',         include('runs.urls'))           # /runs/
path('suites/',       include('suites.urls'))         # /suites/
path('items/',        include('items.urls'))          # /items/
path('reviews/',      include('reviews.urls'))        # /reviews/
path('assessments/',  include('assessments.urls'))    # /assessments/
path('environments/', include('environments.urls'))   # /environments/
path('test-cases/',   include('test_cases.urls'))     # /test-cases/
path('builder/',      include('builder.urls'))        # /builder/
path('admin-config/', include('admin_config.urls'))   # /admin-config/
path('api/',          include('runs.api_urls'))        # /api/runs/…
```
