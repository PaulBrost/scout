# LLM Integration — SCOUT

SCOUT uses AI providers for three features: the **Builder** chat (test script generation), **Grammar & Spelling** analysis (text content), and **Visual Analysis** (screenshot QA). Providers are configured in the database via Admin > AI Settings > AI Providers and assigned per-feature. No AI dependency is required — every feature falls back to a built-in Mock provider that returns canned responses.

---

## Table of Contents

1. [Overview](#overview)
2. [AIProvider Model](#aiprovider-model)
3. [Provider Types](#provider-types)
4. [Provider Factory](#provider-factory)
5. [Feature Assignments](#feature-assignments)
6. [Provider Interface](#provider-interface)
7. [Admin Configuration](#admin-configuration)
8. [API Endpoints](#api-endpoints)
9. [Image Format Differences](#image-format-differences)
10. [Migration from Env Vars](#migration-from-env-vars)
11. [Adding a New Provider](#adding-a-new-provider)

---

## Overview

```
User triggers analysis / builder chat / test run
        |
        v
ai/provider.py :: get_provider_for_feature(feature)
        |
        ├─ Reads {feature}_provider_id from ai_settings table
        ├─ Looks up ai_providers row by UUID
        ├─ Instantiates + caches provider (5-min TTL)
        └─ Falls back to MockProvider if missing/disabled
        |
        v
Provider instance (one of):
        ├─ AnthropicProvider     → Anthropic Messages API
        ├─ AzureFoundryProvider  → Azure OpenAI Chat Completions API
        ├─ OpenAICompatProvider  → OpenAI / OpenRouter / Ollama
        └─ MockProvider          → Canned responses, no HTTP
        |
        v
analyze_text() / analyze_screenshot() / chat_completion() / etc.
        |
        v
Structured JSON → issues routed to Reviews / response shown in Builder
```

---

## AIProvider Model

**File:** `core/models.py`
**Table:** `ai_providers`

| Field | Type | Notes |
|---|---|---|
| `id` | UUIDField (PK) | Auto-generated |
| `name` | TextField | Display name, e.g. "Production GPT-4o" |
| `provider_type` | TextField (choices) | `anthropic`, `azure_openai`, or `openai_compat` |
| `api_key` | TextField | Stored in DB, never returned to browser |
| `model` | TextField | Model name — used by `anthropic` and `openai_compat` |
| `base_url` | TextField | API endpoint base URL — all types |
| `deployment_id` | TextField | Azure OpenAI deployment name — `azure_openai` only |
| `api_version` | TextField | Azure API version string — `azure_openai` only |
| `enabled` | BooleanField | Disabled providers are skipped by the factory |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |

Feature assignments are stored in the `ai_settings` table as key-value pairs:
- `builder_provider_id` — UUID or `"mock"`
- `text_provider_id` — UUID or `"mock"`
- `vision_provider_id` — UUID or `"mock"`

---

## Provider Types

### `anthropic` — Anthropic / Azure AI Foundry

**File:** `ai/anthropic_provider.py`

Uses the **Anthropic Messages API** format. Works with both the direct Anthropic API and Claude models deployed on Azure AI Foundry — they use identical request/response shapes.

| Setting | Value |
|---|---|
| Endpoint | `{base_url}messages` |
| Auth header | `x-api-key: {api_key}` |
| Version header | `anthropic-version: 2023-06-01` |
| Default base URL | `https://api.anthropic.com/v1/` |
| Response path | `content[0].text` |

**Key differences from OpenAI-style providers:**
- `system` is a top-level field in the request body, not a message with `role: system`
- `model` is included in the request body
- Response is `content[0].text`, not `choices[0].message.content`
- Auth uses `x-api-key` not `Authorization: Bearer`
- Image content uses `{type: "image", source: {type: "base64", media_type: "image/png", data: ...}}`

**Direct Anthropic API:**
- Base URL: leave blank (defaults to `https://api.anthropic.com/v1/`)
- API Key: from console.anthropic.com
- Model: e.g. `claude-sonnet-4-5`, `claude-opus-4-6`

**Azure AI Foundry (Anthropic models):**

Azure AI Foundry exposes Claude models through the native Anthropic Messages API, not the Azure OpenAI Chat Completions format. Use `anthropic`, **not** `azure_openai`.

- Base URL: `https://<resource>.services.ai.azure.com/anthropic/v1/`
- API Key: Azure API key
- Model: deployment name, e.g. `claude-sonnet-4-5-kkiser`

The provider appends `/messages` to the base URL, producing:
```
https://<resource>.services.ai.azure.com/anthropic/v1/messages
```

Example request body:
```json
{
  "model": "claude-sonnet-4-5",
  "max_tokens": 1000,
  "system": "You are a proofreading assistant...",
  "messages": [
    {"role": "user", "content": "Analyze this text..."}
  ]
}
```

---

### `azure_openai` — Azure OpenAI

**File:** `ai/azure_foundry.py`

Uses the **Azure OpenAI Chat Completions API** format. For GPT models deployed through Azure OpenAI, not for Anthropic models on Azure AI Foundry (use `anthropic` for those).

| Setting | Value |
|---|---|
| Endpoint | `{base_url}/openai/deployments/{deployment_id}/chat/completions?api-version={api_version}` |
| Auth header | `api-key: {api_key}` |
| Response path | `choices[0].message.content` |

Required fields:
- **Base URL** — resource endpoint, e.g. `https://my-resource.openai.azure.com`
- **Deployment ID** — name of the deployed model, e.g. `gpt-4o`
- **API Version** — defaults to `2024-02-01`

Example request body:
```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "max_completion_tokens": 1000
}
```

---

### `openai_compat` — OpenAI / OpenRouter / Ollama

**File:** `ai/openai_compat.py`

Uses the **OpenAI Chat Completions API** format. Works with any OpenAI-compatible endpoint.

| Setting | Value |
|---|---|
| Endpoint | `{base_url}chat/completions` |
| Auth header | `Authorization: Bearer {api_key}` (omitted if no key) |
| Default base URL | `https://api.openai.com/v1/` |
| Response path | `choices[0].message.content` |

Setting `base_url` to a compatible endpoint makes this provider work with:
- **OpenAI** — `https://api.openai.com/v1/` (default)
- **OpenRouter** — `https://openrouter.ai/api/v1/`
- **Ollama** — `http://localhost:11434/v1/`
- **LM Studio** — `http://localhost:1234/v1/`
- Any other OpenAI-compatible server

API key is optional — Ollama and LM Studio don't require one.

Example request body:
```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "max_completion_tokens": 1000
}
```

---

### Mock — Built-in Testing

**File:** `ai/mock.py`

Returns canned responses with no HTTP calls. Always available as "Mock" in feature dropdowns but not stored in `ai_providers`. Behavior controlled by `MOCK_AI_MODE` env var:

| Mode | Behavior |
|---|---|
| `clean` (default) | Returns empty issues — everything is "clean" |
| `issues` | Returns sample issues for testing the review pipeline |
| `error` | Raises exceptions to test error handling |

---

## Provider Factory

**File:** `ai/provider.py`

### `get_provider_for_feature(feature)`

Main entry point. Reads `{feature}_provider_id` from `ai_settings`, looks up the provider in `ai_providers`, instantiates it, and caches with a 5-minute TTL. Falls back to MockProvider if the setting is missing, set to `"mock"`, or points to a disabled/deleted provider.

```python
from ai.provider import get_provider_for_feature

provider = get_provider_for_feature('text')    # Grammar & Spelling
provider = get_provider_for_feature('vision')  # Visual Analysis
provider = get_provider_for_feature('builder') # Builder chat
```

### `get_provider()`

Backward-compatible entry point. Delegates to `get_provider_for_feature('builder')`.

### `invalidate_provider_cache(provider_id=None)`

Clears the in-memory cache. Called automatically when providers are saved or deleted via admin. Pass a specific UUID to clear one entry, or `None` to clear all.

### `_instantiate_provider(provider_type, config)`

Builds a provider instance from a type string and flat config dict. Used by the factory and by the admin test-connection endpoint to test unsaved configurations.

```python
from ai.provider import _instantiate_provider

provider = _instantiate_provider('anthropic', {
    'api_key': 'sk-ant-...',
    'model': 'claude-sonnet-4-5',
    'base_url': '',
})
```

---

## Feature Assignments

Each SCOUT feature independently selects which provider to use:

| Feature | Setting Key | Used By |
|---|---|---|
| **Builder** | `builder_provider_id` | `builder/chat_manager.py` — AI test builder chat |
| **Text** | `text_provider_id` | `tasks/post_execution.py` — `run_text_analysis()`, `analyze_run_text()` |
| **Vision** | `vision_provider_id` | `tasks/post_execution.py` — `run_visual_analysis()`, `analyze_run_screenshots()` |

Assignments are managed via dropdowns in Admin > AI Settings on the Builder Prompt, Grammar & Spelling, and Visual Analysis tabs.

---

## Provider Interface

All providers implement `BaseProvider` (defined in `ai/provider.py`):

| Method | Purpose | Return |
|---|---|---|
| `analyze_text(text, language, custom_prompt)` | Grammar/spelling analysis | `{issues, issuesFound, summary, raw, model, durationMs}` |
| `analyze_screenshot(screenshot_b64, context, custom_prompt)` | Visual QA on base64 PNG | `{issues, issuesFound, summary, raw, model, durationMs}` |
| `compare_text(baseline, current, language)` | Diff two text versions | `{differences, hasDifferences, raw, model, durationMs}` |
| `generate_test(description, context)` | Generate Playwright test code | Raw code string |
| `chat_completion(messages, options)` | Free-form chat (Builder) | Response text string |
| `health_check()` | Connection test | `{healthy, provider, details}` |

### Custom Prompts

`analyze_text` and `analyze_screenshot` accept an optional `custom_prompt` parameter. When provided, it replaces the default analysis prompt and is wrapped with standard JSON response format instructions via `prompts.wrap_custom_prompt()`.

Custom prompts are stored in `ai_settings`:
- `text_analysis_prompt` — used by text analysis
- `vision_analysis_prompt` — used by visual analysis

### Response Parsing

`BaseProvider._parse_response(raw)` handles AI response normalization:
1. Strips markdown code fences (` ```json ... ``` `)
2. Parses JSON — accepts both `{summary, issues}` objects and plain arrays
3. Returns `{summary: '', issues: []}` on parse failure

---

## Text Extraction Convention (`[SCOUT_TEXT]`)

For AI text analysis to work on a run, test scripts must explicitly extract and log page text using the `[SCOUT_TEXT]` marker convention (analogous to `[SCOUT_QC]` for QC results).

### How It Works

1. **Test scripts** emit extracted text via `console.log("[SCOUT_TEXT] " + JSON.stringify({label, text}))`
2. **Playwright captures** this in stdout, which becomes the `execution_log` on `test_run_scripts`
3. **`executor/runner.py`** provides `parse_text_content(execution_log)` to extract all `[SCOUT_TEXT]` blocks
4. **`tasks/post_execution.py`** sends only the extracted text (not the full Playwright output) to the AI provider
5. **Run detail page** checks for `[SCOUT_TEXT]` markers and hides the "Analyze Text" button when none exist

### Using the Helper

The simplest approach is `extractAndLogItemText(page, label)` from `playwright/src/helpers/items.js`:

```javascript
const { extractAndLogItemText, navigateAllScreens } = require('../helpers/items');

// Extract text from current screen and emit [SCOUT_TEXT]
const text = await extractAndLogItemText(page, 'Screen 1');

// Or use it in a screen navigation callback
await navigateAllScreens(page, envConfig, async (page, screenIndex) => {
  await page.screenshot({ path: `screen-${screenIndex}.png` });
  await extractAndLogItemText(page, `Screen ${screenIndex}`);
});
```

You can also emit `[SCOUT_TEXT]` manually in any test script:

```javascript
const text = await page.locator('#content').innerText();
console.log(`[SCOUT_TEXT] ${JSON.stringify({ label: 'Main content', text })}`);
```

### Button Visibility

- **Analyze Screenshots** — shown only when the run has screenshots in `run_screenshots`
- **Analyze Text** — shown only when at least one `test_run_scripts.execution_log` contains `[SCOUT_TEXT]`
- Both buttons also require their respective feature to be enabled in AI Settings

---

## Admin Configuration

**Location:** Admin > AI Settings (`/admin-config/ai/`)

### Tab Structure

```
[AI Providers] [Builder Prompt] [Grammar & Spelling] [Visual Analysis]
```

### AI Providers Tab

- **Table:** Name, Type (display name), Enabled, Actions (Edit, Test, Delete)
- **Add Provider** button opens a modal with:
  - Name (text)
  - Provider Type (select — shows/hides conditional fields)
  - API Key (password, shows "Configured" placeholder on edit, blank preserves existing)
  - Model (anthropic + openai_compat only)
  - Base URL (all types, label/hint changes per type)
  - Deployment ID (azure_openai only)
  - API Version (azure_openai only)
  - Enabled toggle
  - Test Connection / Save / Cancel

### Builder Prompt Tab

- Provider dropdown (all enabled providers + Mock)
- System prompt textarea
- Max turns, tool calling toggle
- AI Tools enable/disable table

### Grammar & Spelling Tab

- Provider dropdown
- Enabled toggle
- Custom analysis prompt
- Default language setting

### Visual Analysis Tab

- Provider dropdown
- Enabled toggle
- Custom analysis prompt
- Diff threshold

---

## API Endpoints

All endpoints require admin (staff) authentication.

### `POST /admin-config/ai/providers/`

**View:** `list_providers`

Returns all providers with API keys masked.

Response:
```json
{
  "ok": true,
  "providers": [
    {
      "id": "uuid",
      "name": "Production GPT-4o",
      "provider_type": "azure_openai",
      "has_api_key": true,
      "api_key": "",
      "model": "",
      "base_url": "https://...",
      "deployment_id": "gpt-4o",
      "api_version": "2024-02-01",
      "enabled": true
    }
  ]
}
```

### `GET /admin-config/ai/providers/<uuid>/`

**View:** `get_provider`

Returns a single provider (API key masked). Used by the edit modal to populate fields.

### `POST /admin-config/ai/providers/save/`

**View:** `save_provider`

Create or update a provider. Include `id` to update; omit for create. Submitting blank `api_key` preserves the existing key on update.

Request body:
```json
{
  "id": "uuid (optional — omit for create)",
  "name": "My Provider",
  "provider_type": "anthropic",
  "api_key": "sk-ant-...",
  "model": "claude-sonnet-4-5",
  "base_url": "",
  "deployment_id": "",
  "api_version": "",
  "enabled": true
}
```

Response: `{"ok": true, "id": "uuid"}`

### `POST /admin-config/ai/providers/delete/`

**View:** `delete_provider`

Deletes a provider. Any feature assignments referencing it are reset to `"mock"`.

Request: `{"id": "uuid"}`
Response: `{"ok": true}`

### `POST /admin-config/ai/providers/test/`

**View:** `test_provider_connection`

Tests a provider connection. Two modes:
- **By ID:** `{"id": "uuid"}` — tests a saved provider
- **By config:** `{"provider_type": "anthropic", "api_key": "...", ...}` — tests unsaved form values

Response:
```json
{"ok": true, "message": "Connection successful — ok", "durationMs": 1234}
```

### `POST /admin-config/ai/feature-provider/`

**View:** `save_feature_provider`

Assigns a provider to a feature.

Request: `{"feature": "builder|text|vision", "providerId": "uuid or mock"}`
Response: `{"ok": true}`

---

## Image Format Differences

When calling `analyze_screenshot`, each provider formats image content differently in the API request:

### Anthropic

```json
{
  "type": "image",
  "source": {
    "type": "base64",
    "media_type": "image/png",
    "data": "<base64>"
  }
}
```

### Azure OpenAI / OpenAI compat

```json
{
  "type": "image_url",
  "image_url": {
    "url": "data:image/png;base64,<base64>"
  }
}
```

Each provider handles this internally — callers always pass raw base64 to `analyze_screenshot()`.

---

## Migration from Env Vars

Prior to this system, the AI provider was configured globally via the `AI_PROVIDER` env var. Data migration `0020_seed_ai_providers` handles the transition:

| Env Var State | Migration Action |
|---|---|
| `AI_PROVIDER=azure` | Creates `azure_openai` provider from `AZURE_*` env vars, assigns to all 3 features |
| `AI_PROVIDER=ollama` | Creates `openai_compat` provider with `http://{OLLAMA_HOST}/v1/` base URL, assigns to all 3 features |
| `AI_PROVIDER=mock` | No provider created, features default to Mock |

The migration also cleans up old `ai_settings` keys (`text_provider_type`, `text_provider_config`, `vision_provider_type`, `vision_provider_config`).

Env vars in `settings.py` are retained for the migration to read but are no longer used at runtime. The comment in `settings.py` and `.env.example` note they are migration-only.

---

## Adding a New Provider

1. **Create provider class** in `ai/` — subclass `BaseProvider`, implement all methods:
   ```python
   # ai/my_provider.py
   from .provider import BaseProvider
   from . import prompts as p

   class MyProvider(BaseProvider):
       def __init__(self, config):
           self.api_key = config.get('api_key', '')
           self.model = config.get('model', '')
           # ...

       def analyze_text(self, text, language='English', custom_prompt=None):
           # ...

       def analyze_screenshot(self, screenshot_b64, context='', custom_prompt=None):
           # ...

       # ... remaining methods
   ```

2. **Register in factory** — add a branch in `ai/provider.py` `_instantiate_provider()`:
   ```python
   elif provider_type == 'my_provider':
       from .my_provider import MyProvider
       return MyProvider(config)
   ```

3. **Add choice to model** — append to `AIProvider.PROVIDER_TYPE_CHOICES` in `core/models.py`:
   ```python
   ('my_provider', 'My Provider Display Name'),
   ```
   Then run `makemigrations` + `migrate`.

4. **Update admin template** — in `templates/admin_config/ai_settings.html`, update `PROVIDER_TYPE_LABELS` in the `<script>` block and update `onModalTypeChange()` if the new provider needs different field visibility.

No additional migration is needed unless new database fields are required — `provider_type` is a TextField and choices are not enforced at the DB level.

---

## Files Reference

| File | Purpose |
|---|---|
| `core/models.py` | `AIProvider` model definition |
| `ai/provider.py` | `BaseProvider` class, factory (`get_provider_for_feature`), cache |
| `ai/anthropic_provider.py` | Anthropic Messages API provider |
| `ai/azure_foundry.py` | Azure OpenAI Chat Completions provider |
| `ai/openai_compat.py` | OpenAI-compatible provider (OpenAI, OpenRouter, Ollama) |
| `ai/mock.py` | Mock provider for testing |
| `ai/prompts.py` | Prompt templates and `wrap_custom_prompt()` |
| `admin_config/views.py` | CRUD endpoints + feature assignment |
| `admin_config/urls.py` | URL routes for provider management |
| `templates/admin_config/ai_settings.html` | Admin UI (tabs, modal, JS) |
| `builder/chat_manager.py` | Builder chat — calls `get_provider_for_feature('builder')` |
| `tasks/post_execution.py` | Post-execution analysis — calls `get_provider_for_feature('text'/'vision')` |
| `core/migrations/0019_aiprovider.py` | Schema migration |
| `core/migrations/0020_seed_ai_providers.py` | Data migration (env var seed) |
