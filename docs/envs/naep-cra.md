# NAEP CRA (Cognitive Research Assessment)

The primary assessment environment. Runs on ETS's c3.NET platform and hosts multiple CRA math forms plus supporting assessments.

## Connection

| Setting | Value |
|---|---|
| Base URL | `http://rt.ets.org/c3.NET/naep_review.aspx` |
| Auth Type | `password_only` |
| Default Password | `c3c4` (configurable via `ASSESSMENT_PASSWORD`) |
| Password Selector | `#_ctl0_Body_PasswordText` |
| Submit Selector | `#_ctl0_Body_SubmitButton` |

## Launcher Configuration

| Setting | Value |
|---|---|
| Form/Test Selector | `#TheTest` |
| Submit Selector | `input[type="submit"]` |
| Intro Screens | `5` |

After login, the launcher page shows a `#TheTest` dropdown with all available test forms. Selecting a form and clicking submit loads the assessment.

## Assessment Forms

| Form Key | Name | Subject | Grade | Items | Form Value |
|---|---|---|---|---|---|
| `cra-form1` | CRA Form 1 — All Base | Math | 8 | 20 | `tests/craFY25_form1_AllBase.xml\|Pure/prefs/NAEP_CRA_Sept2024.xml` |
| `cra-form2` | CRA Form 2 — All Variant | Math | 8 | 20 | `tests/craFY25_form2_AllVar.xml\|Pure/prefs/NAEP_CRA_Sept2024.xml` |
| `cra-form3` | CRA Form 3 — Odd Var / Even Base | Math | 8 | 20 | `tests/craFY25_form3_OddVarEvenBase.xml\|Pure/prefs/NAEP_CRA_Sept2024.xml` |
| `cra-form4` | CRA Form 4 — Odd Base / Even Var | Math | 8 | 20 | `tests/craFY25_form4_OddBaseEvenVar.xml\|Pure/prefs/NAEP_CRA_Sept2024.xml` |
| `math-fluency` | Math Fluency | Math | 4 & 8 | — | `tests/mathFluency.xml\|Pure/prefs/NAEP_MF_2022.xml` |
| `naep-id-4th` | NAEP ID — 4th Grade | General | 4 | — | `tests/naepID_4thGrade.xml\|Pure/prefs/NAEP_ID_2022.xml` |
| `naep-id-8th` | NAEP ID — 8th Grade | General | 8 | — | `tests/naepID_8thGrade.xml\|Pure/prefs/NAEP_ID_2022.xml` |

Form keys map to the `TEST_FORMS` constant in `playwright/src/helpers/items.js` and to assessment `form_value` fields in the database.

## Screen Flow

```
Login page
  → Launcher (form dropdown + submit)
    → Intro screens (5 by default)
      - Welcome/instructions
      - Audio check (Next disabled until audio plays)
      - Video tutorial (Next disabled until video ends)
      - Practice items / tutorials
    → Assessment items (20 per CRA form)
      - Each item has a #nextButton to advance
      - Some items require an answer before Next is enabled
      - Last item triggers a "You cannot return" confirmation dialog
    → Completion screen
      - May have an OK/Done button to dismiss
```

## DOM Structure

| Element | Selector | Purpose |
|---|---|---|
| Item content area | `#item` | Main content container, visible on all screens including intros |
| Next button | `#nextButton` | Advances to next screen. May have `disabledButton` CSS class |
| Back button | `#backButton` | Returns to previous screen |
| Calculator | `#CalculatorBlueGreenIcon` | Toggles calculator overlay |
| Help panel | `#helpButton` / `#theHelpContent` | Opens/closes help |
| Scratchwork | `#scratchworkButton` | Opens drawing tool |

The Next button uses two mechanisms to indicate disabled state:
- HTML `disabled` attribute
- CSS class `disabledButton` (removed and replaced with `enabledButton` to enable)

## Helpers Used

- **`loginAndStartTest(page, { formKey, env, skipIntro })`** — Full setup: login, select form, optionally skip intros
- **`clickNext(page)`** — Normal navigation (waits for enabled button)
- **`forceClickNext(page)`** — Force-enables disabled Next (for intro screens)
- **`navigateAllScreens(page, envConfig, onScreen)`** — Walk all screens including intros and end
- **`answerAndAdvance(page)`** — Provides dummy answer when "must answer" dialog fires

## Baseline Test Pattern

```javascript
const { test } = require('@playwright/test');
const { loginAndStartTest } = require('../src/helpers/auth');
const { navigateAllScreens } = require('../src/helpers/items');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('Baseline screenshots', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  // skipIntro: false captures intro/tutorial screens
  await loginAndStartTest(page, { formKey: 'cra-form1', env: envConfig, skipIntro: false });

  await navigateAllScreens(page, envConfig, async (pg, idx) => {
    await pg.screenshot({ path: `test-results/screen-${idx}.png`, fullPage: true });
  });
});
```

## Non-Baseline Test Pattern (Items Only)

```javascript
await loginAndStartTest(page, { formKey: 'cra-form1', env: envConfig });
// skipIntro defaults to true — starts on item 1

const TOTAL_ITEMS = 20;
for (let i = 1; i <= TOTAL_ITEMS; i++) {
  await page.waitForLoadState('networkidle');
  // ... do work on each item ...
  if (i < TOTAL_ITEMS) await clickNext(page);
}
```

## Recommended `launcher_config`

```json
{
  "launcher_selector": "#TheTest",
  "submit_selector": "input[type=\"submit\"]",
  "intro_screens": 5,
  "end_indicator": "",
  "done_button": "",
  "video_progress_selector": "video",
  "max_screens": 100
}
```

Set `end_indicator` and `done_button` to match your environment's completion screen. For example, if the end screen shows "You have completed this test" with an OK button:

```json
{
  "end_indicator": "text=You have completed",
  "done_button": "button:has-text('OK')"
}
```

## Known Behaviors

- **Audio check screens**: Next is disabled until audio finishes. `forceClickNext()` bypasses this.
- **Video screens**: Next is disabled until video ends. `skipVideoIfPresent()` seeks to the end, then `forceClickNext()` enables Next.
- **"Must answer" dialogs**: Some items show a native `alert()` requiring an answer. Helpers auto-detect these and provide dummy answers.
- **End-of-assessment dialog**: Clicking Next on the last item shows a confirmation dialog ("You cannot return after this"). `forceClickNext()` accepts this automatically.
- **Timeout**: Multi-item tests must call `test.setTimeout(300000)` (5 min) because the default 120s is not enough.
