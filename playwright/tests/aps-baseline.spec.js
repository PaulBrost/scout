const { test, expect } = require('@playwright/test');
const { login } = require('../src/helpers/auth');
const { selectFilters, getItemLinks, openItem, DEFAULT_FILTERS } = require('../src/helpers/piaac');
const { clickNext, isNextEnabled } = require('../src/helpers/items');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test.describe('APS Baseline', () => {
  test('Log in, open each item, and capture all screens', async ({ page }) => {
    test.setTimeout(300000);

    const envConfig = loadEnvConfig();

    // Login to the PIAAC Translations Portal
    await login(page, { env: envConfig });

    // Apply default filters (adjust via helpers if environment requires)
    await selectFilters(page, DEFAULT_FILTERS);

    // Discover all item links after filtering
    const items = await getItemLinks(page);
    expect(items.length, 'Expected at least one item link on the portal page').toBeGreaterThan(0);

    for (const item of items) {
      const itemPage = await openItem(page, item.itemId);
      let screenIndex = 1;

      try {
        while (true) {
          await itemPage.waitForLoadState('networkidle');
          await itemPage.waitForTimeout(500);

          const name = `${item.itemId}-screen-${String(screenIndex).padStart(2, '0')}.png`;
          await expect(itemPage).toHaveScreenshot(name, { fullPage: true, maxDiffPixelRatio: 0.01 });

          const canGoNext = await isNextEnabled(itemPage);
          if (!canGoNext) break;

          await clickNext(itemPage);
          screenIndex += 1;
        }
      } finally {
        await itemPage.close();
      }
    }
  });
});
