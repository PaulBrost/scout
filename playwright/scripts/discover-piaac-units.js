// SCOUT — PIAAC Unit Discovery Scraper
// Logs into piaac.ets.org, selects dropdown filters, and discovers available units.
// Usage: PIAAC_USER=xxx PIAAC_PASS=xxx node scripts/discover-piaac-units.js [--country=ZZZ] [--language=eng] [--domain=LITNew]
//
// Output: JSON with structured items array to stdout
// Debug screenshots/logs go to stderr

const { chromium } = require('playwright');

const BASE_URL = 'https://piaac.ets.org/portal/translations/';
const USERNAME = process.env.PIAAC_USER || '';
const PASSWORD = process.env.PIAAC_PASS || '';

// Parse --key=value args from process.argv
function parseArgs() {
  const args = {};
  for (const arg of process.argv.slice(2)) {
    const match = arg.match(/^--(\w+)=(.+)$/);
    if (match) args[match[1]] = match[2];
  }
  return args;
}

const cliArgs = parseArgs();

const FILTERS = {
  version: cliArgs.version || process.env.PIAAC_VERSION || 'FT New',
  country: cliArgs.country || process.env.PIAAC_COUNTRY || 'ZZZ',
  language: cliArgs.language || process.env.PIAAC_LANGUAGE || 'eng',
  domain: cliArgs.domain || process.env.PIAAC_DOMAIN || 'LITNew',
};

async function waitForSelectOptions(page, selectId, timeout) {
  timeout = timeout || 10000;
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const count = await page.locator(selectId + ' option').count();
    if (count > 1) return count;   // more than just the placeholder
    await page.waitForTimeout(500);
  }
  return 0;
}

async function dumpSelect(page, selectId) {
  return page.locator(selectId).evaluate(el =>
    Array.from(el.options).map(o => ({ value: o.value, text: o.textContent.trim() }))
  );
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  // 1. Navigate
  console.error('[1/6] Navigating to portal...');
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
  console.error('[1/6] URL:', page.url(), '| Title:', await page.title());

  // 2. Login (WordPress form)
  console.error('[2/6] Logging in...');
  await page.fill('#user_login', USERNAME);
  await page.fill('#user_pass', PASSWORD);
  await page.click('#wp-submit');
  await page.waitForLoadState('networkidle', { timeout: 15000 });
  console.error('[2/6] Post-login URL:', page.url());
  await page.screenshot({ path: '/tmp/piaac-02-post-login.png', fullPage: true });

  // 3. Select Version
  console.error('[3/6] Selecting Version:', FILTERS.version);
  await page.selectOption('#VerSelect', { label: FILTERS.version });
  await page.waitForTimeout(1000);
  await page.locator('#VerSelect').dispatchEvent('change');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: '/tmp/piaac-03-version.png', fullPage: true });

  // 4. Select Country
  console.error('[4/6] Selecting Country:', FILTERS.country);
  var countryOpts = await waitForSelectOptions(page, '#CountrySelect', 5000);
  console.error('[4/6] Country options available:', countryOpts);
  await page.selectOption('#CountrySelect', FILTERS.country);
  await page.locator('#CountrySelect').dispatchEvent('change');
  await page.waitForTimeout(2000);

  // Wait for LangSelect to populate
  var langCount = await waitForSelectOptions(page, '#LangSelect', 10000);
  console.error('[4/6] Language options loaded:', langCount);
  var langOpts = await dumpSelect(page, '#LangSelect');
  console.error('[4/6] Languages:', langOpts.map(o => o.value + '=' + o.text).join(', '));
  await page.screenshot({ path: '/tmp/piaac-04-country.png', fullPage: true });

  // 5. Select Language
  console.error('[5/6] Selecting Language:', FILTERS.language);
  await page.selectOption('#LangSelect', FILTERS.language);
  await page.locator('#LangSelect').dispatchEvent('change');
  await page.waitForTimeout(2000);

  // Wait for DomainSelect to populate
  var domainCount = await waitForSelectOptions(page, '#DomainSelect', 10000);
  console.error('[5/6] Domain options loaded:', domainCount);
  var domainOpts = await dumpSelect(page, '#DomainSelect');
  console.error('[5/6] Domains:', domainOpts.map(o => o.value + '=' + o.text).join(', '));
  await page.screenshot({ path: '/tmp/piaac-05-language.png', fullPage: true });

  // 6. Select Domain
  console.error('[6/6] Selecting Domain:', FILTERS.domain);
  try {
    await page.selectOption('#DomainSelect', FILTERS.domain);
  } catch (e) {
    await page.selectOption('#DomainSelect', { label: FILTERS.domain });
  }
  await page.locator('#DomainSelect').dispatchEvent('change');
  await page.waitForTimeout(2000);

  // Wait for clusters/units to appear
  var clusterCount = await waitForSelectOptions(page, '#ClusterSelect', 10000);
  console.error('[6/6] Cluster options loaded:', clusterCount);
  if (clusterCount > 0) {
    var clusterOpts = await dumpSelect(page, '#ClusterSelect');
    console.error('[6/6] Clusters:', clusterOpts.map(o => o.value + '=' + o.text).join(', '));
  }

  await page.screenshot({ path: '/tmp/piaac-06-domain.png', fullPage: true });

  // Look for unit links/buttons that appeared after filter selection
  console.error('[6/6] Scanning for units...');

  // Get all links on the page
  var allLinks = await page.locator('a').evaluateAll(els =>
    els.filter(el => el.offsetParent !== null).map(el => ({
      text: el.textContent.trim().substring(0, 200),
      href: el.href || '',
      id: el.id,
      classes: el.className,
      onclick: el.getAttribute('onclick') || ''
    }))
  );

  // Also check for clickable elements (divs, spans, buttons) that might be units
  var clickables = await page.locator('[onclick], [data-unit], .unit, .cluster, .item-link, button:not(#wp-submit)').evaluateAll(els =>
    els.filter(el => el.offsetParent !== null).map(el => ({
      tag: el.tagName,
      text: el.textContent.trim().substring(0, 200),
      href: el.href || '',
      id: el.id,
      classes: el.className,
      onclick: el.getAttribute('onclick') || '',
      dataUnit: el.getAttribute('data-unit') || ''
    }))
  );

  // Get page body text to see what's visible
  var bodyText = await page.locator('body').innerText();

  // Save full HTML
  var html = await page.content();
  require('fs').writeFileSync('/tmp/piaac-page.html', html);
  console.error('[6/6] Full HTML saved to /tmp/piaac-page.html');

  // Build structured items array from discovered links
  var items = allLinks
    .filter(l => l.text.length > 1 && /^U\d+/i.test(l.text.trim()))
    .map(l => {
      var text = l.text.trim();
      var parts = text.split(/\s+/);
      return {
        item_id: parts[0],
        unit_name: text,
        href: l.href,
        link_text: text,
      };
    });

  // Deduplicate by item_id
  var seen = new Set();
  items = items.filter(item => {
    if (seen.has(item.item_id)) return false;
    seen.add(item.item_id);
    return true;
  });

  console.error(`[6/6] Found ${items.length} structured items`);

  // Output results
  var result = {
    url: page.url(),
    filters_applied: FILTERS,
    items: items,
    links: allLinks.filter(l => l.text.length > 1),
    clickables: clickables,
    bodyText: bodyText,
    clusterOptions: clusterCount > 0 ? await dumpSelect(page, '#ClusterSelect') : [],
  };

  console.log(JSON.stringify(result, null, 2));

  await browser.close();
}

run().catch(err => {
  console.error('Fatal error:', err.message);
  process.exit(1);
});
