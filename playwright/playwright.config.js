// SCOUT — Playwright Configuration
// Browser matrix, visual regression thresholds, and reporter setup.

const { devices } = require('@playwright/test');

module.exports = {
  testDir: './tests',
  timeout: 120000,
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
  },

  projects: [
    // Primary browser — Chromium (Google Chrome engine)
    {
      name: 'chrome-desktop',
      use: { ...devices['Desktop Chrome'] },
    },

    // Additional browsers — uncomment when needed
    // {
    //   name: 'firefox-desktop',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'chromebook',
    //   use: {
    //     browserName: 'chromium',
    //     viewport: { width: 1366, height: 768 },
    //     deviceScaleFactor: 1,
    //   },
    // },
    // {
    //   name: 'edge-desktop',
    //   use: { ...devices['Desktop Edge'], channel: 'msedge' },
    // },
    // {
    //   name: 'webkit-desktop',
    //   use: { ...devices['Desktop Safari'] },
    // },
  ],

  reporter: [
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/report.json' }],
    ['./src/reporters/db-reporter.js'],
  ],
};
