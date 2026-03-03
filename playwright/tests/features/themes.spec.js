// SCOUT — Theme Tests (CSS-injected)
// The CRA assessment does not have a native theme switcher.
// These tests inject CSS to simulate light/dark/high-contrast modes
// and verify items remain readable under each.

const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../../src/helpers/auth');
const { analyzeItemScreenshot } = require('../../src/helpers/ai');

const themes = {
  light: '', // default, no changes
  dark: `
    body { background: #1a1a2e !important; color: #e0e0e0 !important; }
    #item { background: #1a1a2e !important; color: #e0e0e0 !important; }
    .fixed1280 { background: #16213e !important; }
  `,
  'high-contrast': `
    body { background: #000 !important; color: #ff0 !important; }
    #item { background: #000 !important; color: #ff0 !important; }
    .fixed1280 { background: #000 !important; }
    button { background: #333 !important; color: #ff0 !important; border: 2px solid #ff0 !important; }
  `,
};

test.describe('Theme Simulation', () => {
  for (const [theme, css] of Object.entries(themes)) {
    test(`Item 1 in ${theme} mode @feature @theme`, async ({ page }) => {
      await loginAndStartTest(page, { formKey: 'cra-form1' });

      if (css) {
        await page.addStyleTag({ content: css });
        await page.waitForTimeout(300);
      }

      await expect(page).toHaveScreenshot(`cra-item1-theme-${theme}.png`, {
        maxDiffPixelRatio: 0.02,
      });

      // AI vision: check readability in this theme
      const screenshot = await page.screenshot({ fullPage: true });
      const analysis = await analyzeItemScreenshot(screenshot,
        `Assessment item in ${theme} theme. Verify text readability and sufficient contrast.`);

      if (analysis.issuesFound) {
        await test.info().attach(`vision-${theme}`, {
          body: JSON.stringify(analysis, null, 2),
          contentType: 'application/json',
        });
      }
    });
  }
});
