const { test } = require('@playwright/test');
const { loginAndStartTest } = require('../src/helpers/auth');
const { navigateAllScreens } = require('../src/helpers/items');
const { runQcChecks } = require('../src/helpers/qc');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

// QC Checklist — auto-detect interaction type per screen and run appropriate checks
// Platform: NAEP/CRA, Assessment: CRA Form 3 — Odd Var / Even Base
test('QC Checklist — CRA Form 3 — Odd Var / Even Base', async ({ page }) => {
  // Extend timeout for full-form traversal and QC checks
  test.setTimeout(600000);
  const envConfig = loadEnvConfig();

  // Login and start the assessment session
  await loginAndStartTest(page, { formKey: 'cra-form3', env: envConfig });

  console.log('[SCOUT] Starting QC checklist — navigating all screens...');
  await navigateAllScreens(page, envConfig, async (pg, idx) => {
    console.log(`[SCOUT] QC checking screen ${idx}...`);
    // Auto-detect interaction types and run the appropriate QC steps (radio, checkbox, text, extended text, dropdowns, click-to-select, matching, etc.)
    await runQcChecks(pg, idx);
  });
});
