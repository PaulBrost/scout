# Playwright Helpers Reference

All helpers live in `playwright/src/helpers/`. They are used by test scripts and by the AI test builder to generate tests.

## auth.js — Login & Session Management

Handles authentication against assessment environments. Supports multiple auth types and reusable sessions.

### `login(page, options?)`

Logs in to the assessment application.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `page` | Page | — | Playwright page |
| `options.password` | string | — | Override password |
| `options.env` | object | — | Environment config from DB |

- Resolves credentials from `options.env` (DB config) first, falls back to `.env` values
- Detects whether already on a login page; skips login if already authenticated
- Auth types: `password_only`, `username_password`, `none`

### `loginAndStartTest(page, options?)`

Complete setup: login, select form, skip intros, land on item 1.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `options.formKey` | string | `'cra-form1'` | Assessment form key (maps to `TEST_FORMS` or DB `form_value`) |
| `options.skipIntro` | boolean | `true` | Whether to skip intro/tutorial screens |
| `options.env` | object | — | Environment config (auto-loads from `SCOUT_ENV_CONFIG` if not provided) |

- Tries loading saved session first (avoids re-login)
- Calls `startTestSession()` → `skipIntroScreens()` (if `skipIntro` is true)
- For baselines, pass `skipIntro: false` to capture intro screens

### `saveSession(page)` / `loadSession(page)`

Saves/loads browser cookies to `playwright/auth/session.json`. Sessions expire after 4 hours.

---

## items.js — NAEP/CRA Assessment Navigation

Functions for navigating NAEP/CRA assessments. Handles the c3.NET platform's form launcher, intro screens, and item navigation.

### Constants

```javascript
TEST_FORMS = {
  'cra-form1':  'tests/craFY25_form1_AllBase.xml|...',
  'cra-form2':  'tests/craFY25_form2_AllVar.xml|...',
  'cra-form3':  'tests/craFY25_form3_OddVarEvenBase.xml|...',
  'cra-form4':  'tests/craFY25_form4_OddBaseEvenVar.xml|...',
  'math-fluency': 'tests/mathFluency.xml|...',
  'naep-id-4th':  'tests/naepID_4thGrade.xml|...',
  'naep-id-8th':  'tests/naepID_8thGrade.xml|...',
  'gates-student-experience-form': 'tests/Gates_form1.xml|...',
}

INTRO_SCREENS = 5  // Default intro screen count
```

### `startTestSession(page, formKey?, envConfig?)`

Selects a form from the launcher dropdown and submits it.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `formKey` | string | `'cra-form1'` | Key from `TEST_FORMS` or assessment ID |
| `envConfig` | object | `null` | Environment config for custom selectors |

- Looks up form value in `TEST_FORMS` first, then `envConfig.form_value`
- Uses `envConfig.launcher_config.launcher_selector` and `.submit_selector` if provided
- Waits for `#item` to be visible (assessment loaded)

### `skipIntroScreens(page, count?, envConfig?)`

Force-clicks through intro/tutorial screens.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `count` | number | `5` | Number of screens to skip |
| `envConfig` | object | `null` | Reads `launcher_config.intro_screens` if set |

### `forceClickNext(page)`

Clicks the Next button, force-enabling it if disabled. Used for screens where Next is gated (audio check, video, tutorials).

- Waits for `#nextButton` to be attached (not necessarily visible)
- Removes `disabledButton` class, sets `disabled = false`
- Handles "must answer" `alert()` dialogs automatically
- Calls `answerAndAdvance()` if a validation dialog fires

### `clickNext(page)`

Clicks the Next button only when it's already enabled. Safer than `forceClickNext()`.

- Waits for `#nextButton` to be visible
- Handles "must answer" dialogs

### `clickBack(page)`

Clicks `#backButton`.

### `answerAndAdvance(page)`

Provides a dummy answer when a "must answer" dialog fires. Tries these input types in order:

1. Radio buttons (`input[type="radio"]`)
2. NAEP custom answer elements (`.answerChoice`, `.responseOption`, `[role="radio"]`, etc.)
3. Checkboxes
4. Select dropdowns
5. Text inputs
6. Any clickable element inside `#item`

After answering, retries clicking Next.

### `navigateToItem(page, itemNumber)`

Navigates to a specific 1-indexed item from the start. Skips intros, then advances to the target.

### `extractItemText(page)`

Returns all visible text from the `#item` content area.

### `isNextEnabled(page)` / `isBackEnabled(page)`

Returns `boolean` — whether the button is currently clickable (not disabled, no `disabledButton` class).

### `navigateAllScreens(page, envConfig, onScreen)`

Walks through ALL screens of an assessment — intro screens, items, and end screen. Designed for baseline tests that need to capture everything.

| Parameter | Type | Description |
|---|---|---|
| `page` | Page | Playwright page |
| `envConfig` | object | Environment config (reads `launcher_config` for end detection) |
| `onScreen` | function | `async (page, screenIndex) => {}` — called on each screen |

**Returns**: Total number of screens visited.

**Environment config used** (from `envConfig.launcher_config`):

| Key | Purpose | Example |
|---|---|---|
| `end_indicator` | CSS/text selector visible on the final screen | `text=You have completed` |
| `done_button` | Button to click on end screen | `button:has-text('OK')` |
| `video_progress_selector` | Video element or progress bar to seek | `video` |
| `max_screens` | Safety limit | `100` |

**Behavior**:
1. Waits for `networkidle` on each screen
2. Calls `skipVideoIfPresent()` to handle video screens
3. Calls `onScreen(page, idx)` callback
4. Checks for `end_indicator` — breaks if found
5. Force-clicks Next to advance
6. Stops if Next button is missing or can't be clicked

### `skipVideoIfPresent(page, launcherConfig?)`

Detects and skips video on the current screen.

| Parameter | Type | Description |
|---|---|---|
| `launcherConfig` | object | May contain `video_progress_selector` |

- If `video_progress_selector` is configured, tries that first
- Falls back to: `video` (HTML5), `.video-progress`, `[class*="progress-bar"]`
- For `<video>` elements: seeks to `duration - 0.5s` via JavaScript
- For progress bars: clicks at 95% width position
- Returns `true` if a video was skipped

### Feature Helpers

| Function | Description |
|---|---|
| `setZoom(page, percent)` | Sets CSS zoom (50, 100, 150, 200) |
| `openCalculator(page)` | Opens calculator via `#CalculatorBlueGreenIcon` |
| `closeCalculator(page)` | Closes calculator |
| `openHelp(page)` | Opens help panel via `#helpButton` |
| `closeHelp(page)` | Closes help panel |
| `openScratchwork(page)` | Opens scratchwork drawing tool |

---

## piaac.js — PIAAC Portal Navigation

Functions for the PIAAC Translation Quality Assurance portal. Handles cascading dropdown filters and item popup windows.

### Constants

```javascript
SELECTORS = {
  version: '#VerSelect',
  country: '#CountrySelect',
  language: '#LangSelect',
  domain: '#DomainSelect',
  cluster: '#ClusterSelect',
}

DEFAULT_FILTERS = { version: 'FT New', country: 'ZZZ', language: 'eng', domain: 'LITNew' }
```

### `selectFilters(page, filters?)`

Applies cascading dropdown filters. Order: Version → Country → Language → Domain. Each selection triggers a `change` event and waits for the next dropdown to populate.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `filters.version` | string | `'FT New'` | Version to select |
| `filters.country` | string | `'ZZZ'` | Country code |
| `filters.language` | string | `'eng'` | Language code |
| `filters.domain` | string | `'LITNew'` | Domain |

### `getItemLinks(page, timeout?)`

Waits for item links to appear after filter selection (polls up to 15s). Returns an array of:

```javascript
[{ itemId: 'U504-Crayons', linkText: '...', href: '...', dataPath: '...' }]
```

Looks for `li[data-unit]` first, falls back to text matching for `U###` patterns.

### `openItem(portalPage, itemId)`

Clicks an item link and returns the popup Page. Tries selectors in order: `li[data-unit="..."]` → `a:has-text("...")` → `text="..."`.

### `extractItemContent(itemPage)`

Extracts all text from an item page. Handles content inside iframes.

### `getItemSelectors(envConfig)`

Reads button selectors from `envConfig.launcher_config.item_selectors`. Returns:

```javascript
{ next, finish, close, continue_btn, content_frame }
```

### `navigateItemScreens(itemPage, envConfig, onScreen)`

Walks through all screens of a single PIAAC item.

| Parameter | Type | Description |
|---|---|---|
| `itemPage` | Page | The item popup page |
| `envConfig` | object | Environment config (reads `item_selectors`) |
| `onScreen` | function | `async (page, screenIndex) => {}` — called on each screen |

**Returns**: Total number of screens visited.

**Behavior**:
1. Resolves content target (page or iframe via `content_frame`)
2. Calls `onScreen` on each screen
3. Tries clicking `next` button to advance
4. If next isn't available, checks `finish` / `continue_btn` buttons (end of item)
5. Captures one final screen after clicking finish/continue, then breaks

### `waitForSelectOptions(page, selector, timeout?)`

Utility: waits until a `<select>` has more than one option. Used between cascading filter selections.

---

## ai.js — AI Analysis Helpers

Wraps the AI provider for use in Playwright tests. Gracefully degrades when AI is unavailable.

### `analyzeItemText(text, language?)`

Analyzes item text for spelling, grammar, and homophone issues.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `text` | string | — | Extracted item text |
| `language` | string | `'English'` | `'English'` or `'Spanish'` |

Returns:
```javascript
{ issues: [...], issuesFound: boolean, raw: string, model: string, durationMs: number }
```

Skips analysis if AI is disabled or text is less than 10 characters.

### `analyzeItemScreenshot(screenshotBuffer, context?)`

Analyzes a screenshot for visual quality issues.

| Parameter | Type | Description |
|---|---|---|
| `screenshotBuffer` | Buffer | PNG screenshot buffer from `page.screenshot()` |
| `context` | string | Description for AI (e.g., `"Dark theme at 150% zoom"`) |

Returns same structure as `analyzeItemText`.

### `compareItemText(baselineText, currentText, language?)`

Compares text between baseline and current versions of an item.

Returns:
```javascript
{ differences: [...], hasDifferences: boolean, raw: string, model: string, durationMs: number }
```

---

## Environment Config Passing

Helpers receive environment configuration through two mechanisms:

1. **Explicit parameter**: `login(page, { env: envConfig })` — passed directly in test code
2. **Environment variable**: `process.env.SCOUT_ENV_CONFIG` — JSON string set by the SCOUT executor

The `loginAndStartTest()` function auto-loads from `SCOUT_ENV_CONFIG` if no explicit env is provided. In test code, the standard pattern is:

```javascript
function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}
```

The executor populates `SCOUT_ENV_CONFIG` with the full environment record from the database, including `base_url`, `credentials`, `launcher_config`, and `form_value`.
