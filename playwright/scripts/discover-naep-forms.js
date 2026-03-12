// SCOUT — NAEP Form Discovery
// Logs into a NAEP review site, reads the #TheTest dropdown to discover
// all available test forms, and outputs structured JSON.
//
// Usage: node scripts/discover-naep-forms.js --url=https://rt.ets.org/c3.NET/gates_review.aspx --password=c3c4
//
// Output: JSON with forms array to stdout. Debug logs to stderr.

const { chromium } = require('playwright');

function parseArgs() {
  const args = {};
  for (const arg of process.argv.slice(2)) {
    const match = arg.match(/^--(\w+)=(.+)$/);
    if (match) args[match[1]] = match[2];
  }
  return args;
}

const cliArgs = parseArgs();
const URL = cliArgs.url || process.env.ASSESSMENT_URL || '';
const PASSWORD = cliArgs.password || process.env.ASSESSMENT_PASSWORD || '';

if (!URL || !PASSWORD) {
  console.error('Usage: node scripts/discover-naep-forms.js --url=<review_url> --password=<password>');
  process.exit(1);
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // 1. Navigate & login
  console.error('[1/3] Navigating to', URL);
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  console.error('[1/3] URL:', page.url());

  console.error('[2/3] Logging in...');
  await page.waitForSelector('#_ctl0_Body_PasswordText', { timeout: 15000 });
  await page.fill('#_ctl0_Body_PasswordText', PASSWORD);
  await page.click('#_ctl0_Body_SubmitButton');
  await page.waitForURL(u => !u.toString().includes('Password'), { timeout: 30000 });
  console.error('[2/3] Post-login URL:', page.url());

  // 3. Read the #TheTest dropdown
  console.error('[3/3] Reading form dropdown...');
  await page.waitForSelector('#TheTest', { timeout: 15000 });

  const forms = await page.locator('#TheTest').evaluate(el =>
    Array.from(el.options)
      .filter(o => o.value && o.value.trim() !== '')
      .map(o => ({
        value: o.value,
        label: o.textContent.trim(),
      }))
  );

  console.error(`[3/3] Found ${forms.length} forms`);

  const output = {
    url: URL,
    discovered_at: new Date().toISOString(),
    forms: forms,
  };

  console.log(JSON.stringify(output, null, 2));

  await browser.close();
}

run().catch(err => {
  console.error('Fatal error:', err.message);
  process.exit(1);
});
