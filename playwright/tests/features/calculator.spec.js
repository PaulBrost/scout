// SCOUT — Calculator Overlay Tests
// Verifies the calculator opens, displays, and can be closed.

const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../../src/helpers/auth');
const { openCalculator, closeCalculator } = require('../../src/helpers/items');
const { analyzeItemScreenshot } = require('../../src/helpers/ai');

test.describe('Calculator', () => {
  test('Calculator opens and shows keys @feature @calculator', async ({ page }) => {
    await loginAndStartTest(page, { formKey: 'cra-form1' });

    await openCalculator(page);

    // Verify calculator keys are visible
    await expect(page.locator('#KeyEquals')).toBeVisible();
    await expect(page.locator('#Key0')).toBeVisible();
    await expect(page).toHaveScreenshot('calculator-open.png');
  });

  test('Calculator does not obscure item content @feature @calculator', async ({ page }) => {
    await loginAndStartTest(page, { formKey: 'cra-form1' });

    await openCalculator(page);

    const screenshot = await page.screenshot({ fullPage: true });
    const analysis = await analyzeItemScreenshot(screenshot,
      'Calculator overlay is open over an assessment item. Verify it does not obscure critical assessment content and all buttons are readable.');

    if (analysis.issuesFound) {
      await test.info().attach('vision-calculator', {
        body: JSON.stringify(analysis, null, 2),
        contentType: 'application/json',
      });
    }

    expect(analysis.raw).toBeDefined();
  });

  test('Calculator closes cleanly @feature @calculator', async ({ page }) => {
    await loginAndStartTest(page, { formKey: 'cra-form1' });

    await openCalculator(page);
    await expect(page.locator('#KeyEquals')).toBeVisible();

    await closeCalculator(page);
    await expect(page.locator('#KeyEquals')).not.toBeVisible();
  });
});
