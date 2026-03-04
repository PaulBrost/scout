// SCOUT — PIAAC Item Interaction Test: U593 Birthday Party
// Logs into the PIAAC translations portal, populates the filter dropdowns
// (Version=FT New, Country=ROU, Language=ron, Domain=LITNew), then clicks
// U593-BirthdayParty to launch the item.
//
// Portal selectors: #VerSelect, #CountrySelect, #LangSelect, #DomainSelect
// Each dropdown triggers a cascade — the next dropdown's options load after
// the previous one changes, so we wait for options before selecting.

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

/**
 * Wait until a <select> has more than one option (i.e. its dependent data loaded).
 */
async function waitForSelectOptions(page, selector, timeout = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const count = await page.locator(selector + ' option').count();
    if (count > 1) return count;
    await page.waitForTimeout(500);
  }
  return 0;
}

test.describe('PIAAC U593 — Birthday Party Interaction', () => {

  test('Navigate filters and launch U593-BirthdayParty', async ({ page }) => {
    test.setTimeout(120000); // 2 min — portal navigation can be slow

    const envConfig = loadEnvConfig();

    // --- 1. Login ---
    await login(page, { env: envConfig });

    // --- 2. Populate translation portal filters ---
    // Order matters: Version → Country → Language → Domain (cascading)

    // Version = "FT New"
    await page.waitForSelector('#VerSelect', { timeout: 15000 });
    await page.selectOption('#VerSelect', { label: 'FT New' });
    await page.locator('#VerSelect').dispatchEvent('change');
    await page.waitForTimeout(2000);

    // Country = "ROU"
    await waitForSelectOptions(page, '#CountrySelect');
    await page.selectOption('#CountrySelect', 'ROU');
    await page.locator('#CountrySelect').dispatchEvent('change');
    await page.waitForTimeout(2000);

    // Language = "ron"
    await waitForSelectOptions(page, '#LangSelect');
    await page.selectOption('#LangSelect', 'ron');
    await page.locator('#LangSelect').dispatchEvent('change');
    await page.waitForTimeout(2000);

    // Domain = "LITNew"
    await waitForSelectOptions(page, '#DomainSelect');
    try {
      await page.selectOption('#DomainSelect', 'LITNew');
    } catch {
      await page.selectOption('#DomainSelect', { label: 'LITNew' });
    }
    await page.locator('#DomainSelect').dispatchEvent('change');
    await page.waitForTimeout(2000);

    // --- 3. Click U593-BirthdayParty to launch the item ---
    const itemLink = page.locator('a:has-text("U593-BirthdayParty"), a:has-text("U593"), td:has-text("BirthdayParty") a').first();
    await itemLink.waitFor({ state: 'visible', timeout: 15000 });
    await itemLink.click();
    await page.waitForLoadState('domcontentloaded');

    // Wait for the item content to render (may be in an iframe)
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
    await page.waitForTimeout(500);

    const isHighlighted = await itemFrame.locator('em#U593P002_opt2').evaluate((el) => {
      const classes = el.className || '';
      const parentClasses = el.parentElement?.className || '';
      const style = window.getComputedStyle(el);
      const bgColor = style.backgroundColor;
      const ariaSelected = el.getAttribute('aria-selected') || el.parentElement?.getAttribute('aria-selected');

      const hasActiveClass = /selected|active|highlight|chosen/i.test(classes + ' ' + parentClasses);
      const hasBackground = bgColor && bgColor !== 'rgba(0, 0, 0, 0)' && bgColor !== 'transparent';
      const hasAriaSelected = ariaSelected === 'true';

      return hasActiveClass || hasBackground || hasAriaSelected;
    });

    expect(isHighlighted, 'Option em#U593P002_opt2 should be highlighted after click').toBeTruthy();
  });
});
