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
  // Wait for item links to appear after filter selection.
  // The portal renders items as <li class="unitXLIFF" data-unit="U504-Crayons">
  // or as <a> tags with unit IDs in the text.
  const start = Date.now();
  let links = [];
  while (Date.now() - start < timeout) {
    // Primary: look for li[data-unit] elements (PIAAC portal structure)
    links = await page.$$eval(
      'li[data-unit]',
      els => els.map(el => ({
        itemId: el.getAttribute('data-unit') || (el.textContent || '').trim(),
        linkText: (el.textContent || '').trim(),
        href: '',
        dataPath: el.getAttribute('data-path') || '',
      }))
    );
    if (links.length > 0) return links;

    // Fallback: look for any visible element whose text starts with a unit ID
    links = await page.$$eval(
      'a, li, span, div, [onclick]',
      els => els
        .filter(el => {
          const text = (el.textContent || '').trim();
          if (!/^U\d+/i.test(text)) return false;
          // Skip parent containers — only match leaf elements
          if (el.children.length > 0) {
            const childTexts = Array.from(el.children).map(c => (c.textContent || '').trim());
            if (childTexts.some(t => /^U\d+/i.test(t))) return false;
          }
          const style = window.getComputedStyle(el);
          return style.display !== 'none' && style.visibility !== 'hidden';
        })
        .map(el => ({
          itemId: (el.textContent || '').trim().split(/\s+/)[0],
          linkText: (el.textContent || '').trim(),
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
  // Items may be <li data-unit="...">, <a>, or other clickable elements.
  // Try the most specific selector first, then fall back to text match.
  const dataUnit = portalPage.locator(`li[data-unit="${itemId}"]`).first();
  const anchorLink = portalPage.locator(`a:has-text("${itemId}")`).first();
  const textMatch = portalPage.locator(`text="${itemId}"`).first();

  let target;
  if (await dataUnit.isVisible({ timeout: 2000 }).catch(() => false)) {
    target = dataUnit;
  } else if (await anchorLink.isVisible({ timeout: 2000 }).catch(() => false)) {
    target = anchorLink;
  } else {
    target = textMatch;
  }

  const [newPage] = await Promise.all([
    portalPage.context().waitForEvent('page'),
    target.click(),
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

/**
 * Get item navigation selectors from environment config.
 * Falls back to sensible defaults if not configured.
 * Admins configure these via the environment edit page in SCOUT.
 *
 * @param {object|null} envConfig - Environment config from SCOUT_ENV_CONFIG
 * @returns {object} { next, finish, close, continue_btn, content_frame }
 */
function getItemSelectors(envConfig) {
  const defaults = {
    next: null,
    finish: null,
    close: null,
    continue_btn: null,
    content_frame: null,
  };
  if (!envConfig || !envConfig.launcher_config || !envConfig.launcher_config.item_selectors) {
    return defaults;
  }
  const sel = envConfig.launcher_config.item_selectors;
  return {
    next: sel.next_button || defaults.next,
    finish: sel.finish_button || defaults.finish,
    close: sel.close_button || defaults.close,
    continue_btn: sel.continue_button || defaults.continue_btn,
    content_frame: sel.content_frame || defaults.content_frame,
  };
}

/**
 * Navigate through all screens of a PIAAC item, calling a callback on each screen.
 * Uses configurable selectors from the environment's launcher_config.item_selectors.
 *
 * @param {import('@playwright/test').Page} itemPage - The item popup page
 * @param {object|null} envConfig - Environment config from SCOUT_ENV_CONFIG
 * @param {function} onScreen - async callback(itemPage, screenIndex) called on each screen
 * @returns {Promise<number>} Total number of screens visited
 */
async function navigateItemScreens(itemPage, envConfig, onScreen) {
  const sel = getItemSelectors(envConfig);
  let screenIndex = 1;

  // If content is inside an iframe, get the frame reference
  let contentTarget = itemPage;
  if (sel.content_frame) {
    try {
      const frame = itemPage.frameLocator(sel.content_frame).first();
      // Verify the frame exists by checking for body
      await frame.locator('body').waitFor({ state: 'attached', timeout: 10000 });
      contentTarget = frame;
    } catch {
      // Frame not found, use the page directly
      contentTarget = itemPage;
    }
  }

  while (true) {
    await itemPage.waitForLoadState('networkidle');

    // Capture page text for AI analysis
    try {
      const text = await extractItemContent(itemPage);
      if (text && text.trim()) {
        console.log(`[SCOUT_TEXT] ${JSON.stringify({ label: `Screen ${screenIndex}`, text: text.trim() })}`);
      }
    } catch { /* text extraction is best-effort */ }

    await onScreen(itemPage, screenIndex);

    // Try to advance: next button first, then finish/continue as end-of-item indicators
    let advanced = false;

    if (sel.next) {
      try {
        const nextBtn = contentTarget.locator(sel.next);
        const isVisible = await nextBtn.isVisible({ timeout: 3000 });
        if (isVisible) {
          const isDisabled = await nextBtn.isDisabled().catch(() => false);
          if (!isDisabled) {
            await nextBtn.click();
            await itemPage.waitForTimeout(1000);
            advanced = true;
          }
        }
      } catch {
        // Next button not found or not clickable
      }
    }

    if (!advanced) {
      // Check for finish/continue buttons — these indicate end of item
      // but we may want to capture the screen after clicking them
      for (const btnSel of [sel.finish, sel.continue_btn]) {
        if (!btnSel) continue;
        try {
          const btn = contentTarget.locator(btnSel);
          const isVisible = await btn.isVisible({ timeout: 2000 });
          if (isVisible) {
            const isDisabled = await btn.isDisabled().catch(() => false);
            if (!isDisabled) {
              await btn.click();
              await itemPage.waitForTimeout(1000);
              screenIndex++;
              await itemPage.waitForLoadState('networkidle');
              try {
                const text = await extractItemContent(itemPage);
                if (text && text.trim()) {
                  console.log(`[SCOUT_TEXT] ${JSON.stringify({ label: `Screen ${screenIndex}`, text: text.trim() })}`);
                }
              } catch { /* best-effort */ }
              await onScreen(itemPage, screenIndex);
            }
          }
        } catch {
          // Button not found
        }
      }
      break;
    }

    screenIndex++;
  }

  return screenIndex;
}

module.exports = {
  waitForSelectOptions,
  selectFilters,
  getItemLinks,
  openItem,
  extractItemContent,
  getItemSelectors,
  navigateItemScreens,
  DEFAULT_FILTERS,
  SELECTORS,
};
