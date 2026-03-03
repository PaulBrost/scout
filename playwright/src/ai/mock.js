// SCOUT — Mock AI Provider
// Returns canned responses for CI/development without an AI service.
// Set MOCK_AI_MODE=clean|issues|error to control behavior.

const AIProvider = require('./provider');

class MockProvider extends AIProvider {
  constructor(config) {
    super(config);
    this.mode = config.mockAiMode || 'clean';
  }

  async analyzeText(text, language = 'English') {
    const start = Date.now();
    await this._simulateDelay();

    if (this.mode === 'error') {
      throw new Error('Mock AI error: simulated failure');
    }

    if (this.mode === 'issues') {
      return {
        issues: [
          { type: 'spelling', text: 'teh', suggestion: 'the', context: '...teh answer...' },
          { type: 'homophone', text: 'plain', suggestion: 'plane', context: '...on a plain...' },
        ],
        issuesFound: true,
        raw: 'Mock: Found 2 issues — "teh" (spelling) and "plain" vs "plane" (homophone)',
        model: 'mock',
        durationMs: Date.now() - start,
      };
    }

    // clean mode
    return {
      issues: [],
      issuesFound: false,
      raw: 'No issues detected.',
      model: 'mock',
      durationMs: Date.now() - start,
    };
  }

  async analyzeScreenshot(screenshot, context = '') {
    const start = Date.now();
    await this._simulateDelay();

    if (this.mode === 'error') {
      throw new Error('Mock AI error: simulated failure');
    }

    if (this.mode === 'issues') {
      return {
        issues: [
          { type: 'readability', detail: 'Text appears slightly blurry at bottom of page', severity: 'low' },
        ],
        issuesFound: true,
        raw: 'Mock: Found 1 issue — text readability at bottom of page',
        model: 'mock',
        durationMs: Date.now() - start,
      };
    }

    return {
      issues: [],
      issuesFound: false,
      raw: 'No visual issues detected. Text is readable, layout is intact, contrast is sufficient.',
      model: 'mock',
      durationMs: Date.now() - start,
    };
  }

  async compareText(baselineText, currentText, language = 'English') {
    const start = Date.now();
    await this._simulateDelay();

    if (this.mode === 'error') {
      throw new Error('Mock AI error: simulated failure');
    }

    const hasDiffs = baselineText !== currentText;
    if (hasDiffs && this.mode === 'issues') {
      return {
        differences: [
          { type: 'changed', baseline: 'sample baseline text', current: 'sample current text', significance: 'medium' },
        ],
        hasDifferences: true,
        raw: 'Mock: Found 1 difference between versions',
        model: 'mock',
        durationMs: Date.now() - start,
      };
    }

    return {
      differences: [],
      hasDifferences: false,
      raw: hasDiffs ? 'Texts differ but no significant content changes detected.' : 'Texts are identical.',
      model: 'mock',
      durationMs: Date.now() - start,
    };
  }

  async generateTest(description, context = {}) {
    await this._simulateDelay();

    if (this.mode === 'error') {
      throw new Error('Mock AI error: simulated failure');
    }

    return `// SCOUT — AI Generated Test (Mock)
// Description: ${description}
// Generated: ${new Date().toISOString()}

const { test, expect } = require('@playwright/test');
const { loginAndNavigate } = require('../../src/helpers/auth');
const { getItemUrl } = require('../../src/helpers/items');

test.describe('Mock Generated Test', () => {
  test('placeholder test @smoke', async ({ page }) => {
    // This is a mock-generated test. Replace with actual implementation.
    await loginAndNavigate(page, getItemUrl('001'));
    await expect(page).toHaveScreenshot('mock-test.png');
  });
});
`;
  }

  async healthCheck() {
    return {
      healthy: true,
      provider: 'mock',
      details: { mode: this.mode },
    };
  }

  async _chatCompletion(messages, options = {}) {
    await this._simulateDelay();
    if (this.mode === 'error') {
      throw new Error('Mock AI error: simulated failure');
    }
    // Look at the last user message to craft a relevant mock response
    const lastUser = messages.filter(m => m.role === 'user').pop();
    const msg = (lastUser?.content || '').toLowerCase();

    if (msg.includes('explain') || msg.includes('what does')) {
      return 'This script contains Playwright tests that automate browser interactions. It uses helper functions to log in, navigate to assessment items, and verify expected behavior through assertions and screenshot comparisons.';
    }
    if (msg.includes('modify') || msg.includes('add') || msg.includes('change') || msg.includes('fix') || msg.includes('create') || msg.includes('generate') || msg.includes('write')) {
      return '```tool\n{"tool": "update_code", "args": {"code": "// Mock AI modified code\\nconst { test, expect } = require(\'@playwright/test\');\\n\\ntest(\'mock test\', async ({ page }) => {\\n  // Modified by AI\\n  await page.goto(\'/\');\\n  await expect(page).toBeVisible();\\n});", "summary": "Generated mock test code"}}\n```\n\nI\'ve updated the code with the requested changes.';
    }
    return 'I can help you with this test script. Would you like me to explain what it does, modify it, or create something new?';
  }

  async _simulateDelay() {
    // Simulate realistic latency
    const delay = 50 + Math.random() * 100;
    await new Promise(r => setTimeout(r, delay));
  }
}

module.exports = MockProvider;
