# Automated QC Checks — `src/helpers/qc.js`

SCOUT automates common QC checklist steps using the `qc.js` helper module. Tests detect interaction types at runtime by inspecting the DOM, then run the appropriate checks on each screen. Failures are captured with a screenshot and the test continues — no single check failure blocks the entire run.

## Supported Interaction Types

| Type | Detection Selectors | Formal Checklist |
|---|---|---|
| Radio buttons | `input[type="radio"]`, `[role="radio"]` | — |
| Checkboxes | `input[type="checkbox"]`, `[role="checkbox"]` | — |
| Text inputs | `input[type="text"]`, `input[type="number"]` (not readonly/hidden) | — |
| Extended text (textarea) | `textarea` | ExtendedText QC-1, QC-3 |
| Extended text (contenteditable) | `[contenteditable="true"]` | ExtendedText QC-1, QC-3 |
| Dropdowns | `select` (excludes `#TheTest` form selector) | InlineChoice QC-1, QC-2 |
| Click-to-select (NAEP custom) | `.answerChoice`, `.mcChoice`, `[role="option"]`, etc. | — |
| Matching / drag-and-drop | `[draggable="true"]`, `.source-tray .source` + drop targets | Matching QC-1, QC-5 |

Detection searches the full page, not just `#item`, because NAEP assessments may render form elements outside the item content container.

## What Each Check Does

### Radio Buttons
- Clicks each radio option sequentially
- Verifies the clicked option becomes selected (`checked` attribute or `selected`/`checked` CSS class)
- Verifies mutual exclusivity — all other options are deselected

### Checkboxes
- Clicks each checkbox to check it, verifies it becomes checked
- Clicks again to uncheck it, verifies it becomes unchecked

### Text Inputs
- Skips invisible inputs (NAEP may have hidden inputs in the DOM)
- Uses click + keyboard typing (not Playwright's `fill()`, which hangs on some NAEP custom inputs)
- Enters a test value and verifies it appears
- Clears the field and verifies it's empty

### Extended Text (Textarea / Contenteditable)
- Enters multi-line text and verifies content
- Clears the field
- For contenteditable: uses keyboard shortcuts (Ctrl+A, Backspace) since `fill()` doesn't work

### Dropdowns
- Selects each option (up to 6) and verifies the selected value changes
- Resets to the first option after testing
- Excludes `#TheTest` (the NAEP form-selection dropdown)

### Click-to-Select (NAEP Custom)
- Clicks each answer choice element
- Verifies selection state via CSS class (`selected`, `active`, `checked`) or ARIA attribute (`aria-selected`, `aria-checked`)
- Only runs when no native radio/checkbox elements are present (to avoid double-counting)

### Matching / Drag-and-Drop
- Attempts drag-and-drop from first source to first target
- Falls back to click-click if drag fails
- Verifies the source text appears in the target
- Clicks Clear Answer if available

## Failure Handling

Each check type is wrapped in a `safeCheck()` function that:

1. Applies a **10-second timeout** — prevents hanging on unresponsive elements
2. On failure: captures a **full-page screenshot** to `test-results/qc-fail-screen{N}-{type}.png`
3. Logs the failure: `[FAIL] text-input: Element not interactable — screenshot: test-results/qc-fail-screen5-text-input.png`
4. **Continues** to the next check — the test never aborts on a single failure

After all checks on a screen, `clearAnswer()` is called to reset the assessment state for clean navigation.

## Checklist Coverage vs Formal QC Documents

The automated checks cover the **mechanically verifiable** steps from the formal checklists. Steps that require human judgment (TTS, scratchwork, theming, visual inspection) are not automated.

| Formal Checklist | Automated Steps | Manual-Only Steps |
|---|---|---|
| ExtendedText | QC-1 (text entry), QC-3 (edit/clear) | QC-2 (max char dialog), QC-4/5 (retention across nav), QC-6 (copy/paste restrictions) |
| InlineChoice | QC-1 (select options), QC-2 (clear) | QC-3/4 (retention across nav), QC-5 (TTS reads options) |
| Matching | QC-1 (move source to target), QC-5 (clear) | QC-2/3 (move between targets), QC-4 (single/reuse), QC-6/7 (retention), QC-8 (min selection), QC-9-12 (scratchwork, TTS, highlighter, theming) |

Radio buttons, checkboxes, text inputs, and click-to-select elements do not have formal checklist documents yet. The automated checks cover basic functionality verification for these types.

## Usage in Test Scripts

### Standard pattern (recommended)

Use `navigateAllScreens` with `runQcChecks` for full-assessment QC:

```javascript
const { test } = require('@playwright/test');
const { loginAndStartTest } = require('../src/helpers/auth');
const { navigateAllScreens } = require('../src/helpers/items');
const { runQcChecks } = require('../src/helpers/qc');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('QC Checklist — Assessment Name', async ({ page }) => {
  test.setTimeout(600000);
  const envConfig = loadEnvConfig();
  await loginAndStartTest(page, { formKey: 'cra-form1', env: envConfig });

  await navigateAllScreens(page, envConfig, async (pg, idx) => {
    console.log(`[SCOUT] QC checking screen ${idx}...`);
    await runQcChecks(pg, idx);
  });
});
```

### Using the AI Test Builder

The prompt **"Generate a QC checklist test"** produces this pattern automatically via the `qc_checklist` template. The AI does not need to generate detection or check logic — it's all in the helper.

### Individual check functions

For tests targeting a specific interaction type:

```javascript
const { qcRadioButtons, qcDropdowns, detectTypes } = require('../src/helpers/qc');

// Run only radio and dropdown checks
const types = await detectTypes(page);
const log = (msg) => console.log(msg);
if (types.radio > 0) await qcRadioButtons(page, log);
if (types.dropdown > 0) await qcDropdowns(page, log);
```

Available functions: `qcRadioButtons`, `qcCheckboxes`, `qcTextInputs`, `qcExtendedText`, `qcDropdowns`, `qcClickToSelect`, `qcMatching`.

All accept `(page, log)` where `log` is a function like `(msg) => console.log(msg)`.

### Return value from `runQcChecks`

```javascript
{
  types: { radio: 5, checkbox: 0, textInput: 1, ... },
  checksRun: 2,
  failures: [
    { checkName: 'text-input', error: 'timed out after 10000ms', screenshot: 'test-results/qc-fail-screen1-text-input.png' }
  ],
  known: true  // whether any known interaction type was detected
}
```

## Log Output

Example live log during a QC run:

```
[SCOUT] QC checking screen 6...
[QC 6] Detected: 4 radio
[QC 6]   Radio buttons: 4 options
[QC 6]   [PASS] All 4 radio options selectable, mutual exclusivity OK
[QC 6] Completed 1 check(s), all passed
[SCOUT] QC checking screen 7...
[QC 7] Detected: 1 textarea
[QC 7]   Extended text: 1 textarea, 0 contenteditable
[QC 7]   [PASS] Extended text entry and clear verified
[QC 7] Completed 1 check(s), all passed
[SCOUT] QC checking screen 8...
[QC 8] Detected: none detected
[QC 8] No automatable interaction type detected — manual QC recommended
```

Screens with no detected interaction types (e.g., instruction screens, images, video) are logged as needing manual QC and skipped.
