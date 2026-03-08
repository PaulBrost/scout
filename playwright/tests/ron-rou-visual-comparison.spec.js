const { test, expect } = require('@playwright/test');
const { login } = require('../src/helpers/auth');
const { selectFilters, DEFAULT_FILTERS } = require('../src/helpers/piaac');
const fs = require('fs');
const path = require('path');
const { PNG } = require('pngjs');
const pixelmatch = require('pixelmatch');

function loadEnvConfig() {
  const raw = process.env.SCOUT_ENV_CONFIG;
  if (!raw) throw new Error('SCOUT_ENV_CONFIG env var not set. Run through SCOUT runner or set manually.');
  return JSON.parse(raw);
}

const ITEM_ID = 'U501-Hiccups';

// Baseline snapshots from run b26285fb (ZZZ/eng)
const BASELINE_DIR = path.resolve(__dirname, 'u501-hiccups-baseline.spec.js-snapshots');
const BASELINES = {
  'u501-q1-c501p001': 'u501-q1-c501p001-chrome-desktop-linux.png',
  'u501-item1a':      'u501-item1a-chrome-desktop-linux.png',
  'u501-c501p002':    'u501-c501p002-chrome-desktop-linux.png',
  'u501-c501p003':    'u501-c501p003-chrome-desktop-linux.png',
};

const OUTPUT_DIR = path.resolve(__dirname, '../test-results/ron-rou-comparison');

/**
 * Compare two PNG buffers using pixelmatch.
 * threshold 0.4 tolerates text/color diffs while catching layout breaks.
 */
function compareImages(actualBuf, baselineBuf, name) {
  const actual = PNG.sync.read(actualBuf);
  const baseline = PNG.sync.read(baselineBuf);

  const width = Math.min(actual.width, baseline.width);
  const height = Math.min(actual.height, baseline.height);

  const cropPng = (src, w, h) => {
    const out = new PNG({ width: w, height: h });
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const si = (y * src.width + x) * 4;
        const di = (y * w + x) * 4;
        out.data[di] = src.data[si];
        out.data[di + 1] = src.data[si + 1];
        out.data[di + 2] = src.data[si + 2];
        out.data[di + 3] = src.data[si + 3];
      }
    }
    return out;
  };

  const a = actual.width === width && actual.height === height ? actual : cropPng(actual, width, height);
  const b = baseline.width === width && baseline.height === height ? baseline : cropPng(baseline, width, height);

  const diff = new PNG({ width, height });
  const diffPixels = pixelmatch(a.data, b.data, diff.data, width, height, {
    threshold: 0.4,
    alpha: 0.3,
  });

  const totalPixels = width * height;
  const diffRatio = totalPixels > 0 ? diffPixels / totalPixels : 0;

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  fs.writeFileSync(path.join(OUTPUT_DIR, `${name}-diff.png`), PNG.sync.write(diff));
  fs.writeFileSync(path.join(OUTPUT_DIR, `${name}-actual.png`), actualBuf);

  return {
    diffPixels, totalPixels, diffRatio,
    actualSize: { w: actual.width, h: actual.height },
    baselineSize: { w: baseline.width, h: baseline.height },
  };
}

/**
 * Detect text overflow issues across all frames.
 */
async function findTextOverflowIssues(itemPage) {
  const frames = itemPage.frames();
  const allIssues = [];

  for (const frame of frames) {
    const issues = await frame.evaluate(() => {
      function isVisible(el) {
        const style = getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      }
      function shortPath(el) {
        const parts = [];
        let node = el;
        for (let i = 0; i < 5 && node && node.nodeType === 1; i++) {
          const name = node.tagName.toLowerCase();
          const id = node.id ? '#' + node.id : '';
          const cls = node.className && typeof node.className === 'string'
            ? '.' + node.className.trim().split(/\s+/).slice(0, 2).join('.')
            : '';
          parts.unshift(name + id + cls);
          node = node.parentElement;
        }
        return parts.join(' > ');
      }

      const selectors = ['p','h1','h2','h3','h4','h5','h6','li','label','span','a','button','div'];
      const nodes = Array.from(document.querySelectorAll(selectors.join(',')));
      const issues = [];

      for (const el of nodes) {
        if (!isVisible(el)) continue;
        const text = (el.textContent || '').trim();
        if (!text) continue;

        const cs = getComputedStyle(el);
        const allowScroll = ['auto','scroll'].includes(cs.overflow)
          || ['auto','scroll'].includes(cs.overflowX)
          || ['auto','scroll'].includes(cs.overflowY);
        if (allowScroll) continue;

        const overflowX = el.scrollWidth - el.clientWidth > 1;
        const overflowY = el.scrollHeight - el.clientHeight > 1;

        if (overflowX || overflowY) {
          issues.push({
            path: shortPath(el),
            textPreview: text.slice(0, 150),
            client: { w: el.clientWidth, h: el.clientHeight },
            scroll: { w: el.scrollWidth, h: el.scrollHeight },
          });
        }
      }
      return issues;
    });

    allIssues.push(
      ...issues.map(i => ({ ...i, frameName: frame.name() || '', frameUrl: frame.url() }))
    );
  }
  return allIssues;
}

// Flag if more than 5% of non-text pixels differ (layout break)
const LAYOUT_DIFF_THRESHOLD = 0.05;

test.describe('ron-ROU Visual Comparison', () => {
  test('ROU/ron vs ZZZ/eng baseline — layout and overflow check', async ({ page }) => {
    test.setTimeout(180000);

    const envConfig = loadEnvConfig();
    await login(page, { env: envConfig });

    await selectFilters(page, { ...DEFAULT_FILTERS, country: 'ROU', language: 'ron' });
    await page.waitForTimeout(3000);

    // Open item popup
    const itemEl = page.locator(`text=${ITEM_ID}`).first();
    await expect(itemEl).toBeVisible({ timeout: 10000 });

    const [itemPage] = await Promise.all([
      page.context().waitForEvent('page'),
      itemEl.click(),
    ]);
    await itemPage.waitForLoadState('networkidle');
    await itemPage.waitForTimeout(2000);

    try {
      fs.mkdirSync(OUTPUT_DIR, { recursive: true });
      const failures = [];
      const comparisons = [];

      // --- Screen 1: Q1 / C501P001 (initial screen) ---
      {
        const name = 'u501-q1-c501p001';
        const bFile = path.join(BASELINE_DIR, BASELINES[name]);
        if (fs.existsSync(bFile)) {
          const buf = await itemPage.screenshot({ fullPage: true });
          const result = compareImages(buf, fs.readFileSync(bFile), name);
          comparisons.push({ name, ...result });
          if (result.diffRatio > LAYOUT_DIFF_THRESHOLD) {
            failures.push(`${name}: ${(result.diffRatio * 100).toFixed(2)}% diff (>${LAYOUT_DIFF_THRESHOLD * 100}%)`);
          }
        } else {
          failures.push(`Baseline not found: ${bFile}`);
        }
      }

      // Navigate through item screens: item1a, C501P002, C501P003
      const screens = [
        { btn: 'item1a',   name: 'u501-item1a' },
        { btn: 'C501P002', name: 'u501-c501p002' },
        { btn: 'C501P003', name: 'u501-c501p003' },
      ];

      for (const screen of screens) {
        const btn = itemPage.locator(`input[value="${screen.btn}"], button:has-text("${screen.btn}")`).first();
        if (await btn.count() > 0) {
          await btn.click();
          await itemPage.waitForLoadState('networkidle');
          await itemPage.waitForTimeout(1500);

          const bFile = path.join(BASELINE_DIR, BASELINES[screen.name]);
          if (fs.existsSync(bFile)) {
            const buf = await itemPage.screenshot({ fullPage: true });
            const result = compareImages(buf, fs.readFileSync(bFile), screen.name);
            comparisons.push({ name: screen.name, ...result });
            if (result.diffRatio > LAYOUT_DIFF_THRESHOLD) {
              failures.push(`${screen.name}: ${(result.diffRatio * 100).toFixed(2)}% diff (>${LAYOUT_DIFF_THRESHOLD * 100}%)`);
            }
          } else {
            failures.push(`Baseline not found: ${bFile}`);
          }
        }
      }

      // Attach comparison summary
      await test.info().attach('visual-comparison-results', {
        body: JSON.stringify({
          locale: 'ROU/ron',
          baseline: 'ZZZ/eng (run b26285fb)',
          threshold: LAYOUT_DIFF_THRESHOLD,
          comparisons: comparisons.map(c => ({
            name: c.name,
            diffRatio: (c.diffRatio * 100).toFixed(2) + '%',
            diffPixels: c.diffPixels,
            passed: c.diffRatio <= LAYOUT_DIFF_THRESHOLD,
          })),
        }, null, 2),
        contentType: 'application/json',
      });

      // --- Text overflow detection (run on last screen, navigate back to first) ---
      const firstBtn = itemPage.locator('input[value="C501P001"], button:has-text("C501P001")').first();
      if (await firstBtn.count() > 0) {
        await firstBtn.click();
        await itemPage.waitForLoadState('networkidle');
        await itemPage.waitForTimeout(1000);
      }

      const overflowIssues = await findTextOverflowIssues(itemPage);
      await test.info().attach('overflow-issues-ROU-ron', {
        body: JSON.stringify({ itemId: ITEM_ID, locale: 'ROU/ron', issues: overflowIssues }, null, 2),
        contentType: 'application/json',
      });

      if (overflowIssues.length > 0) {
        const summary = overflowIssues.map(i =>
          `  ${i.path} [${i.frameName || 'main'}]: client ${i.client.w}x${i.client.h}, scroll ${i.scroll.w}x${i.scroll.h}`
        ).join('\n');
        failures.push(`Text overflow (${overflowIssues.length}):\n${summary}`);
      }

      if (failures.length > 0) {
        throw new Error('Visual comparison issues:\n\n' + failures.join('\n\n'));
      }
    } finally {
      await itemPage.close();
    }
  });
});
