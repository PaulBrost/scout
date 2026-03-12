// SCOUT — PIAAC Portal Navigation Helper
// Centralizes portal filter navigation and item interaction for PIAAC tests.
// Reuses login() from auth.js — the PIAAC environment has WordPress auth selectors in DB.

const SELECTORS = {
  version: '#VerSelect',
  country: '#CountrySelect',
  language: '#LangSelect',
  domain: '#DomainSelect',
  cluster: '#ClusterSelect',
};

const DEFAULT_FILTERS = {
  version: 'FT New',
  country: 'ZZZ',
  language: 'eng',
  domain: 'LITNew',
};

/**
 * Wait until a <select> has more than one option (dependent data loaded).
 * @param {import('@playwright/test').Page} page
 * @param {string} selector - CSS selector for the <select>
 * @param {number} timeout - Max wait in ms
 * @returns {Promise<number>} Number of options found
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

/**
 * Apply cascading dropdown filters on the PIAAC translation portal.
 * Order: Version → Country → Language → Domain. Each triggers a change event
 * and waits for the next dropdown to populate.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} filters - { version, country, language, domain }
 */
async function selectFilters(page, filters = {}) {
  const f = { ...DEFAULT_FILTERS, ...filters };

  // Version
  await page.waitForSelector(SELECTORS.version, { timeout: 15000 });
  await page.selectOption(SELECTORS.version, { label: f.version });
  await page.locator(SELECTORS.version).dispatchEvent('change');
  await page.waitForTimeout(2000);

  // Country
  await waitForSelectOptions(page, SELECTORS.country);
  await page.selectOption(SELECTORS.country, f.country);
  await page.locator(SELECTORS.country).dispatchEvent('change');
  await page.waitForTimeout(2000);

  // Language
  await waitForSelectOptions(page, SELECTORS.language);
  await page.selectOption(SELECTORS.language, f.language);
  await page.locator(SELECTORS.language).dispatchEvent('change');
  await page.waitForTimeout(2000);

  // Domain
  await waitForSelectOptions(page, SELECTORS.domain);
  try {
    await page.selectOption(SELECTORS.domain, f.domain);
  } catch {
    await page.selectOption(SELECTORS.domain, { label: f.domain });
  }
  await page.locator(SELECTORS.domain).dispatchEvent('change');
  await page.waitForTimeout(2000);
}

/**
 * Extract visible item links from the portal page after filters are applied.
 * Waits for links to appear (filters trigger async content load).
 * @param {import('@playwright/test').Page} page
 * @param {number} timeout - Max wait in ms for links to appear (default 15000)
 * @returns {Promise<Array<{itemId: string, linkText: string, href: string}>>}
 */
async function getItemLinks(page, timeout = 15000) {
  // Wait for item links to appear after filter selection
  const start = Date.now();
  let links = [];
  while (Date.now() - start < timeout) {
    links = await page.locator('a').evaluateAll(els =>
      els
        .filter(el => el.offsetParent !== null && el.textContent.trim().length > 1)
        .filter(el => {
          const text = el.textContent.trim();
          // PIAAC item links contain unit identifiers like "U593-BirthdayParty"
          return /^U\d+/i.test(text) || el.href?.includes('unit') || el.getAttribute('onclick');
        })
        .map(el => ({
          itemId: el.textContent.trim().split(/\s+/)[0],
          linkText: el.textContent.trim(),
          href: el.href || '',
        }))
    );
    if (links.length > 0) return links;
    await page.waitForTimeout(1000);
  }
  return links;
}

/**
 * Click an item link and handle the popup window that opens.
 * PIAAC items open in new browser windows/tabs.
 *
 * @param {import('@playwright/test').Page} portalPage - The portal page with item links
 * @param {string} itemId - Item identifier to click (e.g., "U593-BirthdayParty")
 * @returns {Promise<import('@playwright/test').Page>} The new page (popup)
 */
async function openItem(portalPage, itemId) {
  const [newPage] = await Promise.all([
    portalPage.context().waitForEvent('page'),
    portalPage.locator(`a:has-text("${itemId}")`).first().click(),
  ]);
  await newPage.waitForLoadState('domcontentloaded');
  return newPage;
}

/**
 * Extract text content from a PIAAC item page.
 * Handles items that render inside iframes or directly on the page.
 *
 * @param {import('@playwright/test').Page} itemPage - The item page (popup)
 * @returns {Promise<string>} Extracted text content
 */
async function extractItemContent(itemPage) {
  // Check if item content is inside an iframe
  let text = '';
  try {
    const hasIframe = await itemPage.locator('iframe').count();
    if (hasIframe > 0) {
      const frame = itemPage.frameLocator('iframe').first();
      text = await frame.locator('body').innerText({ timeout: 10000 });
    } else {
      text = await itemPage.locator('body').innerText({ timeout: 10000 });
    }
  } catch {
    // Fallback: try getting text from the whole page
    text = await itemPage.locator('body').innerText().catch(() => '');
  }
  return text;
}

module.exports = {
  waitForSelectOptions,
  selectFilters,
  getItemLinks,
  openItem,
  extractItemContent,
  DEFAULT_FILTERS,
  SELECTORS,
};
