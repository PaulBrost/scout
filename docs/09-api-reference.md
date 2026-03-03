# API Reference

All endpoints require authentication (session cookie). JSON endpoints additionally require the `X-CSRFToken` header for state-changing requests.

---

## HTML Pages

These routes render full Django templates.

| Method | Path | View | Description |
|--------|------|------|-------------|
| GET | `/` | `dashboard.views.index` | Dashboard |
| GET | `/login/` | `core.views.login_view` | Login form |
| POST | `/login/` | `core.views.login_view` | Authenticate |
| GET | `/logout/` | `core.views.logout_view` | Log out + redirect |
| GET | `/runs/` | `runs.views.index` | Run list |
| GET | `/runs/<uuid>/` | `runs.views.detail` | Run detail |
| GET | `/suites/` | `suites.views.index` | Suite list |
| GET | `/suites/new/` | `suites.views.suite_new` | New suite form |
| GET | `/suites/<uuid>/` | `suites.views.suite_detail` | Edit suite form |
| GET | `/items/` | `items.views.index` | Item list |
| GET | `/items/<int>/` | `items.views.detail` | Item detail |
| GET | `/assessments/` | `assessments.views.index` | Assessment list |
| GET | `/assessments/<str>/` | `assessments.views.detail` | Assessment detail |
| GET | `/environments/` | `environments.views.index` | Environment list (admin) |
| GET | `/environments/new/` | `environments.views.environment_new` | New environment form (admin) |
| GET | `/environments/<uuid>/edit/` | `environments.views.environment_edit` | Edit environment form (admin) |
| GET | `/reviews/` | `reviews.views.index` | Review queue |
| GET | `/test-cases/` | `test_cases.views.index` | Script registry |
| GET | `/builder/` | `builder.views.builder_view` | AI test builder |
| GET | `/admin-config/ai/` | `admin_config.views.ai_settings` | AI settings (admin) |

---

## Form POST Endpoints

These accept `application/x-www-form-urlencoded` from HTML forms and redirect on success.

| Method | Path | Description | Required fields |
|--------|------|-------------|-----------------|
| POST | `/environments/create/` | Create environment | `name`, `base_url`, `auth_type` |
| POST | `/environments/<uuid>/update/` | Update environment | same |
| POST | `/environments/<uuid>/delete/` | Delete environment | — |
| POST | `/admin-config/ai/prompt/` | Update system prompt | `prompt` |
| POST | `/admin-config/ai/settings/` | Update AI settings | `max_conversation_turns`, `tool_calling_enabled` |

---

## JSON API Endpoints

All accept and return `application/json`.

### Dashboard

#### `GET /api/trend/`

Returns recent run trend data.

**Query params:** `limit` (default 10)

**Response:**
```json
{
  "trend": [
    {
      "id": "uuid",
      "started_at": "2024-01-15T10:30:00Z",
      "status": "completed",
      "summary": {"passed": 12, "failed": 1, "errors": 0, "total": 13}
    }
  ]
}
```

---

#### `GET /api/ai-flags/`

Returns count of pending AI reviews.

**Response:**
```json
{"count": 7}
```

---

### Runs

#### `GET /api/runs/latest/`

Returns the most recent test run.

**Response:**
```json
{
  "run": {
    "id": "uuid",
    "status": "completed",
    "trigger_type": "manual",
    "started_at": "2024-01-15T10:30:00Z",
    "completed_at": "2024-01-15T10:35:00Z",
    "summary": {"passed": 12, "failed": 1, "errors": 0, "total": 13}
  }
}
```

---

#### `GET /api/runs/list/`

Paginated run list.

**Query params:** `page`, `pageSize`, `status`, `search`

**Response:**
```json
{
  "rows": [...],
  "total": 47,
  "page": 1,
  "pageSize": 25
}
```

---

#### `GET /runs/<uuid>/script/<uuid>/`

Single script execution result (used by the run detail log modal).

**Response:**
```json
{
  "id": "uuid",
  "script_path": "items/vh123456.spec.js",
  "status": "failed",
  "duration_ms": 4200,
  "error_message": "expect(locator).toHaveScreenshot() failed...",
  "execution_log": "Running 1 test...\n  ✗ [chromium] items/vh123456.spec.js",
  "trace_path": "test-results/.../trace.zip",
  "video_path": null,
  "started_at": "2024-01-15T10:30:05Z",
  "completed_at": "2024-01-15T10:30:09Z"
}
```

---

### Suites

#### `POST /suites/api/create/`

**Request body:**
```json
{
  "name": "Smoke Suite",
  "description": "Quick sanity checks",
  "scripts": ["items/vh001.spec.js", "items/vh002.spec.js"],
  "browser_profiles": ["Desktop Chrome"],
  "schedule": {},
  "environment_id": "uuid-or-null"
}
```

**Response:**
```json
{"id": "uuid", "redirect": "/suites/uuid/"}
```

---

#### `POST /suites/api/update/<uuid>/`

Same body shape as create. Replaces all script associations.

**Response:**
```json
{"ok": true}
```

---

#### `POST /suites/api/delete/<uuid>/`

**Response:**
```json
{"ok": true}
```

---

#### `POST /suites/<uuid>/run/`

Triggers a test run for the suite.

**Request body (optional):**
```json
{
  "browser_profiles": ["Desktop Chrome", "firefox-desktop"],
  "notes": "Pre-release check"
}
```

**Response:**
```json
{
  "runId": "uuid",
  "status": "running",
  "scripts": 5
}
```

---

#### `POST /suites/run-script/`

Ad-hoc single-script run (not attached to a suite).

**Request body:**
```json
{"scriptPath": "items/vh123456.spec.js"}
```

**Response:**
```json
{"runId": "uuid", "status": "running"}
```

---

#### `GET /suites/api/list/`

**Query params:** `page`, `page_size`, `search`

**Response:**
```json
{
  "suites": [...],
  "total": 12,
  "page": 1
}
```

---

### Items

#### `GET /items/api/list/`

**Query params:** `search`, `assessment`

**Response:**
```json
{
  "items": [
    {"numeric_id": 42, "item_id": "VH123456", "title": "Fraction comparison", "category": "visual_regression"}
  ],
  "total": 847
}
```

---

### Assessments

#### `GET /assessments/api/list/`

**Query params:** `search`, `page`, `page_size`

---

### Reviews

#### `POST /reviews/action/`

Approve, dismiss, or file a bug on a review.

**Request body:**
```json
{
  "reviewId": "uuid",
  "action": "approve",
  "notes": "Confirmed valid, no issue",
  "bugUrl": ""
}
```

`action` must be one of: `approve`, `dismiss`, `bug_filed`.

**Response:**
```json
{"ok": true}
```

On error:
```json
{"error": "Review not found"}
```

---

#### `GET /reviews/api/list/`

**Query params:** `page`, `pageSize`, `status`

---

### Test Cases

#### `POST /test-cases/api/save/`

Write a script file to disk and register it.

**Request body:**
```json
{
  "path": "items/vh123456.spec.js",
  "content": "import { test, expect } from '@playwright/test';\n…"
}
```

Path must resolve inside `PLAYWRIGHT_TESTS_DIR`.

**Response:**
```json
{"success": true, "path": "items/vh123456.spec.js"}
```

---

#### `POST /test-cases/api/dry-run/`

Syntax-check JavaScript code via `node --check`.

**Request body:**
```json
{"code": "import { test } from '@playwright/test'; test('x', …)"}
```

**Response (pass):**
```json
{"success": true, "message": "Syntax valid — no errors found"}
```

**Response (fail):**
```json
{"error": "SyntaxError: Unexpected token 'export' (line 5)"}
```

---

#### `POST /test-cases/api/associate/`

Associate a script with an item, assessment, and/or category.

**Request body:**
```json
{
  "scriptPath": "items/vh123456.spec.js",
  "itemId": "VH123456",
  "assessmentId": "M4-2024-A",
  "category": "visual_regression",
  "description": "Visual regression for item VH123456"
}
```

All fields except `scriptPath` are optional.

**Response:**
```json
{"ok": true}
```

---

#### `GET /test-cases/api/list/`

**Query params:** `search`

**Response:**
```json
{
  "scripts": [
    {
      "script_path": "items/vh123456.spec.js",
      "source": "registered",
      "item_id": "VH123456",
      "category": "visual_regression",
      "description": "…"
    }
  ],
  "total": 120
}
```

---

### Builder

#### `POST /builder/api/chat/`

Send a chat message to the AI assistant.

**Request body:**
```json
{
  "message": "Add a screenshot comparison step",
  "conversationId": "uuid-or-null",
  "currentCode": "// current editor contents…",
  "filename": "vh123456.spec.js"
}
```

**Response:**
```json
{
  "conversationId": "uuid",
  "response": "I've added a screenshot comparison step. Here's the updated test:",
  "codeUpdate": "import { test, expect } from '@playwright/test';\ntest(…)",
  "toolsUsed": ["update_code"]
}
```

`codeUpdate` is `null` if the AI did not invoke `update_code`.

---

#### `POST /builder/api/save/`

Save the generated script to the `generated/` directory.

**Request body:**
```json
{"code": "// playwright script…"}
```

**Response:**
```json
{"path": "generated/generated-1705316200.spec.js"}
```

---

### Admin Config

#### `POST /admin-config/ai/tools/<str:tool_id>/toggle/`

Toggle a tool's `enabled` flag.

**Request body:** (empty JSON object or empty body)

**Response:**
```json
{"success": true}
```

---

## CSRF

All state-changing JSON endpoints require the `X-CSRFToken` header with the value from the `csrftoken` cookie:

```javascript
function getCookie(name) {
  return document.cookie.split(';')
    .map(c => c.trim())
    .find(c => c.startsWith(name + '='))
    ?.split('=')[1] || '';
}

fetch('/suites/<uuid>/run/', {
  method: 'POST',
  headers: {
    'X-CSRFToken': getCookie('csrftoken'),
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({...})
});
```

---

## Pagination Parameters

Most paginated list endpoints accept:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number (1-based) |
| `page_size` | int | 25 | Rows per page; options: 10, 25, 50, 100 |
| `sort` | str | varies | Sort column name |
| `dir` | str | `asc`/`desc` | Sort direction |
| `search` | str | — | Text search |

Paginated HTML responses include:
- `start_item` / `end_item` — row numbers for display ("Showing 26–50 of 847")
- `total_pages`
- `page_range` — smart page number list with `'...'` gaps
