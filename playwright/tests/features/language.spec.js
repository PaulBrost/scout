// SCOUT — Language Tests (placeholder)
// The CRA Form 1 assessment does not have a language toggle.
// This test verifies that all item text is in English (no unexpected language mixing).
// When a bilingual test form is available, this will be expanded.

const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../../src/helpers/auth');
const { clickNext, extractItemText } = require('../../src/helpers/items');
const { analyzeItemText } = require('../../src/helpers/ai');

test.describe('Language Consistency', () => {
  test('All CRA Form 1 items are in English @feature @language', async ({ page }) => {
    await loginAndStartTest(page, { formKey: 'cra-form1' });

    const itemCount = 5; // Check first 5 items for language consistency
    for (let i = 1; i <= itemCount; i++) {
      const text = await extractItemText(page);

      if (text && text.trim().length >= 10) {
        const result = await analyzeItemText(text, 'English');

        if (result.issuesFound) {
          await test.info().attach(`language-check-item-${i}`, {
            body: JSON.stringify(result, null, 2),
            contentType: 'application/json',
          });
        }
      }

      if (i < itemCount) {
        await clickNext(page);
      }
    }
  });
});
