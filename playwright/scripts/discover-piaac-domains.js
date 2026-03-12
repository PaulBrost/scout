// SCOUT — PIAAC All-Domain Discovery
// Logs into piaac.ets.org, enumerates every domain for a given country/language,
// and discovers items in each domain — all in a single browser session.
//
// Usage: PIAAC_USER=xxx PIAAC_PASS=xxx node scripts/discover-piaac-domains.js [--country=ZZZ] [--language=eng]
//
// Output: JSON with domains array (each containing items) to stdout.
//         Also writes per-domain files to playwright/data/piaac-{domain}-items.json
//         Debug screenshots + HTML saved to /tmp/piaac-domains/
// Debug logs go to stderr.

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'https://piaac.ets.org/portal/translations/';
const USERNAME = process.env.PIAAC_USER || '';
const PASSWORD = process.env.PIAAC_PASS || '';
const DEBUG_DIR = '/tmp/piaac-domains';

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
};

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
      .filter(o => o.value && o.value !== '' && o.value !== '0' && o.value !== '-1')
      .map(o => ({ value: o.value, text: o.textContent.trim() }))
  );
}

/**
 * Scan the page for any visible element whose text matches a PIAAC unit pattern (U + digits).
 * Checks <a>, <div>, <span>, <td>, <button>, <li> — not just links.
 * Polls for up to `timeout` ms since items load asynchronously.
 */
async function scanForItems(page, timeout) {
  timeout = timeout || 15000;
  const start = Date.now();
  let items = [];
  while (Date.now() - start < timeout) {
    items = await page.evaluate(() => {
      const unitPattern = /^U\d{3,}/i;
      const found = [];
      // Check all visible elements, not just <a> tags
      const els = document.querySelectorAll('a, div, span, td, li, button, p, h1, h2, h3, h4, h5, h6, label');
      for (const el of els) {
        if (el.offsetParent === null) continue;
        // Use only the element's direct text (not children) for precision,
        // but fall back to full textContent for links
        let text = '';
        if (el.tagName === 'A') {
          text = el.textContent.trim();
        } else {
          // Check direct text nodes only to avoid double-counting
          for (const node of el.childNodes) {
            if (node.nodeType === 3) text += node.textContent;
          }
          text = text.trim();
          if (!text) text = el.textContent.trim();
        }
        if (!unitPattern.test(text)) continue;
        const id = text.split(/\s+/)[0];
        found.push({
          item_id: id,
          unit_name: text.substring(0, 200),
          href: el.href || '',
          tag: el.tagName,
        });
      }
      return found;
    });
    if (items.length > 0) break;
    await page.waitForTimeout(1000);
  }
  // Deduplicate by item_id
  const seen = new Set();
  return items.filter(item => {
    if (seen.has(item.item_id)) return false;
    seen.add(item.item_id);
    return true;
  });
}

async function discoverItemsForDomain(page, domain, domainIndex) {
  // Select domain
  try {
    await page.selectOption('#DomainSelect', domain.value);
  } catch {
    await page.selectOption('#DomainSelect', { label: domain.text });
  }
  await page.locator('#DomainSelect').dispatchEvent('change');
  await page.waitForTimeout(3000);

  // Save debug screenshot after domain selection
  const slug = domain.value.toLowerCase().replace(/[^a-z0-9]/g, '');
  await page.screenshot({ path: `${DEBUG_DIR}/${domainIndex}-${slug}-after-domain.png`, fullPage: true });

  // Check if a cluster dropdown appeared and has options
  const clusterCount = await waitForSelectOptions(page, '#ClusterSelect', 8000);

  // Try scanning for items directly first (some domains may not need clusters)
  let directItems = await scanForItems(page, 5000);
  if (directItems.length > 0) {
    console.error(`    → Found ${directItems.length} items directly (no cluster needed)`);
    return directItems;
  }

  // If there are clusters, iterate each one to collect all items
  if (clusterCount > 0) {
    const clusters = await getSelectOptions(page, '#ClusterSelect');
    console.error(`    Clusters (${clusters.length}): ${clusters.map(c => c.value).join(', ')}`);

    const allItems = [];
    const seen = new Set();

    for (let ci = 0; ci < clusters.length; ci++) {
      const cluster = clusters[ci];
      console.error(`      [${ci + 1}/${clusters.length}] Cluster: ${cluster.value}...`);
      try {
        await page.selectOption('#ClusterSelect', cluster.value);
      } catch {
        await page.selectOption('#ClusterSelect', { label: cluster.text });
      }
      await page.locator('#ClusterSelect').dispatchEvent('change');
      await page.waitForTimeout(2000);

      await page.screenshot({ path: `${DEBUG_DIR}/${domainIndex}-${slug}-cluster-${ci}.png`, fullPage: true });

      const items = await scanForItems(page, 10000);
      for (const item of items) {
        if (!seen.has(item.item_id)) {
          seen.add(item.item_id);
          item.cluster = cluster.value;
          allItems.push(item);
        }
      }
      console.error(`        → ${items.length} items`);
    }

    if (allItems.length > 0) return allItems;
  }

  // Last resort: save HTML for manual inspection
  const html = await page.content();
  fs.writeFileSync(`${DEBUG_DIR}/${domainIndex}-${slug}-page.html`, html);
  console.error(`    → 0 items found. HTML saved for inspection.`);

  // Also dump any text on the page that looks like it might be a unit ID
  const bodyText = await page.locator('body').innerText();
  const unitMatches = bodyText.match(/U\d{3,}[A-Za-z0-9-]*/g) || [];
  if (unitMatches.length > 0) {
    console.error(`    → Found unit-like text in body: ${[...new Set(unitMatches)].join(', ')}`);
    // Return these as items with a note they came from text scan
    const textItems = [];
    const seen2 = new Set();
    for (const m of unitMatches) {
      const id = m.split(/\s+/)[0];
      if (!seen2.has(id)) {
        seen2.add(id);
        textItems.push({ item_id: id, unit_name: id, href: '', source: 'text-scan' });
      }
    }
    return textItems;
  }

  return [];
}

async function run() {
  if (!USERNAME || !PASSWORD) {
    console.error('Error: PIAAC_USER and PIAAC_PASS environment variables are required.');
    process.exit(1);
  }

  // Create debug directory
  fs.mkdirSync(DEBUG_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  // 1. Navigate & login
  console.error('[1/5] Navigating to portal...');
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
  await page.screenshot({ path: `${DEBUG_DIR}/01-before-login.png`, fullPage: true });

  console.error('[2/5] Logging in...');
  await page.fill('#user_login', USERNAME);
  await page.fill('#user_pass', PASSWORD);
  await page.click('#wp-submit');
  await page.waitForLoadState('networkidle', { timeout: 15000 });
  console.error('[2/5] Post-login URL:', page.url());
  await page.screenshot({ path: `${DEBUG_DIR}/02-post-login.png`, fullPage: true });

  // 3. Select Version
  console.error('[3/5] Selecting Version:', FILTERS.version);
  await page.selectOption('#VerSelect', { label: FILTERS.version });
  await page.waitForTimeout(1000);
  await page.locator('#VerSelect').dispatchEvent('change');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${DEBUG_DIR}/03-version.png`, fullPage: true });

  // 4. Select Country → Language
  console.error('[4/5] Selecting Country:', FILTERS.country, '→ Language:', FILTERS.language);
  await waitForSelectOptions(page, '#CountrySelect', 10000);
  await page.selectOption('#CountrySelect', FILTERS.country);
  await page.locator('#CountrySelect').dispatchEvent('change');
  await page.waitForTimeout(2000);

  await waitForSelectOptions(page, '#LangSelect', 10000);
  await page.selectOption('#LangSelect', FILTERS.language);
  await page.locator('#LangSelect').dispatchEvent('change');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${DEBUG_DIR}/04-language.png`, fullPage: true });

  // Wait for domain dropdown to populate
  await waitForSelectOptions(page, '#DomainSelect', 10000);
  const domains = await getSelectOptions(page, '#DomainSelect');
  console.error(`[5/5] Found ${domains.length} domains:`, domains.map(d => d.value).join(', '));

  // 5. Iterate each domain and discover items
  const results = [];
  const dataDir = path.resolve(__dirname, '..', 'data');

  for (let i = 0; i < domains.length; i++) {
    const domain = domains[i];
    console.error(`  [${i + 1}/${domains.length}] ${domain.value} (${domain.text})...`);

    const items = await discoverItemsForDomain(page, domain, i);
    console.error(`    → ${items.length} items total`);

    const domainResult = {
      domain: domain.value,
      domain_label: domain.text,
      items: items,
    };
    results.push(domainResult);

    // Write per-domain file
    const perDomainData = {
      filters_applied: {
        version: FILTERS.version,
        country: FILTERS.country,
        language: FILTERS.language,
        domain: domain.value,
      },
      items: items,
    };
    const filename = `piaac-${domain.value.toLowerCase()}-items.json`;
    fs.writeFileSync(path.join(dataDir, filename), JSON.stringify(perDomainData, null, 2));
    console.error(`    → Saved ${filename}`);
  }

  // Output combined results
  const output = {
    version: FILTERS.version,
    country: FILTERS.country,
    language: FILTERS.language,
    discovered_at: new Date().toISOString(),
    domains: results,
  };

  console.log(JSON.stringify(output, null, 2));

  const totalItems = results.reduce((sum, d) => sum + d.items.length, 0);
  console.error(`\nDone. ${results.length} domains, ${totalItems} total items.`);
  console.error(`Debug screenshots saved to ${DEBUG_DIR}/`);

  await browser.close();
}

run().catch(err => {
  console.error('Fatal error:', err.message);
  process.exit(1);
});
