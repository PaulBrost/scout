const { test, expect } = require('@playwright/test');
const { login } = require('../src/helpers/auth');
const { selectFilters, getItemLinks, openItem } = require('../src/helpers/piaac');
const { clickNext, forceClickNext } = require('../src/helpers/items');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

// Logs in, opens U511-AppComparison in the PIAAC portal, and captures a full-page screenshot of every screen.
test('U511-AppComparison — capture all screens', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  const ITEM_ID = 'U511-AppComparison';

  // Login to the portal
  await login(page, { env: envConfig });

  // Apply standard filters and wait for item links to populate
  await selectFilters(page, { version: 'FT New', country: 'ZZZ', language: 'eng', domain: 'LITNew' });
  const items = await getItemLinks(page);
  const target = items.find(i => i.itemId === ITEM_ID);
  if (!target) throw new Error(`Target item ${ITEM_ID} not found with current filters.`);

  // Open the item in a popup window
  const itemPage = await openItem(page, target.itemId);
  try {
    let screenIndex = 1;
    while (true) {
      await itemPage.waitForLoadState('networkidle');
      await expect(itemPage).toHaveScreenshot(`${ITEM_ID}-screen-${screenIndex}.png`, { fullPage: true });

      const advanced = await tryAdvance(itemPage);
      if (!advanced) break;
      screenIndex += 1;
    }
  } finally {
    await itemPage.close();
  }
});

// Attempts to navigate to the next screen; returns true if navigation occurred, false otherwise.
async function tryAdvance(page) {
  try {
    await clickNext(page);
    return true;
  } catch (e1) {
    try {
      await forceClickNext(page);
      return true;
    } catch (e2) {
      return false;
    }
  }
}
