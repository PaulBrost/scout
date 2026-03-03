// SCOUT — PIAAC Item Interaction Test: U593 Birthday Party
// Logs into the PIAAC translations portal, navigates to item U593-BirthdayParty,
// clicks option em#U593P002_opt2, and verifies it highlights.
//
// Portal navigation uses dropdown_config from the environment record.
// Selectors here are best-guess for the PIAAC translations portal and may
// need adjustment after a first run.

const { test, expect } = require('@playwright/test');
const { login } = require('../../src/helpers/auth');

/**
 * Load environment config from SCOUT_ENV_CONFIG env var (set by executor/runner.py).
 */
function loadEnvConfig() {
  const raw = process.env.SCOUT_ENV_CONFIG;
  if (!raw) throw new Error('SCOUT_ENV_CONFIG env var not set. Run this script through the SCOUT runner or set it manually.');
  return JSON.parse(raw);
}

test.describe('PIAAC U593 — Birthday Party Interaction', () => {

  test('Click option 2 and verify highlight', async ({ page }) => {
    test.setTimeout(120000); // 2 min — portal navigation can be slow

    const envConfig = loadEnvConfig();
    const dropdown = envConfig.launcher_config?.dropdown_config || {};

    // --- 1. Login ---
    await login(page, { env: envConfig });

    // --- 2. Navigate the PIAAC translations portal ---
    // The portal has dropdown filters for domain, country, version, language.
    // Fill them using values from the environment's launcher_config.dropdown_config.

    if (dropdown.domain) {
      await page.waitForSelector('select#domain, select[name="domain"]', { timeout: 15000 });
      await page.selectOption('select#domain, select[name="domain"]', { label: dropdown.domain });
      await page.waitForTimeout(1000); // allow dependent dropdowns to refresh
    }

    if (dropdown.country) {
      await page.selectOption('select#country, select[name="country"]', { label: dropdown.country });
      await page.waitForTimeout(1000);
    }

    if (dropdown.version) {
      await page.selectOption('select#version, select[name="version"]', { label: dropdown.version });
      await page.waitForTimeout(1000);
    }

    if (dropdown.language) {
      await page.selectOption('select#language, select[name="language"]', { label: dropdown.language });
      await page.waitForTimeout(1000);
    }

    // --- 3. Locate and open item U593-BirthdayParty ---
    // Try clicking a link/row containing the item identifier.
    // The portal may show items in a table or list. Try multiple strategies.
    const itemLink = page.locator('a:has-text("U593"), a:has-text("BirthdayParty"), tr:has-text("U593") a').first();
    await itemLink.waitFor({ state: 'visible', timeout: 15000 });
    await itemLink.click();
    await page.waitForLoadState('domcontentloaded');

    // Wait for the item content to render (may be in an iframe)
    // Check for iframe first, fall back to direct DOM
    const iframe = page.frameLocator('iframe').first();
    let itemFrame;
    try {
      await page.waitForSelector('iframe', { timeout: 5000 });
      itemFrame = iframe;
    } catch {
      // No iframe — item renders directly on the page
      itemFrame = page;
    }

    // --- 4. Click em#U593P002_opt2 ---
    const option = itemFrame.locator('em#U593P002_opt2');
    await option.waitFor({ state: 'visible', timeout: 15000 });
    await option.click();

    // --- 5. Assert: element gains a highlight indicator ---
    // PIAAC items typically mark selected options via CSS class, background-color,
    // or aria-selected. Check for common patterns.
    await page.waitForTimeout(500); // allow UI to update

    const isHighlighted = await itemFrame.locator('em#U593P002_opt2').evaluate((el) => {
      const classes = el.className || '';
      const parentClasses = el.parentElement?.className || '';
      const style = window.getComputedStyle(el);
      const bgColor = style.backgroundColor;
      const ariaSelected = el.getAttribute('aria-selected') || el.parentElement?.getAttribute('aria-selected');

      // Check multiple highlight indicators
      const hasActiveClass = /selected|active|highlight|chosen/i.test(classes + ' ' + parentClasses);
      const hasBackground = bgColor && bgColor !== 'rgba(0, 0, 0, 0)' && bgColor !== 'transparent';
      const hasAriaSelected = ariaSelected === 'true';

      return hasActiveClass || hasBackground || hasAriaSelected;
    });

    expect(isHighlighted, 'Option em#U593P002_opt2 should be highlighted after click').toBeTruthy();
  });
});
