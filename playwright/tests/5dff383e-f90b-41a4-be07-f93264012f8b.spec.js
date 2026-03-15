const { test } = require('@playwright/test');
const { loginAndStartTest } = require('../src/helpers/auth');
const { navigateAllScreens } = require('../src/helpers/items');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('Baseline screenshots — CRA Form 3 — Odd Var / Even Base', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  // skipIntro: false to capture intro/tutorial screens as part of the baseline
  await loginAndStartTest(page, { formKey: 'cra-form3', env: envConfig, skipIntro: false });

  await navigateAllScreens(page, envConfig, async (pg, idx) => {
    await pg.screenshot({ path: `test-results/screen-${idx}.png`, fullPage: true });
  });
});
