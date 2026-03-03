# AI Test Builder

The Builder (`/builder/`) is a browser-based IDE that lets users write, edit, and save Playwright test scripts with help from an AI assistant. It consists of a split-panel layout: chat on the left, code editor on the right.

---

## URL and Query Parameters

```
GET /builder/
GET /builder/?file=items/vh123456.spec.js
GET /builder/?assessment=M4-2024-A
GET /builder/?file=items/vh123456.spec.js&assessment=M4-2024-A
```

| Parameter | Description |
|-----------|-------------|
| `file` | Relative path to a `.spec.js` file (relative to `PLAYWRIGHT_TESTS_DIR`). Loads file content into the editor and fetches metadata + run history. |
| `assessment` | Assessment ID. If set, pre-loads context (assessment name, subject, grade) as an info banner at the top of the chat panel. Also used as default when associating a newly saved script. |
| `type` | Test type hint (e.g., `visual_regression`). Passed to the AI as context. |
| `baseline` | Baseline version string. Passed to the AI as context. |

---

## Interface Layout

```
┌──────────────────────────┬─────────────────────────────────────┐
│       AI Chat            │        Code Editor                   │
│                          │                                       │
│  [context banner]        │  filename.spec.js ● unsaved          │
│                          │  [Check] [Copy] [Save]               │
│  ┌────────────────────┐  │                                       │
│  │  chat messages     │  │  // dark-background textarea         │
│  │                    │  │  // monospace, no syntax highlight   │
│  │  assistant         │  │                                       │
│  │  user              │  │                                       │
│  │                    │  │                                       │
│  └────────────────────┘  │                                       │
│                          │  [dry-run result bar]                 │
│  [textarea]  [Send]      ├─────────────────────────────────────┤
│  [status line]           │  Script Details & Run History (▼)   │
└──────────────────────────┘  [metadata form + run history table] │
                           └─────────────────────────────────────┘
```

---

## Chat Panel

### Sending a message

- Type in the `<textarea>` and click Send, or press **Ctrl+Enter** / **Cmd+Enter**
- The message is appended to the chat history display
- A `POST /builder/api/chat/` request is fired

### API request body

```json
{
  "message": "Write a visual regression test for item VH123456",
  "conversationId": "uuid-or-null",
  "currentCode": "// existing script contents…",
  "filename": "vh123456.spec.js"
}
```

### API response

```json
{
  "conversationId": "uuid",
  "response": "Here's the test I've written for you…",
  "codeUpdate": "import { test, expect } from '@playwright/test';\n…",
  "toolsUsed": ["update_code"]
}
```

- `response` is appended to the chat as an assistant bubble
- If `codeUpdate` is set, the code editor contents are replaced and the "unsaved" indicator appears
- `toolsUsed` is shown in the status line

### Clearing the conversation

The refresh button in the chat header sets `conversationId = null` and clears the message history. The next message starts a new `AIConversation` record in the DB.

---

## Code Editor

The editor is a plain `<textarea>` styled with a dark (`#1e1e1e`) background and monospace font. There is no syntax highlighting. This keeps the template simple while remaining fully functional for writing and editing JavaScript.

### Dirty state

Any edit to the textarea sets `isDirty = true` and shows an "● unsaved" indicator. A `beforeunload` handler warns the user if they try to navigate away with unsaved changes.

### Check (Syntax Dry Run)

Clicking **Check** calls `POST /test-cases/api/dry-run/` with the current editor contents. The server writes the code to a temp file and runs `node --check`. The result appears in the bar below the editor:

- ✓ green: "Syntax valid — no errors found"
- ✗ red: Node.js error output (first 500 chars)

### Save

Clicking **Save** calls `POST /test-cases/api/save/`. If a `file` was loaded from a URL param, it saves back to the same path. Otherwise, it auto-generates a filename: `generated/generated-{timestamp}.spec.js`.

On success:
- `isDirty = false`, "unsaved" indicator hidden
- `currentFilePath` updated to the saved path
- Status line shows "Saved to generated/generated-1234567890.spec.js"

### Copy

Copies the full editor contents to the clipboard via `navigator.clipboard.writeText()`.

---

## Script Metadata Accordion

Shown only when a `?file=` param was provided (i.e., an existing script is loaded). Collapsed by default.

### Fields

| Field | Description |
|-------|-------------|
| Item ID | Dropdown from all items in DB; associates the script with a NAEP item |
| Assessment | Dropdown from all assessments |
| Category | Select: `visual_regression`, `content_validation`, `feature_functional`, `workflow`, `scoring_validation` |
| Description | Free text |

Clicking **Save Metadata** calls `POST /test-cases/api/associate/` to upsert the `TestScript` row.

### Run History table

Displays the last 50 executions of this script, pulled from `TestRunScript`. Shows status badge, suite name (or trigger type if ad-hoc), duration, and completion time.

---

## Chat Manager (`builder/chat_manager.py`)

The `chat()` function is the backend for the `api_chat` view. See [docs/05-ai-integration.md](05-ai-integration.md) for the full tool list and system prompt construction.

Key behaviors:
- Conversations are persistent (stored in `AIConversation.messages` JSONField)
- Max turns enforced by `AISetting(key='max_conversation_turns')` (default 50); older messages trimmed from the middle preserving the system prompt and recent exchanges
- Tool calls extracted from response text; `update_code` tool result becomes `codeUpdate` in the response

---

## Saving vs Registering

There are two separate actions:

| Action | Endpoint | What happens |
|--------|----------|-------------|
| **Save** (builder) | `POST /builder/api/save/` | Writes file to `generated/` subdirectory; registers path in `test_scripts` |
| **Save** (test cases) | `POST /test-cases/api/save/` | Writes to a specified path; registers or updates `test_scripts` row |
| **Associate** | `POST /test-cases/api/associate/` | Updates metadata (item, category, description) without writing the file |

After saving, the script appears in the Test Cases list (`/test-cases/`) with `source: registered`.

---

## Workflow Example

1. Navigate to `/assessments/M4-2024-A/` → click "AI Builder"
2. Builder opens at `/builder/?assessment=M4-2024-A`; assessment context banner appears
3. Type: *"Write a visual regression test for item VH123456. The item is a drag-and-drop math problem."*
4. AI responds with explanation and fires `update_code` tool → editor fills with Playwright script
5. Click **Check** → "Syntax valid"
6. Open the metadata accordion → select item "VH123456", category "visual_regression"
7. Click **Save Metadata** → associates the script
8. Click **Save** → writes `generated/generated-1234567890.spec.js`
9. Navigate to `/test-cases/` → script appears with "registered" badge and the associated item
10. Navigate to `/suites/new/` → script appears in the script picker; add it to a suite and run

---

## Limitations

- **No syntax highlighting** — the editor is a plain `<textarea>`; consider adding CodeMirror or Monaco in a future iteration
- **Single active conversation** — the chat panel only tracks one `conversationId` per page load; opening a new tab starts a fresh conversation
- **No real-time collaboration** — each browser session is independent
- **Playwright execution not triggered from builder** — to run a saved script, create or edit a suite and trigger a run from `/suites/`
