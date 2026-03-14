const { test, expect } = require('@playwright/test');
const { login, loginAndStartTest } = require('../src/helpers/auth');
const { clickNext, startTestSession, INTRO_SCREENS } = require('../src/helpers/items');
const { analyzeItemScreenshot } = require('../src/helpers/ai');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

// Captures intro + instructional pages, then iterates items with AI checks
// Note: We avoid loginAndStartTest for this flow so we don't auto-skip intros
// Instead we: login -> startTestSession -> capture intro screens -> proceed to items

test('Intro/Instruction + Item screenshots + AI — Gates Student Experience Form', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();

  // Login and open the selected form without skipping intros
  await login(page, { env: envConfig });
  await startTestSession(page, 'gates-student-experience-form', envConfig);

  // Capture introduction/instructional screens before items
  const introCount = typeof INTRO_SCREENS === 'function' ? INTRO_SCREENS() : 0;
  for (let i = 1; i <= introCount; i++) {
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveScreenshot(`intro-${i}.png`, { fullPage: true });
    await clickNext(page);
  }

  // Now iterate through items
  const TOTAL_ITEMS = 25;
  for (let i = 1; i <= TOTAL_ITEMS; i++) {
    await page.waitForLoadState('networkidle');

    // Capture baseline for each item
    await expect(page).toHaveScreenshot(`item-${i}.png`, { fullPage: true });

    // AI visual inspection for layout issues
    const screenshot = await page.screenshot({ fullPage: true });
    const result = await analyzeItemScreenshot(
      screenshot,
      `Gates Student Experience item ${i}. Check layout integrity, overlapping elements, clipped or truncated text, missing images, misaligned controls, and obvious visual anomalies.`
    );
    if (result && result.issuesFound) {
      console.warn(`Visual issues in item ${i}:`, result.issues);
    }
    await test.info().attach(`ai-vision-item-${i}`, {
      body: JSON.stringify(result, null, 2),
      contentType: 'application/json',
    });

    if (i < TOTAL_ITEMS) await clickNext(page);
  }

  // End-of-assessment confirmation: click OK to complete
  await page.waitForLoadState('networkidle');

  // Accept native dialog if it's a window.alert/confirm
  page.once('dialog', async (dialog) => {
    try { await dialog.accept(); } catch (e) {}
  });

  // Attempt to proceed (some flows require clicking Next one more time to trigger the prompt)
  try {
    await clickNext(page);
  } catch (e) {
    // Ignore if Next isn't available
  }

  // If it's a DOM modal, click an OK/Confirm/Proceed button
  const confirmBtn = page.getByRole('button', { name: /^(ok|confirm|proceed)$/i });
  if (await confirmBtn.count()) {
    await expect(confirmBtn.first()).toBeVisible({ timeout: 5000 });
    await confirmBtn.first().click();
  }

  // Optional: capture final completion screen
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveScreenshot('end-complete.png', { fullPage: true });
});
