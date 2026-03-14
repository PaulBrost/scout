import time
import random
from .provider import BaseProvider


class MockProvider(BaseProvider):
    def __init__(self, config):
        self.mode = config.get('mockAiMode', 'clean')

    def _delay(self):
        time.sleep(0.05 + random.random() * 0.1)

    def analyze_text(self, text, language='English'):
        start = time.time()
        self._delay()
        if self.mode == 'error':
            raise Exception('Mock AI error: simulated failure')
        if self.mode == 'issues':
            issues = [
                {'type': 'spelling', 'text': 'teh', 'suggestion': 'the', 'context': '...teh answer...'},
                {'type': 'homophone', 'text': 'plain', 'suggestion': 'plane', 'context': '...on a plain...'},
            ]
            return {'issues': issues, 'issuesFound': True, 'raw': 'Mock: 2 issues', 'model': 'mock',
                    'durationMs': int((time.time() - start) * 1000)}
        return {'issues': [], 'issuesFound': False, 'raw': 'No issues.', 'model': 'mock',
                'durationMs': int((time.time() - start) * 1000)}

    def analyze_screenshot(self, screenshot_b64, context=''):
        start = time.time()
        self._delay()
        if self.mode == 'error':
            raise Exception('Mock AI error: simulated failure')
        if self.mode == 'issues':
            issues = [{'type': 'readability', 'detail': 'Text slightly blurry', 'severity': 'low'}]
            return {'issues': issues, 'issuesFound': True, 'raw': 'Mock: 1 issue', 'model': 'mock',
                    'durationMs': int((time.time() - start) * 1000)}
        return {'issues': [], 'issuesFound': False, 'raw': 'No visual issues.', 'model': 'mock',
                'durationMs': int((time.time() - start) * 1000)}

    def compare_text(self, baseline, current, language='English'):
        start = time.time()
        self._delay()
        if self.mode == 'error':
            raise Exception('Mock AI error: simulated failure')
        has_diffs = baseline != current
        if has_diffs and self.mode == 'issues':
            diffs = [{'type': 'changed', 'baseline': 'sample baseline', 'current': 'sample current', 'significance': 'medium'}]
            return {'differences': diffs, 'hasDifferences': True, 'raw': 'Mock: 1 diff', 'model': 'mock',
                    'durationMs': int((time.time() - start) * 1000)}
        return {'differences': [], 'hasDifferences': False, 'raw': 'Texts identical.', 'model': 'mock',
                'durationMs': int((time.time() - start) * 1000)}

    def generate_test(self, description, context=None):
        self._delay()
        if self.mode == 'error':
            raise Exception('Mock AI error: simulated failure')
        return f"""// SCOUT — AI Generated Test (Mock)
// Description: {description}
const {{ test, expect }} = require('@playwright/test');
const {{ loginAndNavigate }} = require('../../src/helpers/auth');

test.describe('Mock Generated Test', () => {{
  test('placeholder test @smoke', async ({{ page }}) => {{
    await loginAndNavigate(page, '/items/001');
    await page.screenshot({{ path: 'test-results/mock-test.png', fullPage: true }});
  }});
}});
"""

    def health_check(self):
        return {'healthy': True, 'provider': 'mock', 'details': {'mode': self.mode}}

    def chat_completion(self, messages, options=None):
        self._delay()
        if self.mode == 'error':
            raise Exception('Mock AI error: simulated failure')
        last_user = next((m for m in reversed(messages) if m['role'] == 'user'), None)
        msg = (last_user.get('content', '') if last_user else '').lower()

        if any(w in msg for w in ['explain', 'what does', 'how does']):
            return 'This script contains Playwright tests that automate browser interactions for NAEP assessments.'
        if any(w in msg for w in ['modify', 'add', 'change', 'fix', 'create', 'generate', 'write']):
            return ('```tool\n{"tool": "update_code", "args": {"code": "// Mock AI modified code\\n'
                    "const { test, expect } = require('@playwright/test');\\n\\n"
                    "test('mock test', async ({ page }) => {\\n  await page.goto('/');\\n});", '"summary": "Generated mock test"}}\n```\n\nI\'ve updated the code.')
        return 'I can help you with this test script. Would you like me to explain, modify, or create something new?'
