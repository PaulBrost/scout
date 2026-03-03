// SCOUT — AI Content Validation Tests
// Extracts text from items and runs AI analysis for spelling, grammar, homophones.
// AI results are advisory — flagged for human review, never auto-fail.

const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../../src/helpers/auth');
const { clickNext, extractItemText } = require('../../src/helpers/items');
const { analyzeItemText, analyzeItemScreenshot } = require('../../src/helpers/ai');

const TOTAL_ITEMS = 20;

test.describe('Content Validation — Text Analysis', () => {
  test('All CRA Form 1 items text quality @smoke @content', async ({ page }) => {
    test.setTimeout(300000); // 5 min — 20 items × AI calls
    await loginAndStartTest(page, { formKey: 'cra-form1' });

    for (let itemNum = 1; itemNum <= TOTAL_ITEMS; itemNum++) {
      const text = await extractItemText(page);

      if (text && text.trim().length >= 10) {
        const result = await analyzeItemText(text, 'English');

        if (result.issuesFound) {
          console.warn(`SCOUT AI flagged issues in Item ${itemNum}:`, JSON.stringify(result.issues));
          await test.info().attach(`ai-text-item-${itemNum}`, {
            body: JSON.stringify(result, null, 2),
            contentType: 'application/json',
          });
        }

        expect(result.raw).toBeDefined();
      }

      if (itemNum < TOTAL_ITEMS) {
        await clickNext(page);
      }
    }
  });
});

test.describe('Content Validation — Vision Analysis', () => {
  test('First 5 items screenshot readability @smoke @vision', async ({ page }) => {
    await loginAndStartTest(page, { formKey: 'cra-form1' });

    for (let itemNum = 1; itemNum <= 5; itemNum++) {
      const screenshot = await page.screenshot({ fullPage: true });
      const result = await analyzeItemScreenshot(screenshot,
        'Assessment item in default theme. Check text readability, layout integrity, and visual anomalies.');

      if (result.issuesFound) {
        console.warn(`SCOUT vision issues in Item ${itemNum}:`, JSON.stringify(result.issues));
        await test.info().attach(`ai-vision-item-${itemNum}`, {
          body: JSON.stringify(result, null, 2),
          contentType: 'application/json',
        });
      }

      expect(result.raw).toBeDefined();

      if (itemNum < 5) {
        await clickNext(page);
      }
    }
  });
});
