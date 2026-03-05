// SCOUT — PIAAC Country/Language Discovery
// Logs into piaac.ets.org, selects Version, then iterates all countries
// to discover available language options for each.
// Usage: PIAAC_USER=xxx PIAAC_PASS=xxx node scripts/discover-piaac-countries.js
//
// Output: JSON with countries array to stdout
// Debug logs go to stderr

const { chromium } = require('playwright');

const BASE_URL = 'https://piaac.ets.org/portal/translations/';
const USERNAME = process.env.PIAAC_USER || '';
const PASSWORD = process.env.PIAAC_PASS || '';
const VERSION = process.env.PIAAC_VERSION || 'FT New';

async function waitForSelectOptions(page, selectId, timeout) {
  timeout = timeout || 10000;
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const count = await page.locator(selectId + ' option').count();
    if (count > 1) return count;
    await page.waitForTimeout(500);
  }
  return 0;
}

async function getSelectOptions(page, selectId) {
  return page.locator(selectId).evaluate(el =>
    Array.from(el.options)
      .filter(o => o.value && o.value !== '' && o.value !== '0')
      .map(o => ({ code: o.value, text: o.textContent.trim() }))
  );
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  // 1. Navigate
  console.error('[1/4] Navigating to portal...');
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });

  // 2. Login (WordPress form)
  console.error('[2/4] Logging in...');
  await page.fill('#user_login', USERNAME);
  await page.fill('#user_pass', PASSWORD);
  await page.click('#wp-submit');
  await page.waitForLoadState('networkidle', { timeout: 15000 });
  console.error('[2/4] Post-login URL:', page.url());

  // 3. Select Version
  console.error('[3/4] Selecting Version:', VERSION);
  await page.selectOption('#VerSelect', { label: VERSION });
  await page.waitForTimeout(1000);
  await page.locator('#VerSelect').dispatchEvent('change');
  await page.waitForTimeout(2000);

  // Wait for country dropdown to populate
  var countryCount = await waitForSelectOptions(page, '#CountrySelect', 10000);
  console.error('[3/4] Country options loaded:', countryCount);

  // 4. Iterate countries and discover languages
  console.error('[4/4] Discovering languages for each country...');
  var countries = await getSelectOptions(page, '#CountrySelect');
  console.error('[4/4] Countries found:', countries.length);

  var results = [];

  for (var i = 0; i < countries.length; i++) {
    var country = countries[i];
    console.error(`  [${i + 1}/${countries.length}] ${country.code} (${country.text})...`);

    // Select country
    await page.selectOption('#CountrySelect', country.code);
    await page.locator('#CountrySelect').dispatchEvent('change');
    await page.waitForTimeout(2000);

    // Wait for language dropdown to populate
    var langCount = await waitForSelectOptions(page, '#LangSelect', 10000);

    var languages = [];
    if (langCount > 0) {
      languages = await getSelectOptions(page, '#LangSelect');
    }

    console.error(`    Languages: ${languages.map(l => l.code).join(', ') || '(none)'}`);

    results.push({
      code: country.code,
      text: country.text,
      languages: languages,
    });
  }

  // Output results
  var output = {
    version: VERSION,
    discovered_at: new Date().toISOString(),
    countries: results,
  };

  console.log(JSON.stringify(output, null, 2));
  console.error(`\nDone. ${results.length} countries discovered.`);

  await browser.close();
}

run().catch(err => {
  console.error('Fatal error:', err.message);
  process.exit(1);
});
