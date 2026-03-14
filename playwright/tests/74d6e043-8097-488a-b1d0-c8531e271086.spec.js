const { test } = require('@playwright/test');
const { loginAndStartTest } = require('../src/helpers/auth');
const { navigateAllScreens } = require('../src/helpers/items');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('Gates Screenshots — Student Experience Form', async ({ page }) => {
  test.setTimeout(600000); // 10 min — generous for full navigation
  const envConfig = loadEnvConfig();

  console.log('[SCOUT] Starting Gates baseline — logging in and selecting form...');
  // skipIntro: false to capture intro/tutorial screens as part of the baseline
  await loginAndStartTest(page, { formKey: 'gates-student-experience-form', env: envConfig, skipIntro: false });
  console.log('[SCOUT] Login complete, beginning screen navigation...');

  const totalScreens = await navigateAllScreens(page, envConfig, async (pg, idx) => {
    console.log(`[SCOUT] Capturing screen ${idx}...`);
    await pg.screenshot({ path: `test-results/screen-${idx}.png`, fullPage: true });
  });

  console.log(`[SCOUT] Done — captured ${totalScreens} screens.`);
});
