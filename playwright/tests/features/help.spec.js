// SCOUT — Help Panel Tests
// Verifies the help button opens and closes the help panel correctly.

const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../../src/helpers/auth');
const { openHelp, closeHelp } = require('../../src/helpers/items');

test.describe('Help Panel', () => {
  test('Help panel opens and displays content @feature @help', async ({ page }) => {
    await loginAndStartTest(page, { formKey: 'cra-form1' });

    const help = await openHelp(page);
    await expect(help).toBeVisible();
    await expect(page).toHaveScreenshot('help-panel-open.png');
  });

  test('Help panel closes cleanly @feature @help', async ({ page }) => {
    await loginAndStartTest(page, { formKey: 'cra-form1' });

    await openHelp(page);
    await expect(page.locator('#theHelpContent')).toBeVisible();

    await closeHelp(page);
    // Help content should be hidden after closing
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot('help-panel-closed.png');
  });
});
