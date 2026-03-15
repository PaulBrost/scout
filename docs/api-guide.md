# SCOUT REST API Guide

The SCOUT API allows external systems to create test scripts, manage test suites, trigger test runs, and retrieve results programmatically.

**Base URL:** `/api/v1/`

---

## Authentication

Every request (except `/api/v1/health/`) must include a Bearer token in the `Authorization` header:

```
Authorization: Bearer scout_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

API keys are created by admins in **Admin → API**. Each key is:

- Scoped to a single **environment** — the client can only access data within that environment
- Shown **once** at creation — copy it immediately; SCOUT stores only a SHA-256 hash
- Prefixed with `scout_` for easy identification in logs and configs

### Error responses

All errors follow a consistent format:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Missing or invalid Authorization header. Use: Bearer <api_key>"
  }
}
```

| Status | Code | Meaning |
|--------|------|---------|
| 401 | `unauthorized` | Missing, empty, or invalid API key |
| 403 | `forbidden` | Client is disabled or key has expired |
| 429 | `rate_limited` | Rate limit exceeded (see headers) |

---

## Rate Limiting

Each API client has a configurable rate limit (default: 60 requests/minute). Every response includes rate-limit headers:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Max requests per minute |
| `X-RateLimit-Remaining` | Requests left in current window |
| `X-RateLimit-Reset` | Unix epoch when the window resets |
| `Retry-After` | Seconds to wait (only on 429 responses) |

---

## Endpoints

### Health Check

#### `GET /api/v1/health/`

No authentication required. Returns API availability.

```bash
curl https://your-scout-host/api/v1/health/
```

```json
{"status": "ok"}
```

---

### Scripts

#### `GET /api/v1/scripts/`

List test scripts in the client's environment.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 25 | Results per page (max 100) |
| `search` | string | | Filter by script path or description |

```bash
curl -H "Authorization: Bearer $KEY" \
  "https://your-scout-host/api/v1/scripts/?page_size=10"
```

```json
{
  "scripts": [
    {
      "id": 42,
      "script_path": "items/vh123456.spec.js",
      "description": "Login flow test",
      "test_type": "functional",
      "browser": "chromium",
      "viewport": "1920x1080",
      "item_id": "VH123456",
      "assessment_id": null,
      "category": "auth",
      "tags": ["smoke", "login"],
      "created_at": "2026-03-14T10:30:00Z",
      "updated_at": "2026-03-14T10:30:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 10
}
```

---

#### `GET /api/v1/scripts/{id}/`

Get details for a single script.

```bash
curl -H "Authorization: Bearer $KEY" \
  https://your-scout-host/api/v1/scripts/42/
```

---

#### `POST /api/v1/scripts/`

Create a new test script. Writes the file to disk and registers it in the database.

**Request body:**

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `script_path` | yes | | Relative path within the tests directory (e.g., `items/my-test.spec.js`) |
| `content` | yes | | Full JavaScript file content |
| `description` | no | | Human-readable description |
| `test_type` | no | `functional` | One of: `functional`, `visual_regression`, `ai_content`, `ai_visual`, `qc_checklist` |
| `browser` | no | `chromium` | `chromium`, `firefox`, or `webkit` |
| `viewport` | no | `1920x1080` | e.g., `1920x1080`, `1280x720`, `375x812` |
| `item_id` | no | | NAEP item identifier (e.g., `VH123456`) |
| `assessment_id` | no | | Assessment identifier |
| `category` | no | | Grouping category |
| `tags` | no | | Comma-separated string or JSON array |

```bash
curl -X POST -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "script_path": "items/vh999999.spec.js",
    "content": "const { test, expect } = require(\"@playwright/test\");\ntest(\"example\", async ({ page }) => {\n  await page.goto(\"/\");\n});",
    "description": "Basic page load test",
    "test_type": "functional"
  }' \
  https://your-scout-host/api/v1/scripts/
```

**Response (201):**

```json
{
  "id": 43,
  "script_path": "items/vh999999.spec.js",
  "environment_id": "a1b2c3d4-...",
  "created_at": "2026-03-14T10:35:00Z"
}
```

> **Note:** Helper import paths (e.g., `require('../src/helpers/...')`) are automatically corrected based on the file's depth in the directory tree.

---

#### `POST /api/v1/scripts/{id}/run/`

Start a test run for a single script. Returns immediately; the test executes in the background.

**Request body (optional):**

| Field | Description |
|-------|-------------|
| `browser` | Override the script's default browser |
| `viewport` | Override the script's default viewport |

```bash
curl -X POST -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{}' \
  https://your-scout-host/api/v1/scripts/42/run/
```

**Response (202):**

```json
{
  "run_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "running",
  "status_url": "/api/v1/runs/f47ac10b-58cc-4372-a567-0e02b2c3d479/status/"
}
```

---

### Suites

#### `GET /api/v1/suites/`

List test suites in the client's environment.

**Query parameters:** `page`, `page_size`, `search` (same as scripts).

```bash
curl -H "Authorization: Bearer $KEY" \
  https://your-scout-host/api/v1/suites/
```

```json
{
  "suites": [
    {
      "id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
      "name": "Smoke Suite",
      "description": "Quick sanity checks",
      "environment_id": "a1b2c3d4-...",
      "created_at": "2026-03-10T08:00:00Z",
      "updated_at": "2026-03-14T10:00:00Z",
      "script_count": 5
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 25
}
```

---

#### `GET /api/v1/suites/{id}/`

Get suite details including its script list.

```bash
curl -H "Authorization: Bearer $KEY" \
  https://your-scout-host/api/v1/suites/d290f1ee-6c54-4b01-90e6-d701748f0851/
```

```json
{
  "id": "d290f1ee-...",
  "name": "Smoke Suite",
  "description": "Quick sanity checks",
  "environment_id": "a1b2c3d4-...",
  "created_by": "api:CI Pipeline",
  "created_at": "2026-03-10T08:00:00Z",
  "updated_at": "2026-03-14T10:00:00Z",
  "scripts": [
    {"script_path": "items/vh001.spec.js", "browser": "chromium", "viewport": "1920x1080"},
    {"script_path": "items/vh002.spec.js", "browser": "chromium", "viewport": "1920x1080"}
  ]
}
```

---

#### `POST /api/v1/suites/`

Create a new test suite.

**Request body:**

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Suite name |
| `description` | no | Description |
| `scripts` | no | Array of script entries (see below) |

Each script entry can be a string (script path) or an object:

```json
{"script_path": "items/vh001.spec.js", "browser": "chromium", "viewport": "1920x1080"}
```

```bash
curl -X POST -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Nightly Regression",
    "description": "Full regression suite",
    "scripts": [
      {"script_path": "items/vh001.spec.js"},
      {"script_path": "items/vh002.spec.js", "browser": "firefox"}
    ]
  }' \
  https://your-scout-host/api/v1/suites/
```

**Response (201):**

```json
{
  "id": "a8098c1a-f86e-11da-bd1a-00112444be1e",
  "name": "Nightly Regression",
  "environment_id": "a1b2c3d4-...",
  "scripts": 2
}
```

---

#### `PUT /api/v1/suites/{id}/`

Update a suite's name, description, and/or script list. Replaces all script associations.

```bash
curl -X PUT -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Suite",
    "scripts": [
      {"script_path": "items/vh001.spec.js"},
      {"script_path": "items/vh003.spec.js"}
    ]
  }' \
  https://your-scout-host/api/v1/suites/a8098c1a-f86e-11da-bd1a-00112444be1e/
```

**Response (200):**

```json
{"ok": true, "id": "a8098c1a-..."}
```

---

#### `DELETE /api/v1/suites/{id}/`

Delete a suite and its script associations. Does not delete the underlying test scripts or historical runs.

```bash
curl -X DELETE -H "Authorization: Bearer $KEY" \
  https://your-scout-host/api/v1/suites/a8098c1a-f86e-11da-bd1a-00112444be1e/
```

**Response (200):**

```json
{"ok": true}
```

---

#### `POST /api/v1/suites/{id}/run/`

Start a test run for all scripts in the suite. Returns immediately; execution happens in the background.

```bash
curl -X POST -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{}' \
  https://your-scout-host/api/v1/suites/d290f1ee-6c54-4b01-90e6-d701748f0851/run/
```

**Response (202):**

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "scripts": 5,
  "status_url": "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/status/"
}
```

---

### Runs

#### `GET /api/v1/runs/`

List test runs in the client's environment.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 25 | Results per page (max 100) |
| `status` | string | | Filter: `running`, `completed`, `failed`, `cancelled` |

```bash
curl -H "Authorization: Bearer $KEY" \
  "https://your-scout-host/api/v1/runs/?status=completed&page_size=5"
```

```json
{
  "runs": [
    {
      "id": "550e8400-...",
      "status": "completed",
      "trigger_type": "api",
      "suite_id": "d290f1ee-...",
      "suite_name": "Smoke Suite",
      "environment_id": "a1b2c3d4-...",
      "summary": {"passed": 4, "failed": 1, "errors": 0, "issues": 0, "total": 5},
      "notes": "API Suite: Smoke Suite",
      "queued_at": "2026-03-14T10:30:00Z",
      "started_at": "2026-03-14T10:30:01Z",
      "completed_at": "2026-03-14T10:32:15Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 5
}
```

---

#### `GET /api/v1/runs/{id}/`

Get full run details including per-script results.

```bash
curl -H "Authorization: Bearer $KEY" \
  https://your-scout-host/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/
```

```json
{
  "id": "550e8400-...",
  "status": "completed",
  "trigger_type": "api",
  "suite_id": "d290f1ee-...",
  "suite_name": "Smoke Suite",
  "summary": {"passed": 4, "failed": 1, "errors": 0, "issues": 0, "total": 5},
  "queued_at": "2026-03-14T10:30:00Z",
  "started_at": "2026-03-14T10:30:01Z",
  "completed_at": "2026-03-14T10:32:15Z",
  "scripts": [
    {
      "id": "6ba7b810-...",
      "script_path": "items/vh001.spec.js",
      "browser": "chromium",
      "viewport": "1920x1080",
      "status": "passed",
      "duration_ms": 4500,
      "error_message": null,
      "started_at": "2026-03-14T10:30:01Z",
      "completed_at": "2026-03-14T10:30:06Z"
    },
    {
      "id": "6ba7b811-...",
      "script_path": "items/vh002.spec.js",
      "browser": "chromium",
      "viewport": "1920x1080",
      "status": "failed",
      "duration_ms": 8200,
      "error_message": "expect(locator).toHaveScreenshot() failed...",
      "started_at": "2026-03-14T10:30:06Z",
      "completed_at": "2026-03-14T10:30:14Z"
    }
  ]
}
```

---

#### `GET /api/v1/runs/{id}/status/`

Lightweight status check for polling. Returns the run status and a summary of script statuses without full script details.

```bash
curl -H "Authorization: Bearer $KEY" \
  https://your-scout-host/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/status/
```

```json
{
  "id": "550e8400-...",
  "status": "running",
  "summary": null,
  "started_at": "2026-03-14T10:30:01Z",
  "completed_at": null,
  "script_statuses": {
    "passed": 3,
    "running": 1,
    "queued": 1
  }
}
```

**Polling pattern:**

```bash
# Poll every 5 seconds until completed
while true; do
  STATUS=$(curl -s -H "Authorization: Bearer $KEY" \
    https://your-scout-host/api/v1/runs/$RUN_ID/status/ | jq -r '.status')
  echo "Status: $STATUS"
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 5
done
```

---

## Common Workflows

### 1. Create a script and run it

```bash
# Create the script
SCRIPT=$(curl -s -X POST -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"script_path": "items/my-test.spec.js", "content": "..."}' \
  https://your-scout-host/api/v1/scripts/)

SCRIPT_ID=$(echo $SCRIPT | jq -r '.id')

# Run it
RUN=$(curl -s -X POST -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d '{}' \
  https://your-scout-host/api/v1/scripts/$SCRIPT_ID/run/)

RUN_ID=$(echo $RUN | jq -r '.run_id')

# Poll for completion
while true; do
  RESULT=$(curl -s -H "Authorization: Bearer $KEY" \
    https://your-scout-host/api/v1/runs/$RUN_ID/status/)
  STATUS=$(echo $RESULT | jq -r '.status')
  echo "Run status: $STATUS"
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 5
done

# Get full results
curl -s -H "Authorization: Bearer $KEY" \
  https://your-scout-host/api/v1/runs/$RUN_ID/ | jq .
```

### 2. Create a suite and trigger a run

```bash
# Create suite with existing scripts
SUITE=$(curl -s -X POST -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CI Smoke Tests",
    "scripts": [
      {"script_path": "items/vh001.spec.js"},
      {"script_path": "items/vh002.spec.js"}
    ]
  }' \
  https://your-scout-host/api/v1/suites/)

SUITE_ID=$(echo $SUITE | jq -r '.id')

# Run the suite
curl -s -X POST -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d '{}' \
  https://your-scout-host/api/v1/suites/$SUITE_ID/run/ | jq .
```

### 3. List recent failed runs

```bash
curl -s -H "Authorization: Bearer $KEY" \
  "https://your-scout-host/api/v1/runs/?status=failed&page_size=10" | jq '.runs[] | {id, completed_at, summary}'
```

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created (new script or suite) |
| 202 | Accepted (run started, executing in background) |
| 400 | Bad request (validation error, invalid JSON) |
| 401 | Unauthorized (missing or invalid API key) |
| 403 | Forbidden (client disabled, key expired, access denied) |
| 404 | Not found (resource doesn't exist or is in a different environment) |
| 405 | Method not allowed |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
