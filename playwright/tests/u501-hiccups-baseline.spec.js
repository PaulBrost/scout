const { test, expect } = require('@playwright/test');
const { login } = require('../src/helpers/auth');
const { selectFilters, DEFAULT_FILTERS } = require('../src/helpers/piaac');

// Only run on chrome-desktop project (Chromium — Google Chrome engine)
test.use({
  video: 'off',
  snapshotPathTemplate: '{snapshotDir}/{testFileDir}/{testFileName}-snapshots/{arg}-{projectName}{ext}',
});

function loadEnvConfig() {
  if (process.env.SCOUT_ENV_CONFIG) {
    try { return JSON.parse(process.env.SCOUT_ENV_CONFIG); } catch (e) { /* ignore */ }
  }
  return null;
}

const ITEM_ID = 'U501-Hiccups';

test.describe('PIAAC U501-Hiccups baseline @baseline', () => {
  test.setTimeout(180000);

  test('capture all screens', async ({ page, browserName }, testInfo) => {
    test.skip(testInfo.project.name !== 'chrome-desktop', 'Baseline only on chrome-desktop');

    const envConfig = loadEnvConfig();

    // 1) Login
    await login(page, { env: envConfig });
    await page.waitForLoadState('domcontentloaded');

    // 2) Apply filters
    await selectFilters(page, DEFAULT_FILTERS);
    await page.waitForTimeout(3000);

    // 3) Click item to open popup
    const itemEl = page.locator(`text=${ITEM_ID}`).first();
    await expect(itemEl).toBeVisible({ timeout: 10000 });

    const [itemPage] = await Promise.all([
      page.context().waitForEvent('page'),
      itemEl.click(),
    ]);
    await itemPage.waitForLoadState('networkidle');
    await itemPage.waitForTimeout(2000);

    // 4) Capture Question 1/3 (C501P001 — initial screen)
    await expect(itemPage).toHaveScreenshot('u501-q1-c501p001.png', {
      maxDiffPixelRatio: 0.01, fullPage: true,
    });

    // 5) Navigate through each item button in the top bar
    //    Buttons: C501P001, item1a, C501P002, C501P003
    const itemButtons = ['item1a', 'C501P002', 'C501P003'];
    for (const btnLabel of itemButtons) {
      const btn = itemPage.locator(`input[value="${btnLabel}"], button:has-text("${btnLabel}")`).first();
      if (await btn.count() > 0) {
        await btn.click();
        await itemPage.waitForLoadState('networkidle');
        await itemPage.waitForTimeout(1500);

        const safeName = btnLabel.toLowerCase().replace(/[^a-z0-9]/g, '-');
        await expect(itemPage).toHaveScreenshot(`u501-${safeName}.png`, {
          maxDiffPixelRatio: 0.01, fullPage: true,
        });
      }
    }

    // 6) Go back to first question for help screenshot
    const firstBtn = itemPage.locator('input[value="C501P001"], button:has-text("C501P001")').first();
    if (await firstBtn.count() > 0) {
      await firstBtn.click();
      await itemPage.waitForLoadState('networkidle');
      await itemPage.waitForTimeout(1000);
    }

    // 7) Capture help popup (the ? button in the top-right)
    const helpBtn = itemPage.locator('img[alt*="help" i], img[alt*="Help" i], [title*="help" i], [title*="Help" i], a:has(img[src*="help"]), button:has(img[src*="help"]), img[src*="help"]').first();
    if (await helpBtn.count() > 0) {
      await helpBtn.click();
      await itemPage.waitForTimeout(2000);
      await expect(itemPage).toHaveScreenshot('u501-help.png', {
        maxDiffPixelRatio: 0.01, fullPage: true,
      });

      // Close help — try Escape, close button, or clicking help again
      await itemPage.keyboard.press('Escape');
      await itemPage.waitForTimeout(500);
    }

    // 8) Try forward arrow navigation as alternative to buttons
    //    The right arrow (▶) navigates to next question
    const fwdArrow = itemPage.locator('img[alt*="next" i], img[alt*="forward" i], img[src*="next"], img[src*="forward"], [title*="Next"]').first();
    if (await fwdArrow.count() > 0) {
      // We already captured via buttons above; just verify the arrow works
      await fwdArrow.click();
      await itemPage.waitForLoadState('networkidle');
      await itemPage.waitForTimeout(1000);
      await expect(itemPage).toHaveScreenshot('u501-nav-forward.png', {
        maxDiffPixelRatio: 0.01, fullPage: true,
      });
    }

    await itemPage.close();
  });
});
