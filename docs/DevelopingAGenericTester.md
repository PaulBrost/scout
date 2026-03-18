# Developing SCOUT as a Generic Web Testing Platform

## Current State Assessment

SCOUT was built to test NAEP and PIAAC assessment environments, but its architecture separates concerns well enough that generalizing it is realistic without a rewrite.

### What's Already Generic

The core platform — roughly 80% of the codebase — has no dependency on assessments or items:

- **Test execution** (`executor/runner.py`) just runs `npx playwright test <script>` with environment variables. It doesn't know what an assessment is.
- **AI analysis pipeline** (`tasks/post_execution.py`) uses `LEFT JOIN` to items — fully optional. Baseline comparison now triggers based on whether a script has stored baselines, not its type.
- **Data models** (`core/models.py`) — TestScript has nullable FKs to Assessment and Item. Scripts work fine without them.
- **Builder** (`builder/chat_manager.py`) — the chat loop, tool system, and code generation framework are generic. Only the system prompt content and reference scripts are NAEP-specific.
- **Everything else** — runs, suites, reviews, environments, users, admin config, script types — all generic.

### What's NAEP/PIAAC-Specific

Only two layers are tightly coupled to the current use case:

**1. Playwright helper modules** (`playwright/src/helpers/`)

| Module | Specificity | Purpose |
|--------|------------|---------|
| `auth.js` | Semi-generic | Login + session management. Has NAEP form-selection logic (`#TheTest` selector) baked in alongside generic auth. |
| `items.js` | NAEP-specific | Hardcoded CRA selectors (`#nextButton`, `#backButton`, `#item`), form keys, intro screen logic. |
| `piaac.js` | PIAAC-specific | Portal selectors (`#VerSelect`, `#CountrySelect`), popup-based item navigation. |
| `ai.js` | Generic | AI text/screenshot analysis — calls SCOUT's API, no assessment assumptions. |
| `qc.js` | Semi-generic | Interaction detection (dropdowns, text areas, drag-and-drop) is generic; the QC rules themselves are assessment-flavored. |
| `testdata.js` | Generic | Loads test data from DB-linked datasets via `SCOUT_TEST_DATA` env var. |

**2. AI builder context** (`builder/chat_manager.py`)

- System prompt says "PIAAC and NAEP assessment platforms"
- Reference scripts (7 complete examples) all demonstrate NAEP/PIAAC patterns
- Code conventions section references NAEP-specific helpers and patterns
- `list_helpers` tool scans a single global helpers directory

---

## Plan: Environment-Scoped Helper Libraries

### Concept

Introduce **Helper Libraries** — named, reusable collections of Playwright helper files that can be assigned to environments. Each library provides the helpers, reference scripts, and code conventions that the AI builder needs to generate correct tests for that target application.

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Environment │────>│ Helper Library   │────>│ Helper Files    │
│ "NAEP Prod" │     │ "NAEP/CRA"       │     │ auth.js         │
│             │     │                  │     │ items.js        │
│             │     │ reference scripts│     │ ai.js           │
│             │     │ code conventions │     │ qc.js           │
└─────────────┘     └──────────────────┘     └─────────────────┘

┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Environment │────>│ Helper Library   │────>│ Helper Files    │
│ "Banking QA"│     │ "Generic Web"    │     │ auth.js         │
│             │     │                  │     │ navigation.js   │
│             │     │ reference scripts│     │ ai.js           │
│             │     │ code conventions │     │ forms.js        │
└─────────────┘     └──────────────────┘     └─────────────────┘
```

### Data Model

New table: `helper_libraries`

```sql
CREATE TABLE helper_libraries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,          -- "NAEP/CRA", "PIAAC", "Generic Web"
    description TEXT,                   -- shown in admin UI
    directory TEXT NOT NULL UNIQUE,     -- relative path: "naep", "piaac", "generic"
    reference_scripts TEXT,             -- markdown with complete example scripts
    code_conventions TEXT,              -- markdown with import patterns, conventions
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

New column on `environments`:

```sql
ALTER TABLE environments ADD COLUMN helper_library_id UUID REFERENCES helper_libraries(id);
```

### File Structure

Move from a single flat helpers directory to library-scoped directories:

```
playwright/
├── src/
│   ├── helpers/
│   │   ├── _shared/              # Helpers available to ALL libraries
│   │   │   ├── ai.js             # AI analysis (generic)
│   │   │   └── testdata.js       # Test data loading (generic)
│   │   │
│   │   ├── naep/                 # NAEP/CRA library
│   │   │   ├── auth.js           # Login + form selection
│   │   │   ├── items.js          # Screen navigation, selectors
│   │   │   └── qc.js             # QC interaction checks
│   │   │
│   │   ├── piaac/                # PIAAC library
│   │   │   ├── auth.js           # Portal login
│   │   │   ├── portal.js         # Filter selection, item links
│   │   │   └── items.js          # Popup navigation, iframe content
│   │   │
│   │   └── generic/              # Generic web testing library
│   │       ├── auth.js           # Configurable login (form-based, SSO, etc.)
│   │       ├── navigation.js     # Page navigation, menu traversal
│   │       └── forms.js          # Form filling, validation checking
│   │
│   └── reporters/
└── tests/                        # Generated test scripts (unchanged)
```

### How Imports Work

Tests currently use `require('../../src/helpers/auth')`. With libraries, a NAEP test would use:

```javascript
const { loginAndStartTest } = require('../../src/helpers/naep/auth');
const { analyzeItemText } = require('../../src/helpers/_shared/ai');
```

The AI builder generates the correct import paths because it knows which library the environment uses.

### Builder Integration

#### 1. `list_helpers` becomes library-aware

When a script is tied to an environment, `list_helpers` scans that environment's library directory plus `_shared/`:

```python
def list_helpers(environment_id):
    library_dir = get_library_dir(environment_id)  # e.g., "naep"
    scan_dirs = [
        project_root / 'src' / 'helpers' / '_shared',
        project_root / 'src' / 'helpers' / library_dir,
    ]
    # ... scan and return helpers from both directories
```

#### 2. System prompt becomes dynamic

Instead of hardcoding NAEP reference scripts, `build_system_prompt()` loads them from the helper library record:

```python
def build_system_prompt(environment_id=None):
    prompt = get_default_system_prompt()  # Generic intro (remove NAEP references)

    if environment_id:
        library = get_library_for_environment(environment_id)
        if library:
            prompt += f"\n## Reference Scripts\n{library.reference_scripts}\n"
            prompt += f"\n## Code Conventions\n{library.code_conventions}\n"
            prompt += f"\n## Import Paths\n"
            prompt += f"- Shared helpers: require('../../src/helpers/_shared/<module>')\n"
            prompt += f"- Library helpers: require('../../src/helpers/{library.directory}/<module>')\n"
    else:
        prompt += "\n## Note\nNo environment selected. Ask the user which environment this test targets.\n"

    return prompt
```

#### 3. `get_test_template` tool becomes library-aware

The builder already has a `get_test_template` tool. It would check the environment's library for relevant templates instead of returning hardcoded NAEP boilerplate.

### Runner Integration

The runner doesn't need significant changes. It already passes environment config as `SCOUT_ENV_CONFIG`. The only addition: pass the library directory name so helpers can self-configure if needed:

```python
env_vars['SCOUT_HELPER_LIBRARY'] = library.directory  # e.g., "naep"
```

### Admin UI

Add a "Helper Libraries" section under Admin (or within General Settings):

- **List view**: Shows all libraries with name, description, number of helper files, number of environments using it
- **Edit view**: Name, description, directory path (read-only after creation), reference scripts (markdown editor), code conventions (markdown editor)
- **Helper file browser**: Read-only view of the JS files in the library's directory with their exported functions
- **Environment assignment**: On the environment edit page, add a "Helper Library" dropdown

### Migration Path

This can be rolled out incrementally:

**Phase 1: Restructure files, no DB changes**
- Create the `_shared/`, `naep/`, and `piaac/` directories
- Move `ai.js` and `testdata.js` to `_shared/`
- Move NAEP helpers to `naep/`, PIAAC helpers to `piaac/`
- Keep copies in the old location for backward compatibility with existing test scripts
- Update `list_helpers` to scan library directories

**Phase 2: Add the data model**
- Create `helper_libraries` table
- Add `helper_library_id` to environments
- Seed the three initial libraries (NAEP, PIAAC, Generic)
- Build admin UI for managing libraries

**Phase 3: Dynamic builder context**
- Refactor `build_system_prompt()` to load reference scripts from the library record
- Refactor `get_test_template` to be library-aware
- Remove hardcoded NAEP content from `chat_manager.py`
- Update the default system prompt to be platform-agnostic

**Phase 4: Generic Web library**
- Build a `generic/` helper set with configurable auth, navigation, and form helpers
- Write reference scripts showing common patterns (login flow, CRUD operations, form validation, report generation)
- This becomes the default library for new environments

---

## What a "Generic Web" Helper Library Looks Like

### `generic/auth.js`

Configurable login that reads strategy from `SCOUT_ENV_CONFIG`:

```javascript
async function login(page, envConfig) {
    const { base_url, auth_type, credentials } = envConfig;
    await page.goto(base_url);

    if (auth_type === 'form') {
        // Configurable selectors from launcher_config
        const selectors = envConfig.launcher_config?.login || {};
        await page.fill(selectors.username || '#username', credentials.username);
        await page.fill(selectors.password || '#password', credentials.password);
        await page.click(selectors.submit || 'button[type="submit"]');
    } else if (auth_type === 'basic') {
        // HTTP basic auth via context
        await page.context().setHTTPCredentials(credentials);
        await page.goto(base_url);
    }
    // ... other auth types
}
```

### `generic/navigation.js`

```javascript
async function navigateToPage(page, path) { /* ... */ }
async function clickMenuItem(page, menuText) { /* ... */ }
async function waitForPageLoad(page) { /* ... */ }
async function getPageTitle(page) { /* ... */ }
async function screenshotFullPage(page, name) { /* ... */ }
```

### `generic/forms.js`

```javascript
async function fillForm(page, fieldValues) { /* ... */ }
async function submitForm(page, submitSelector) { /* ... */ }
async function getValidationErrors(page) { /* ... */ }
async function selectDropdownOption(page, selector, value) { /* ... */ }
```

### Example Reference Script: "Login and Screenshot All Pages"

```javascript
const { test, expect } = require('@playwright/test');
const { login } = require('../../src/helpers/generic/auth');
const { navigateToPage, screenshotFullPage } = require('../../src/helpers/generic/navigation');

const envConfig = JSON.parse(process.env.SCOUT_ENV_CONFIG || '{}');

test('capture screenshots of all main pages', async ({ page }) => {
    await login(page, envConfig);

    const pages = ['/dashboard', '/users', '/reports', '/settings'];
    for (const path of pages) {
        await navigateToPage(page, path);
        await screenshotFullPage(page, `page-${path.replace(/\//g, '-')}`);
    }
});
```

---

## What Stays Assessment-Specific

Even with full generalization, the Assessment and Item models remain useful for environments that have that structure. They become an **optional organizational layer**:

- Environments that test assessments keep using Assessment → Item hierarchy
- Environments that test a banking app just don't create any assessments/items
- The UI already handles this gracefully — assessment/item columns show "—" when null
- The sidebar "Assessments" and "Items" nav links could be conditionally shown based on whether the environment has any

No need to remove or rename the models. They serve their purpose for the original use case and stay out of the way for others.
