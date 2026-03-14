const { test } = require('@playwright/test');
const { login } = require('../src/helpers/auth');
const { selectFilters, openItem, navigateItemScreens } = require('../src/helpers/piaac');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

// Baseline screenshots for PIAAC item U503-Banking in ROU/ron
// Captures a full-page screenshot of every in-item screen, including any intro/instruction screens.
test('Baseline screenshots — U503-Banking (ROU ron)', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();

  // Login to PIAAC Translations Portal
  await login(page, { env: envConfig });

  // Apply filters to locate the item in the portal
  await selectFilters(page, { version: 'FT New', country: 'ROU', language: 'ron', domain: 'LITNew' });

  // Open the specified item directly by itemId
  const itemId = 'U503-Banking';
  const itemPage = await openItem(page, itemId);

  // Walk through all screens of the item and capture full-page screenshots of each
  await navigateItemScreens(itemPage, envConfig, async (pg, idx) => {
    await pg.screenshot({ path: `test-results/${itemId}-screen-${idx}.png`, fullPage: true });
  });

  await itemPage.close();
});
