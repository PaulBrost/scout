// SCOUT — PIAAC Visual Baseline Capture
// Captures ZZZ/eng screenshots as the master baseline for PIAAC LITNew items.
// First run with --update-snapshots to create golden baselines.
// Usage: npx playwright test tests/items/piaac-visual-baseline.spec.js --update-snapshots

const { test, expect } = require('@playwright/test');
const { login } = require('../../src/helpers/auth');
const { selectFilters, getItemLinks, openItem, DEFAULT_FILTERS } = require('../../src/helpers/piaac');

function loadEnvConfig() {
  const raw = process.env.SCOUT_ENV_CONFIG;
  if (!raw) throw new Error('SCOUT_ENV_CONFIG env var not set. Run through SCOUT runner or set manually.');
  return JSON.parse(raw);
}

test.describe('PIAAC Visual Baseline — LITNew (ZZZ/eng)', () => {

  test('Capture master baselines for all LITNew items @visual @piaac @baseline', async ({ page }) => {
    test.setTimeout(300000); // 5 min — many items to screenshot

    const envConfig = loadEnvConfig();

    // Login to PIAAC portal
    await login(page, { env: envConfig });

    // Apply ZZZ/eng/LITNew filters
    await selectFilters(page, DEFAULT_FILTERS);

    // Discover all item links
    const items = await getItemLinks(page);
    console.log(`Found ${items.length} PIAAC LITNew items to baseline`);

    expect(items.length, 'Expected at least one item link on the portal page').toBeGreaterThan(0);

    for (const item of items) {
      console.log(`Capturing baseline: ${item.itemId}`);

      // Open item in popup window
      const itemPage = await openItem(page, item.itemId);

      try {
        // Wait for content to stabilize
        await itemPage.waitForLoadState('networkidle');
        await itemPage.waitForTimeout(1000);

        // Capture baseline screenshot
        await expect(itemPage).toHaveScreenshot(
          `piaac-baseline-${item.itemId}.png`,
          { maxDiffPixelRatio: 0.01, fullPage: true }
        );
      } finally {
        await itemPage.close();
      }
    }

    console.log(`Baseline capture complete: ${items.length} items`);
  });
});
