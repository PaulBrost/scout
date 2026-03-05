// SCOUT — PIAAC AI Content Validation
// Runs AI text and vision analysis on PIAAC LITNew items.
// Results are advisory only — flagged for human review, never auto-fail.

const { test, expect } = require('@playwright/test');
const { login } = require('../../src/helpers/auth');
const { selectFilters, getItemLinks, openItem, extractItemContent, DEFAULT_FILTERS } = require('../../src/helpers/piaac');
const { analyzeItemText, analyzeItemScreenshot } = require('../../src/helpers/ai');

function loadEnvConfig() {
  const raw = process.env.SCOUT_ENV_CONFIG;
  if (!raw) throw new Error('SCOUT_ENV_CONFIG env var not set. Run through SCOUT runner or set manually.');
  return JSON.parse(raw);
}

test.describe('PIAAC Content Validation — Text Analysis', () => {

  test('All LITNew items text quality @content @piaac @ai', async ({ page }) => {
    test.setTimeout(600000); // 10 min

    const envConfig = loadEnvConfig();
    await login(page, { env: envConfig });
    await selectFilters(page, DEFAULT_FILTERS);

    const items = await getItemLinks(page);
    console.log(`Found ${items.length} items for text analysis`);
    expect(items.length).toBeGreaterThan(0);

    for (const item of items) {
      console.log(`Text analysis: ${item.itemId}`);
      const itemPage = await openItem(page, item.itemId);

      try {
        await itemPage.waitForLoadState('networkidle');
        const text = await extractItemContent(itemPage);

        if (text && text.trim().length >= 10) {
          const result = await analyzeItemText(text, 'English');

          if (result.issuesFound) {
            console.warn(`AI flagged issues in ${item.itemId}:`, JSON.stringify(result.issues));
            await test.info().attach(`ai-text-${item.itemId}`, {
              body: JSON.stringify(result, null, 2),
              contentType: 'application/json',
            });
          }

          expect(result.raw).toBeDefined();
        } else {
          console.log(`Skipping ${item.itemId} — insufficient text content`);
        }
      } finally {
        await itemPage.close();
      }
    }
  });
});

test.describe('PIAAC Content Validation — Vision Analysis', () => {

  test('All LITNew items visual quality @vision @piaac @ai', async ({ page }) => {
    test.setTimeout(600000); // 10 min

    const envConfig = loadEnvConfig();
    await login(page, { env: envConfig });
    await selectFilters(page, DEFAULT_FILTERS);

    const items = await getItemLinks(page);
    console.log(`Found ${items.length} items for vision analysis`);
    expect(items.length).toBeGreaterThan(0);

    for (const item of items) {
      console.log(`Vision analysis: ${item.itemId}`);
      const itemPage = await openItem(page, item.itemId);

      try {
        await itemPage.waitForLoadState('networkidle');
        await itemPage.waitForTimeout(1000);

        const screenshot = await itemPage.screenshot({ fullPage: true });
        const result = await analyzeItemScreenshot(screenshot,
          `PIAAC LITNew item ${item.itemId}. Check text readability, layout integrity, and visual anomalies.`
        );

        if (result.issuesFound) {
          console.warn(`Vision issues in ${item.itemId}:`, JSON.stringify(result.issues));
          await test.info().attach(`ai-vision-${item.itemId}`, {
            body: JSON.stringify(result, null, 2),
            contentType: 'application/json',
          });
        }

        expect(result.raw).toBeDefined();
      } finally {
        await itemPage.close();
      }
    }
  });
});
