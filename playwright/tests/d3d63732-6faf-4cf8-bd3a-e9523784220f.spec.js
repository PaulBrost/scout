const { test, expect } = require('@playwright/test');
const { login } = require('../src/helpers/auth');
const { selectFilters, getItemLinks, openItem, navigateItemScreens } = require('../src/helpers/piaac');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

// Logs in, navigates to the U504-Crayons item (eng/ZZZ), and captures full-page screenshots for every screen
// using soft screenshot assertions so Playwright stores baselines and the test continues on mismatches.
test('U504-Crayons eng-ZZZ Baseline — capture screenshots for all screens', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();

  // Login to the PIAAC Translations Portal
  await login(page, { env: envConfig });

  // Apply filters for the target item
  await selectFilters(page, { version: 'FT New', country: 'ZZZ', language: 'eng', domain: 'LITNew' });

  // Verify items are available and confirm the target item exists
  const items = await getItemLinks(page);
  expect(items.length).toBeGreaterThan(0);
  const targetId = 'U504-Crayons';
  const match = items.find(i => i.itemId === targetId);
  if (!match) {
    throw new Error(`Item not found after filtering: ${targetId}`);
  }

  // Open the target item in a popup and capture screenshots across all in-item screens
  const itemPage = await openItem(page, targetId);
  await navigateItemScreens(itemPage, envConfig, async (pg, idx) => {
    await pg.waitForLoadState('networkidle');
    await expect.soft(pg).toHaveScreenshot(`${targetId}-screen-${idx}.png`, { fullPage: true });
  });

  await itemPage.close();
});
