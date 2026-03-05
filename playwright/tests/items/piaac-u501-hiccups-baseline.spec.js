// SCOUT — U501-Hiccups Comprehensive Baseline
// Captures ZZZ/eng master baseline: visual screenshots, text content, and DOM structure.
// First run with --update-snapshots to create golden baselines.
// Usage: npx playwright test tests/items/piaac-u501-hiccups-baseline.spec.js --update-snapshots

const { test, expect } = require('@playwright/test');
const { login } = require('../../src/helpers/auth');
const { selectFilters, openItem, extractItemContent, DEFAULT_FILTERS } = require('../../src/helpers/piaac');

function loadEnvConfig() {
  const raw = process.env.SCOUT_ENV_CONFIG;
  if (!raw) throw new Error('SCOUT_ENV_CONFIG env var not set. Run through SCOUT runner or set manually.');
  return JSON.parse(raw);
}

const ITEM_ID = 'U501-Hiccups';

test.describe('U501-Hiccups Baseline — ZZZ/eng', () => {

  test('Visual baseline capture @visual @baseline', async ({ page }) => {
    test.setTimeout(180000); // 3 min

    const envConfig = loadEnvConfig();
    await login(page, { env: envConfig });
    await selectFilters(page, DEFAULT_FILTERS);

    const itemPage = await openItem(page, ITEM_ID);

    try {
      await itemPage.waitForLoadState('networkidle');
      await itemPage.waitForTimeout(2000);

      // Full page baseline
      await expect(itemPage).toHaveScreenshot(
        'u501-hiccups-baseline-full.png',
        { maxDiffPixelRatio: 0.01, fullPage: true }
      );

      // Viewport-only baseline
      await expect(itemPage).toHaveScreenshot(
        'u501-hiccups-baseline-viewport.png',
        { maxDiffPixelRatio: 0.01 }
      );
    } finally {
      await itemPage.close();
    }
  });

  test('Text content baseline @content @baseline', async ({ page }) => {
    test.setTimeout(180000);

    const envConfig = loadEnvConfig();
    await login(page, { env: envConfig });
    await selectFilters(page, DEFAULT_FILTERS);

    const itemPage = await openItem(page, ITEM_ID);

    try {
      await itemPage.waitForLoadState('networkidle');
      await itemPage.waitForTimeout(1000);

      const text = await extractItemContent(itemPage);

      // Attach text as baseline artifact
      await test.info().attach('baseline-text-U501-Hiccups', {
        body: JSON.stringify({ itemId: ITEM_ID, language: 'ZZZ/eng', text: text }, null, 2),
        contentType: 'application/json',
      });

      // Verify text is non-empty and has reasonable length
      expect(text, 'Item text should not be empty').toBeTruthy();
      expect(text.length, 'Item text should have reasonable length (>50 chars)').toBeGreaterThan(50);
    } finally {
      await itemPage.close();
    }
  });

  test('DOM structure baseline @structure @baseline', async ({ page }) => {
    test.setTimeout(180000);

    const envConfig = loadEnvConfig();
    await login(page, { env: envConfig });
    await selectFilters(page, DEFAULT_FILTERS);

    const itemPage = await openItem(page, ITEM_ID);

    try {
      await itemPage.waitForLoadState('networkidle');
      await itemPage.waitForTimeout(1000);

      // Extract a simplified DOM structure tree
      const structure = await extractDomStructure(itemPage);

      // Attach structure as baseline artifact
      await test.info().attach('baseline-structure-U501-Hiccups', {
        body: JSON.stringify({ itemId: ITEM_ID, language: 'ZZZ/eng', structure: structure }, null, 2),
        contentType: 'application/json',
      });

      // Verify structure has content
      expect(structure.length, 'DOM structure should contain elements').toBeGreaterThan(0);
    } finally {
      await itemPage.close();
    }
  });
});

/**
 * Extract a simplified DOM structure from the item page.
 * Captures headings, paragraphs, interactive elements, images, and form fields.
 * Handles content inside iframes.
 */
async function extractDomStructure(itemPage) {
  const extractFromContext = async (locator) => {
    return locator.evaluate(root => {
      const elements = [];
      const selectors = 'h1, h2, h3, h4, h5, h6, p, img, button, input, select, textarea, a, table, ul, ol, label, [role="button"], [role="checkbox"], [role="radio"]';
      root.querySelectorAll(selectors).forEach(el => {
        if (el.offsetParent === null && el.tagName !== 'INPUT') return; // skip hidden
        elements.push({
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute('role') || undefined,
          type: el.getAttribute('type') || undefined,
          text: el.textContent.trim().substring(0, 200) || undefined,
          src: el.tagName === 'IMG' ? (el.getAttribute('src') || '').substring(0, 200) : undefined,
          alt: el.tagName === 'IMG' ? el.getAttribute('alt') : undefined,
          id: el.id || undefined,
          className: el.className ? String(el.className).substring(0, 100) : undefined,
        });
      });
      return elements;
    });
  };

  try {
    const hasIframe = await itemPage.locator('iframe').count();
    if (hasIframe > 0) {
      const frame = itemPage.frameLocator('iframe').first();
      return extractFromContext(frame.locator('body'));
    }
  } catch {
    // fallback to main page
  }

  return extractFromContext(itemPage.locator('body'));
}
