# AI Integration

SCOUT integrates AI for two distinct purposes:

1. **Analysis** — automated quality checks on test results (text content, screenshots)
2. **Generation** — interactive chat assistant that writes and modifies Playwright scripts

Both paths use the same provider abstraction layer (`ai/provider.py`).

---

## Provider Abstraction

### `BaseProvider` (`ai/provider.py`)

All providers implement this interface:

```python
class BaseProvider:
    def analyze_text(self, text: str, language: str = 'English') -> dict: ...
    def analyze_screenshot(self, screenshot_b64: str, context: str = '') -> dict: ...
    def compare_text(self, baseline: str, current: str, language: str = 'English') -> dict: ...
    def generate_test(self, description: str, context: dict = None) -> str: ...
    def health_check(self) -> dict: ...
    def chat_completion(self, messages: list, options: dict = None) -> str: ...
```

### Return shapes

**`analyze_text` / `analyze_screenshot` / `compare_text`:**
```python
{
    "issuesFound": bool,
    "issues": [...],     # list of issue dicts
    "raw": str,          # raw model response
    "model": str,        # model name used
    "durationMs": int
}
```

**`chat_completion`:**
Returns a plain string — the assistant's message content.

### `get_provider()` factory

```python
from ai.provider import get_provider
provider = get_provider()  # returns singleton based on AI_PROVIDER env var
```

The singleton is created once per process and reused. Switching providers requires restarting the server/worker (or clearing `_provider_instance`).

| `AI_PROVIDER` value | Class loaded |
|--------------------|-------------|
| `mock` | `ai.mock.MockProvider` |
| `azure` | `ai.azure_foundry.AzureFoundryProvider` |
| `ollama` | `ai.ollama.OllamaProvider` |

---

## Azure AI Foundry Provider (`ai/azure_foundry.py`)

Targets the Azure OpenAI API (same API shape as OpenAI Chat Completions).

### Configuration

| Setting | Env var | Default |
|---------|---------|---------|
| Endpoint | `AZURE_ENDPOINT` | — |
| API key | `AZURE_API_KEY` | — |
| Text deployment | `AZURE_TEXT_DEPLOYMENT` | `gpt-4o` |
| Vision deployment | `AZURE_VISION_DEPLOYMENT` | `gpt-4o` |
| API version | `AZURE_API_VERSION` | `2024-02-01` |

### HTTP call

```
POST {endpoint}/openai/deployments/{deployment}/chat/completions?api-version={version}
Headers: api-key: {key}
Body: {"messages": [...], "max_tokens": N}
```

### Retry logic

Up to 3 attempts with exponential backoff on `429` (rate limit) responses:
- Attempt 1: immediate
- Attempt 2: 2s delay
- Attempt 3: 4s delay

### Vision analysis

The `analyze_screenshot` method sends the base64 image as an inline data URL in the message:

```python
messages = [{
    "role": "user",
    "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
    ]
}]
```

---

## Ollama Provider (`ai/ollama.py`)

Targets a locally running Ollama server (no internet connection required).

### Configuration

| Setting | Env var | Default |
|---------|---------|---------|
| Host | `OLLAMA_HOST` | `localhost:11434` |
| Text model | `OLLAMA_TEXT_MODEL` | `qwen2.5:14b` |
| Vision model | `OLLAMA_VISION_MODEL` | `gemma3:12b` |

### HTTP call

```
POST http://{host}/api/chat
Body: {
    "model": "qwen2.5:14b",
    "messages": [...],
    "stream": false,
    "options": {"num_predict": max_tokens}
}
```

Vision messages use the Ollama-native `images` field:
```python
{"role": "user", "content": prompt, "images": [base64_string]}
```

### Health check

```
GET http://{host}/api/tags
```
Returns the list of available models. If the request succeeds and the model is present, health is OK.

---

## Mock Provider (`ai/mock.py`)

Used for local development and CI. Controlled by `MOCK_AI_MODE`:

| Mode | Behavior |
|------|----------|
| `clean` | Returns no issues; all checks pass |
| `issues` | Returns fabricated issues (spelling: "teh→the", homophone: "plain→plane", readability) |
| `error` | Raises `Exception` to test error handling |

Adds a 50–150ms simulated delay via `time.sleep(random.uniform(0.05, 0.15))`.

**`chat_completion` pattern matching:**

| Message contains | Response |
|------------------|----------|
| `explain`, `what`, `how` | Explanation text |
| `modify`, `add`, `change`, `fix`, `create` | Tool block: `update_code` with boilerplate |
| *(anything else)* | Generic "I can help with…" |

---

## Prompt Templates (`ai/prompts.py`)

### `text_analysis_prompt(text, language='English')`

Instructs the model to find spelling, homophone, and grammar errors and return them as a JSON array:

```json
[
  {"type": "spelling", "text": "teh", "suggestion": "the", "context": "…sentence…"},
  {"type": "homophone", "text": "plain", "suggestion": "plane", "context": "…"}
]
```

### `vision_analysis_prompt(context='')`

Instructs the model to analyze a screenshot for:
- Text readability issues
- Layout/alignment problems
- Missing or truncated content
- Contrast issues
- Rendering artifacts

Returns a JSON array:
```json
[
  {"type": "readability", "detail": "text too small in footer", "severity": "medium"}
]
```

### `text_comparison_prompt(baseline, current, language='English')`

Compares two text strings and identifies significant differences:
```json
[
  {"type": "changed", "baseline": "original text", "current": "new text", "significance": "high"}
]
```

Types: `added`, `removed`, `changed`, `reordered`.

### `test_generation_system_prompt(helpers=None)`

System prompt for the builder chat. Describes the NAEP context, available Playwright helpers, and output requirements (valid `.spec.js` with `import {test, expect}` from `@playwright/test`).

---

## AI Analysis Pipeline

Analysis is triggered by `tasks/ai_tasks.py:process_ai_queue()`, a django-q2 periodic task.

```
AIAnalysis(status='pending')
    ↓
process_ai_queue() picks up to 10 records
    ↓
For each: check analysis_type
    ├── has screenshot_path → provider.analyze_screenshot(b64)
    ├── has text → provider.analyze_text(text, language)
    └── nothing → status = 'skipped'
    ↓
Update AIAnalysis:
    status = 'completed' | 'error'
    issues_found = bool
    issues = JSON array
    raw_response = str
    model_used = str
    duration_ms = int
```

Review records (`Review`) are expected to be created separately (e.g., in a post-save signal or by the test executor) when `issues_found=True`.

---

## Chat Manager (`builder/chat_manager.py`)

### `chat(message, conversation_id, current_code, filename)`

Main entry point for the builder API. Returns:

```python
{
    "conversationId": str,
    "response": str,          # assistant text (tools stripped out)
    "codeUpdate": str | None, # new code if update_code tool was called
    "toolsUsed": list[str]    # names of tools invoked
}
```

### Conversation storage

Conversations are stored in the `AIConversation` model (`messages` JSONField). Each turn appends to the array:

```json
[
  {"role": "system", "content": "…system prompt…"},
  {"role": "user", "content": "write a visual regression test"},
  {"role": "assistant", "content": "Here's the test:\n```tool\n{\"tool\":\"update_code\",…}\n```"}
]
```

### System prompt construction (`build_system_prompt`)

1. Load `AISetting(key='system_prompt')` if set; otherwise use the built-in default from `ai/prompts.py`
2. Append descriptions of all **enabled** `AITool` records (name + description + parameters)
3. If `current_code` is non-empty, append it as context: `Current file: {filename}\n\`\`\`js\n{code}\n\`\`\``

### Tool call parsing (`parse_tool_calls`)

Two strategies, tried in order:

**Strategy 1 — fenced block:**
```
```tool
{"tool": "update_code", "args": {"code": "…", "summary": "…"}}
```
```

**Strategy 2 — inline JSON:**
Finds `{"tool": "…", …}` patterns in the response text using balanced-brace extraction.

Returns `(text_without_tool_blocks, [tool_calls])`.

---

## AI Tools

Tools are called by the AI during a chat turn. The `AITool` table controls which tools are enabled at runtime.

| Tool ID | Category | Description |
|---------|----------|-------------|
| `explain_code` | code | Explain what the current script does (AI responds in text; no side effect) |
| `update_code` | code | Return updated JavaScript code; replaces editor content |
| `read_file` | filesystem | Read a file from allowed directories (`src/helpers`, `tests`, `src/config`) |
| `list_helpers` | filesystem | Scan `src/helpers/*.js` and extract exported function signatures |
| `analyze_script` | code | Static analysis — currently reports "syntax check: passed" |
| `search_tests` | filesystem | Full-text search across `.spec.js` files; returns top 5 matches |
| `get_items` | database | Query items table by `assessmentId` or search term; returns up to 50 rows |

### `update_code` args

```json
{
  "code": "// full updated playwright script…",
  "summary": "Added screenshot comparison step"
}
```

When this tool is executed, `codeUpdate` in the response is set and the browser replaces the editor contents.

### `read_file` args

```json
{"path": "src/helpers/navigation.js"}
```

Path must resolve inside one of the safe directories. Returns up to 4,000 characters.

### `get_items` args

```json
{
  "assessmentId": "M4-2024-A",
  "search": "fraction"
}
```

Returns a markdown-formatted list:
```
- #42 | VH123456 | Fraction comparison | visual_regression | tier: core
```

---

## Adding a New Provider

1. Create `ai/my_provider.py`, subclass `BaseProvider`, implement all methods.
2. Register in `ai/provider.py`'s `get_provider()`:
   ```python
   elif provider_name == 'myprovider':
       from ai.my_provider import MyProvider
       _provider_instance = MyProvider(...)
   ```
3. Add env vars to `.env.example` and `docs/10-configuration.md`.
4. Set `AI_PROVIDER=myprovider` in `.env`.
