// SCOUT — Playwright Configuration
// Browser matrix, visual regression thresholds, and reporter setup.

const { devices } = require('@playwright/test');

// Parse viewport override from env: "WIDTHxHEIGHT" e.g. "1280x720"
function parseViewport() {
  const vp = process.env.SCOUT_VIEWPORT;
  if (!vp) return undefined;
  const parts = vp.split('x');
  if (parts.length === 2) {
    const w = parseInt(parts[0], 10);
    const h = parseInt(parts[1], 10);
    if (w > 0 && h > 0) return { width: w, height: h };
  }
  return undefined;
}

const viewportOverride = parseViewport();

module.exports = {
  testDir: './tests',
  timeout: 300000, // 5 min — multi-item screenshot tests need time for intro screens + all items
  retries: 1,
  workers: 1, // serialize — assessment server cannot handle concurrent sessions

  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
      animations: 'disabled',
    },
  },

  use: {
    baseURL: process.env.ASSESSMENT_URL || 'https://assessment.internal',
    screenshot: process.env.PW_SCREENSHOT || 'only-on-failure',
    trace: process.env.PW_TRACE || 'retain-on-failure',
    video: process.env.PW_VIDEO || 'retain-on-failure',
    ...(viewportOverride ? { viewport: viewportOverride } : {}),
  },

  projects: [
    {
      name: 'chrome-desktop',
      use: { ...devices['Desktop Chrome'], ...(viewportOverride ? { viewport: viewportOverride } : {}) },
    },
    {
      name: 'firefox-desktop',
      use: { ...devices['Desktop Firefox'], ...(viewportOverride ? { viewport: viewportOverride } : {}) },
    },
    {
      name: 'webkit-desktop',
      use: { ...devices['Desktop Safari'], ...(viewportOverride ? { viewport: viewportOverride } : {}) },
    },
  ],

  reporter: [
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/report.json' }],
    ['./src/reporters/db-reporter.js'],
  ],
};
