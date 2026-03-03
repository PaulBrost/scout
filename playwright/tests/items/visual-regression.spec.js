// SCOUT — Visual Regression Tests
// Captures screenshots and compares against baselines for CRA Form 1 items.

const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../../src/helpers/auth');
const { clickNext, extractItemText } = require('../../src/helpers/items');

// CRA Form 1 has 20 math items (screens 6-25 after intro)
const TOTAL_ITEMS = 20;

test.describe('Visual Regression — CRA Form 1', () => {
  test('All items visual baseline capture @smoke @visual', async ({ page }) => {
    await loginAndStartTest(page, { formKey: 'cra-form1' });

    for (let itemNum = 1; itemNum <= TOTAL_ITEMS; itemNum++) {
      // Wait for item content to be fully loaded and stable
      await page.waitForSelector('#item', { state: 'visible' });
      await page.waitForLoadState('networkidle');

      const text = await extractItemText(page);
      console.log(`Item ${itemNum}: ${text.substring(0, 80)}...`);

      await expect(page).toHaveScreenshot(`cra-form1-item-${String(itemNum).padStart(2, '0')}.png`, {
        maxDiffPixelRatio: 0.01,
        fullPage: true,
      });

      if (itemNum < TOTAL_ITEMS) {
        await clickNext(page);
        // Brief pause to let item transition complete
        await page.waitForTimeout(500);
      }
    }
  });
});
