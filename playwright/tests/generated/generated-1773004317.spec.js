const { test, expect } = require('@playwright/test');
const { login } = require('../../src/helpers/auth');
const { selectFilters, openItem, extractItemContent, DEFAULT_FILTERS } = require('../../src/helpers/piaac');
const { analyzeItemText } = require('../../src/helpers/ai');

// Test: U501-Hiccups — iterate all screens, extract visible text, run AI text analysis (spelling/grammar/syntax)
// Environment: PIAAC Translation Portal — ZZZ country, eng language

async function loadEnvConfig() {
  // Prefer runner-provided env config if available
  if (process.env.SCOUT_ENV_CONFIG) {
    try { return JSON.parse(process.env.SCOUT_ENV_CONFIG); } catch (e) { /* ignore */ }
  }
  // Fallback to project config via auth.login internal logic if not provided
  return null;
}

async function applyPortalFilters(page) {
  // Use defaults but explicitly enforce ZZZ + eng as requested
  const filters = { ...DEFAULT_FILTERS, country: 'ZZZ', language: 'eng' };
  await selectFilters(page, filters);
}

async function analyzeScreensWithAI(screens, languageLabel) {
  const issues = [];
  for (const s of screens) {
    const text = (s && (s.text || s.content || s.visibleText || s.raw)) || '';
    const screenIndex = s && (s.index != null ? s.index : s.pageIndex != null ? s.pageIndex : null);
    // AI text analysis expects 'English' or 'Spanish' strings
    const result = await analyzeItemText(text, languageLabel);
    const hasIssues = !!(result && (result.issuesFound || (Array.isArray(result.issues) && result.issues.length > 0)));
    if (hasIssues) {
      issues.push({ screenIndex, issues: result.issues || [], raw: result.raw || '', model: result.model || 'unknown' });
    }
  }
  return issues;
}

// Helper to navigate to portal base URL prior to filters
async function gotoPortal(page, envConfig) {
  // If the environment config has a base_url, login() will navigate to it.
  await login(page, { env: envConfig });
}

// Main test
test('PIAAC U501-Hiccups: AI text QA across all screens (ZZZ / eng)', async ({ page }) => {
  const envConfig = await loadEnvConfig();

  // Login and land on PIAAC portal
  await gotoPortal(page, envConfig);

  // Apply filters: ZZZ (country) + eng (language)
  await applyPortalFilters(page);

  // Open the requested item in a new page/tab
  const itemId = 'U501-Hiccups';
  const itemPage = await openItem(page, itemId);

  // Ensure item UI is ready
  await itemPage.waitForLoadState('domcontentloaded');

  // Extract all screens' visible content via helper
  const content = await extractItemContent(itemPage);
  // Normalize to an array of screens
  const screens = Array.isArray(content) ? content : (content && content.screens ? content.screens : []);
  expect(screens.length).toBeGreaterThan(0);

  // Run AI text analysis for each screen
  const languageLabel = 'English'; // AI helper expects full language name
  const issues = await analyzeScreensWithAI(screens, languageLabel);

  // Report and flag issues
  if (issues.length > 0) {
    console.warn(`AI flagged issues on ${issues.length} screen(s) for ${itemId}:`);
    for (const entry of issues) {
      const idx = entry.screenIndex != null ? `Screen ${entry.screenIndex}` : 'Screen ?';
      console.warn(`${idx}: ${JSON.stringify(entry.issues)}`);
    }
  }

  expect(issues.length, 'AI detected spelling/grammar/syntax issues in item text').toBe(0);

  // Close the item page if it is still open
  try { await itemPage.close(); } catch (_) { /* ignore */ }
});
