# NAEP Gates (Student Experience)

A Gates Foundation assessment form running on the same NAEP CRA platform. Uses the same c3.NET infrastructure, login flow, and helpers as CRA.

## Connection

Same as [NAEP CRA](./naep-cra.md) — shares the same environment and login credentials. The Gates form is selected via the launcher dropdown.

## Assessment Forms

| Form Key | Name | Items | Form Value |
|---|---|---|---|
| `gates-student-experience-form` | Gates Student Experience Form 1 | 25 | `tests/Gates_form1.xml\|Pure/prefs/NAEP_Gates_2025.xml` |

## Differences from CRA

- **Item count**: 25 items (vs 20 for CRA forms)
- **Content**: Student experience survey questions rather than math assessment
- **Intro screens**: Same 5-screen intro flow as CRA

## Screen Flow

Same as CRA — see [NAEP CRA Screen Flow](./naep-cra.md#screen-flow). The only difference is the assessment content and item count.

## Helpers Used

Same helpers as CRA. Example test:

```javascript
const { test } = require('@playwright/test');
const { loginAndStartTest } = require('../src/helpers/auth');
const { navigateAllScreens } = require('../src/helpers/items');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('Gates Baseline Screenshots', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await loginAndStartTest(page, {
    formKey: 'gates-student-experience-form',
    env: envConfig,
    skipIntro: false
  });

  await navigateAllScreens(page, envConfig, async (pg, idx) => {
    await pg.screenshot({ path: `test-results/screen-${idx}.png`, fullPage: true });
  });
});
```

## Recommended `launcher_config`

Uses the same environment config as CRA. No separate environment is needed — the Gates form is just another entry in the `#TheTest` dropdown.
