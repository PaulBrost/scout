# Data Models

All models are defined in `core/models.py`. The database uses PostgreSQL. Most primary keys are UUIDs (`models.UUIDField(default=uuid.uuid4)`); the exception is `Item`, which uses an `AutoField` integer PK for URL-friendly numeric IDs.

---

## Entity Relationship Overview

```
Environment ─┬──────────────────── Assessment ──── Item
             │                                      │
             │  UserEnvironment                     │ (via item_id FK)
             │  (user ↔ environment)               │
             │                                      ▼
             └── TestSuite ──── TestSuiteScript   TestScript
                       │                          (registry)
                       ▼
                   TestRun ──── TestRunScript
                       │
                       ├── TestResult ──── Baseline
                       │
                       └── AIAnalysis ──── Review


AISetting    (key/value config)
AITool       (tool registry)
AIConversation (chat history)
```

---

## Models

### Environment

Represents a deployment target (e.g., "NAEP Production", "Dev QA Server").

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField PK | |
| `name` | CharField(200) | Unique |
| `base_url` | URLField | Base URL for test navigation |
| `auth_type` | CharField | `password_only` / `username_password` / `none` |
| `credentials` | JSONField | `{username, password}` — never store in plaintext |
| `launcher_config` | JSONField | Extra Playwright launch options |
| `notes` | TextField | Free-text notes |
| `is_default` | BooleanField | One environment flagged as default |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |

---

### UserEnvironment

Junction table granting a user access to an environment.

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField PK | |
| `user` | FK → User | |
| `environment` | FK → Environment | |

Unique constraint: `(user, environment)`.

---

### Assessment

An assessment form (e.g., "Grade 4 Math 2024 Form A").

| Field | Type | Notes |
|-------|------|-------|
| `id` | CharField(100) PK | NAEP assessment ID (e.g., "M4-2024-A") |
| `environment` | FK → Environment | Nullable |
| `name` | CharField(500) | |
| `subject` | CharField(100) | e.g., "Mathematics", "Reading" |
| `grade` | CharField(50) | e.g., "4", "8", "12" |
| `year` | CharField(20) | e.g., "2024" |
| `item_count` | IntegerField | Expected count (metadata) |
| `form_value` | CharField(100) | Form identifier |
| `description` | TextField | |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |

---

### Item

An individual test item within an assessment.

| Field | Type | Notes |
|-------|------|-------|
| `numeric_id` | AutoField PK | Integer; used in URLs (`/items/42/`) |
| `item_id` | TextField | NAEP text ID (e.g., "VH123456"), unique |
| `assessment` | FK → Assessment | Nullable |
| `title` | TextField | Display title |
| `category` | CharField(100) | e.g., "visual_regression", "content_validation" |
| `tier` | CharField(50) | e.g., "smoke", "core", "full" |
| `languages` | JSONField | `["en", "es"]` |
| `metadata` | JSONField | Arbitrary extra data |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |

> **Two IDs**: `numeric_id` is the URL/PK (integer). `item_id` is the NAEP text identifier used to look up items in the assessment platform.

---

### Baseline

An approved reference screenshot for visual regression testing.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField PK | |
| `item` | FK → Item | via `item_id` |
| `browser` | CharField(50) | e.g., "chrome", "firefox" |
| `device_profile` | CharField(100) | e.g., "Desktop Chrome", "Chromebook" |
| `version` | CharField(50) | e.g., "v2024" |
| `screenshot_path` | TextField | Relative path to stored PNG |
| `approved_by` | FK → User | Nullable |
| `approved_at` | DateTimeField | Nullable |
| `created_at` | DateTimeField | Auto |

Unique constraint: `(item, browser, device_profile, version)`.

---

### TestSuite

A named collection of Playwright scripts to run together.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField PK | |
| `name` | CharField(200) | |
| `description` | TextField | |
| `environment` | FK → Environment | Nullable; used for RBAC scoping |
| `browser_profiles` | JSONField | `["Desktop Chrome", "Chromebook"]` |
| `schedule` | JSONField | Cron-like config (future use) |
| `created_by` | FK → User | Nullable |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |

---

### TestSuiteScript

Individual `.spec.js` file included in a suite.

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField PK | |
| `suite` | FK → TestSuite | |
| `script_path` | TextField | Relative to `PLAYWRIGHT_TESTS_DIR` |
| `order` | IntegerField | Execution order (default 0) |

Unique constraint: `(suite, script_path)`.

---

### TestRun

One execution of a suite (or ad-hoc script).

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField PK | |
| `suite` | FK → TestSuite | Nullable (ad-hoc runs have no suite) |
| `status` | CharField | `running` / `completed` / `failed` / `cancelled` |
| `trigger_type` | CharField | `manual` / `dashboard` / `scheduled` |
| `config` | JSONField | Run-time options passed to executor |
| `summary` | JSONField | `{passed, failed, errors, total}` — written at completion |
| `notes` | TextField | |
| `started_at` | DateTimeField | |
| `completed_at` | DateTimeField | Nullable |
| `created_at` | DateTimeField | Auto |

---

### TestRunScript

One script's execution result within a `TestRun`.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField PK | |
| `run` | FK → TestRun | |
| `script_path` | TextField | |
| `status` | CharField | `queued` / `running` / `passed` / `failed` / `error` |
| `duration_ms` | IntegerField | Nullable |
| `error_message` | TextField | Nullable |
| `execution_log` | TextField | Full stdout/stderr from Playwright |
| `trace_path` | TextField | Relative path to `trace.zip` |
| `video_path` | TextField | Relative path to video |
| `started_at` | DateTimeField | Nullable |
| `completed_at` | DateTimeField | Nullable |

---

### TestResult

Per-item result within a run (legacy item-level model).

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField PK | |
| `run` | FK → TestRun | |
| `item` | FK → Item | Nullable |
| `browser` | CharField(50) | |
| `device_profile` | CharField(100) | |
| `status` | CharField | `passed` / `failed` / `error` / `skipped` |
| `duration_ms` | IntegerField | |
| `error_message` | TextField | |
| `screenshot_path` | TextField | |
| `diff_path` | TextField | Path to diff image |
| `diff_ratio` | FloatField | 0.0–1.0 pixel difference ratio |
| `created_at` | DateTimeField | Auto |

---

### AIAnalysis

AI evaluation of a test result (screenshot or text).

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField PK | |
| `run` | FK → TestRun | Nullable |
| `item` | FK → Item | Nullable |
| `analysis_type` | CharField | e.g., `visual_regression`, `content_validation` |
| `status` | CharField | `pending` / `processing` / `completed` / `skipped` / `error` |
| `issues_found` | BooleanField | True if AI detected problems |
| `issues` | JSONField | `[{type, detail, severity}, …]` |
| `raw_response` | TextField | Full AI model response text |
| `model_used` | CharField | e.g., `gpt-4o`, `qwen2.5:14b` |
| `screenshot_path` | TextField | Path to screenshot for vision analysis |
| `duration_ms` | IntegerField | AI call latency |
| `created_at` | DateTimeField | Auto |

---

### Review

Human review decision on an `AIAnalysis`.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField PK | |
| `analysis` | FK → AIAnalysis | |
| `item_id` | CharField | Denormalized for quick filtering |
| `analysis_type` | CharField | Denormalized |
| `status` | CharField | `pending` / `approved` / `dismissed` / `bug_filed` |
| `reviewer` | FK → User | Nullable; set when reviewed |
| `notes` | TextField | Reviewer notes |
| `bug_url` | TextField | Link to filed bug |
| `reviewed_at` | DateTimeField | Nullable |
| `created_at` | DateTimeField | Auto |

---

### TestScript

Registry of discovered `.spec.js` files, merged with filesystem scan.

| Field | Type | Notes |
|-------|------|-------|
| `id` | AutoField PK | |
| `script_path` | TextField | Unique; relative to `PLAYWRIGHT_TESTS_DIR` |
| `description` | TextField | |
| `item_id` | CharField | Associated NAEP item ID |
| `assessment_id` | CharField | Associated assessment ID |
| `category` | CharField | e.g., `visual_regression` |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |

---

### AISetting

Key/value configuration for AI behavior.

| Field | Type | Notes |
|-------|------|-------|
| `key` | CharField PK | e.g., `system_prompt`, `max_conversation_turns` |
| `value` | TextField | JSON-encoded value |
| `updated_at` | DateTimeField | Auto |

Common keys:

| Key | Default | Description |
|-----|---------|-------------|
| `system_prompt` | (built-in) | System prompt for builder chat |
| `max_conversation_turns` | `50` | Max AI exchanges per conversation |
| `tool_calling_enabled` | `true` | Whether AI may invoke tools |

---

### AITool

Pluggable tools available to the AI in the builder chat.

| Field | Type | Notes |
|-------|------|-------|
| `id` | CharField PK | e.g., `explain_code`, `update_code` |
| `name` | CharField | Display name |
| `description` | TextField | Shown to AI in system prompt |
| `category` | CharField | e.g., `code`, `filesystem`, `database` |
| `enabled` | BooleanField | Togglable at runtime via admin config |
| `parameters` | JSONField | JSON Schema for tool parameters |
| `created_at` | DateTimeField | Auto |

---

### AIConversation

Persistent chat history for the builder.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUIDField PK | The `conversationId` passed in API calls |
| `messages` | JSONField | `[{role, content}, …]` |
| `created_at` | DateTimeField | Auto |
| `last_active_at` | DateTimeField | Updated on each turn |

---

## JSON Field Conventions

| Model.field | Shape |
|-------------|-------|
| `Environment.credentials` | `{"username": "...", "password": "..."}` |
| `TestSuite.browser_profiles` | `["Desktop Chrome", "firefox-desktop"]` |
| `TestSuite.schedule` | `{"cron": "0 2 * * *"}` (future use) |
| `TestRun.summary` | `{"passed": 12, "failed": 1, "errors": 0, "total": 13}` |
| `AIAnalysis.issues` | `[{"type": "spelling", "text": "teh", "suggestion": "the", "context": "..."}]` |
| `Item.languages` | `["en", "es"]` |
| `AITool.parameters` | JSON Schema object |
