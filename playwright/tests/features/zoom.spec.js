// SCOUT — Zoom Level Tests
// Verifies items render correctly at different zoom levels.
// Note: This assessment has no native zoom control; we use CSS zoom.

const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../../src/helpers/auth');
const { setZoom } = require('../../src/helpers/items');
const { analyzeItemScreenshot } = require('../../src/helpers/ai');

const zoomLevels = [50, 100, 150, 200];

test.describe('Zoom Levels', () => {
  for (const zoom of zoomLevels) {
    test(`Item 1 at ${zoom}% zoom @feature @zoom`, async ({ page }) => {
      await loginAndStartTest(page, { formKey: 'cra-form1' });
      await setZoom(page, zoom);

      await expect(page).toHaveScreenshot(`cra-item1-zoom-${zoom}.png`, {
        maxDiffPixelRatio: 0.02,
      });

      // AI vision for extreme zoom levels
      if (zoom === 50 || zoom === 200) {
        const screenshot = await page.screenshot({ fullPage: true });
        const analysis = await analyzeItemScreenshot(screenshot,
          `Assessment item at ${zoom}% zoom. Check for truncation, overflow, and readability.`);

        if (analysis.issuesFound) {
          await test.info().attach(`vision-zoom-${zoom}`, {
            body: JSON.stringify(analysis, null, 2),
            contentType: 'application/json',
          });
        }
      }
    });
  }
});
