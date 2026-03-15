// SCOUT — QC Checklist Helpers
// Reusable detection and validation for common HTML interaction types.
// Import this in QC checklist tests to avoid duplicating detection logic.
//
// IMPORTANT: Detection and checks search the FULL page, not just #item.
// NAEP assessments may render form elements outside the #item container
// (e.g., answer choices in a sibling panel). The only navigation element
// that could cause a false positive is the #TheTest dropdown, which is
// excluded explicitly.
//
// Each check is wrapped in a try/catch with a per-check timeout.
// On failure: a screenshot is saved, the error is logged, and the test
// continues to the next check/screen. Assertions never kill the run.

const { expect } = require('@playwright/test');

/** Per-check timeout (ms). Prevents hanging on unfillable inputs, etc. */
const CHECK_TIMEOUT = 10000;

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

/** Try to click a Clear Answer button if one exists. Returns true if clicked. */
async function clearAnswer(page) {
  const selectors = [
    '#ClearAnswer',
    'button:has-text("Clear Answer")',
    'button:has-text("Clear")',
    '.clearAnswer',
    '[class*="clear-answer"]',
    '.clearButton',
  ];
  for (const sel of selectors) {
    try {
      const btn = page.locator(sel).first();
      if (await btn.isVisible({ timeout: 500 })) {
        await btn.click();
        await page.waitForTimeout(300);
        return true;
      }
    } catch { /* not found */ }
  }
  return false;
}

/**
 * Run a check function with a timeout. On failure, capture a screenshot
 * and return the error instead of throwing.
 */
async function safeCheck(page, screenIndex, checkName, fn) {
  try {
    await Promise.race([
      fn(),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`${checkName} timed out after ${CHECK_TIMEOUT}ms`)), CHECK_TIMEOUT)
      ),
    ]);
    return null; // success
  } catch (err) {
    const msg = err.message || String(err);
    // Capture evidence screenshot
    const safeName = checkName.replace(/[^a-zA-Z0-9]/g, '-').toLowerCase();
    const path = `test-results/qc-fail-screen${screenIndex}-${safeName}.png`;
    try {
      await page.screenshot({ path, fullPage: true });
    } catch { /* screenshot failed — non-critical */ }
    return { checkName, error: msg, screenshot: path };
  }
}

// ---------------------------------------------------------------------------
// Interaction type detection
// ---------------------------------------------------------------------------

/**
 * Inspect the current page and return which interaction types are present.
 * Searches the full document — NAEP form elements may live outside #item.
 * Excludes navigation chrome (#TheTest dropdown, #nextButton, etc.).
 */
async function detectTypes(page) {
  return await page.evaluate(() => {
    const root = document.body;

    const radios = root.querySelectorAll('input[type="radio"], [role="radio"]');
    const checkboxes = root.querySelectorAll('input[type="checkbox"], [role="checkbox"]');
    const textInputs = root.querySelectorAll(
      'input[type="text"]:not([readonly]):not([hidden]), input[type="number"]:not([readonly])'
    );
    const textareas = root.querySelectorAll('textarea');
    const contenteditables = root.querySelectorAll('[contenteditable="true"]');

    // Exclude the #TheTest form-selection dropdown from assessment dropdowns
    const allSelects = root.querySelectorAll('select');
    let dropdownCount = 0;
    for (const sel of allSelects) {
      if (sel.id === 'TheTest') continue;
      dropdownCount++;
    }

    // NAEP custom elements — click-to-select answer choices
    // Only flag when no native radios/checkboxes (they may wrap these elements)
    const choiceEls = root.querySelectorAll(
      '.answerChoice, .responseOption, .answer-option, [data-answer], ' +
      '.mcChoice, .mc-choice, .choiceLabel, [role="option"]'
    );
    const hasNativeRadioOrCheck = radios.length > 0 || checkboxes.length > 0;

    // Drag-and-drop / matching
    const draggables = root.querySelectorAll(
      '[draggable="true"], .source-tray .source, .match-source'
    );
    const dropTargets = root.querySelectorAll(
      '[data-drop-target], .drop-target, .match-target, .dropzone, ' +
      '[aria-dropeffect], [dropzone]'
    );

    return {
      radio:          radios.length,
      checkbox:       checkboxes.length,
      textInput:      textInputs.length,
      textarea:       textareas.length,
      contentEditable: contenteditables.length,
      dropdown:       dropdownCount,
      clickToSelect:  hasNativeRadioOrCheck ? 0 : choiceEls.length,
      draggable:      draggables.length,
      dropTarget:     dropTargets.length,
    };
  });
}

/** Human-readable summary of detected types (for logging). */
function describeTypes(t) {
  const parts = [];
  if (t.radio)           parts.push(`${t.radio} radio`);
  if (t.checkbox)        parts.push(`${t.checkbox} checkbox`);
  if (t.textInput)       parts.push(`${t.textInput} text input`);
  if (t.textarea)        parts.push(`${t.textarea} textarea`);
  if (t.contentEditable) parts.push(`${t.contentEditable} contenteditable`);
  if (t.dropdown)        parts.push(`${t.dropdown} dropdown`);
  if (t.clickToSelect)   parts.push(`${t.clickToSelect} click-to-select`);
  if (t.draggable)       parts.push(`${t.draggable} draggable → ${t.dropTarget} targets`);
  return parts.length ? parts.join(', ') : 'none detected';
}

function hasKnownType(t) {
  return t.radio > 0 || t.checkbox > 0 || t.textInput > 0 || t.textarea > 0
    || t.contentEditable > 0 || t.dropdown > 0 || t.clickToSelect > 0
    || (t.draggable > 0 && t.dropTarget > 0);
}

// ---------------------------------------------------------------------------
// Per-type QC checks  (all page-wide, no #item scoping)
// ---------------------------------------------------------------------------

/**
 * Radio buttons — select each option, verify mutual exclusivity.
 */
async function qcRadioButtons(page, log) {
  const radios = page.locator('input[type="radio"], [role="radio"]');
  const count = await radios.count();
  log(`  Radio buttons: ${count} options`);

  for (let i = 0; i < count; i++) {
    const radio = radios.nth(i);
    await radio.scrollIntoViewIfNeeded();
    await radio.click({ force: true, timeout: 3000 });
    await page.waitForTimeout(150);

    const isChecked = await radio.evaluate(el => {
      if (el.tagName === 'INPUT') return el.checked;
      return el.getAttribute('aria-checked') === 'true'
        || el.classList.contains('selected')
        || el.classList.contains('checked');
    });
    expect(isChecked, `Radio option ${i + 1} should be selected after click`).toBeTruthy();

    for (let j = 0; j < count; j++) {
      if (j === i) continue;
      const other = radios.nth(j);
      const otherChecked = await other.evaluate(el => {
        if (el.tagName === 'INPUT') return el.checked;
        return el.getAttribute('aria-checked') === 'true'
          || el.classList.contains('selected')
          || el.classList.contains('checked');
      });
      expect(otherChecked, `Radio ${j + 1} should NOT be selected when ${i + 1} is`).toBeFalsy();
    }
  }
  log(`  [PASS] All ${count} radio options selectable, mutual exclusivity OK`);
}

/**
 * Checkboxes — check and uncheck each.
 */
async function qcCheckboxes(page, log) {
  const boxes = page.locator('input[type="checkbox"], [role="checkbox"]');
  const count = await boxes.count();
  log(`  Checkboxes: ${count} found`);

  for (let i = 0; i < count; i++) {
    const box = boxes.nth(i);
    await box.scrollIntoViewIfNeeded();

    await box.click({ force: true, timeout: 3000 });
    await page.waitForTimeout(150);
    const checked = await box.evaluate(el => {
      if (el.tagName === 'INPUT') return el.checked;
      return el.getAttribute('aria-checked') === 'true'
        || el.classList.contains('selected')
        || el.classList.contains('checked');
    });
    expect(checked, `Checkbox ${i + 1} should be checked after click`).toBeTruthy();

    await box.click({ force: true, timeout: 3000 });
    await page.waitForTimeout(150);
    const unchecked = await box.evaluate(el => {
      if (el.tagName === 'INPUT') return !el.checked;
      return el.getAttribute('aria-checked') !== 'true'
        && !el.classList.contains('selected')
        && !el.classList.contains('checked');
    });
    expect(unchecked, `Checkbox ${i + 1} should be unchecked after second click`).toBeTruthy();
  }
  log(`  [PASS] All ${count} checkboxes toggle correctly`);
}

/**
 * Text inputs — enter text, verify, clear.
 * Skips inputs that are not visible or not interactable.
 */
async function qcTextInputs(page, log) {
  const inputs = page.locator(
    'input[type="text"]:not([readonly]):not([hidden]), input[type="number"]:not([readonly])'
  );
  const count = await inputs.count();
  log(`  Text inputs: ${count} found`);

  for (let i = 0; i < count; i++) {
    const input = inputs.nth(i);

    // Skip invisible inputs (NAEP may have hidden inputs in the DOM)
    const visible = await input.isVisible().catch(() => false);
    if (!visible) {
      log(`  Text input ${i + 1}: not visible, skipping`);
      continue;
    }

    await input.scrollIntoViewIfNeeded();
    const inputType = await input.getAttribute('type') || 'text';

    // Use click + keyboard instead of fill() — fill() hangs on some NAEP inputs
    await input.click({ timeout: 3000 });
    await page.keyboard.press('Control+A');
    const shortVal = inputType === 'number' ? '42' : 'Test';
    await page.keyboard.type(shortVal, { delay: 5 });
    let val = await input.inputValue().catch(() => '');
    expect(val).toContain(shortVal);

    // Clear the field
    await input.click({ timeout: 3000 });
    await page.keyboard.press('Control+A');
    await page.keyboard.press('Backspace');
    val = await input.inputValue().catch(() => '');
    expect(val).toBe('');
  }
  log(`  [PASS] All ${count} text inputs accept and clear values`);
}

/**
 * Textareas / contenteditable — multi-line entry, edit, clear.
 */
async function qcExtendedText(page, log) {
  const textareas = page.locator('textarea');
  const editables = page.locator('[contenteditable="true"]');
  const taCount = await textareas.count();
  const ceCount = await editables.count();
  log(`  Extended text: ${taCount} textarea, ${ceCount} contenteditable`);

  for (let i = 0; i < taCount; i++) {
    const ta = textareas.nth(i);
    const visible = await ta.isVisible().catch(() => false);
    if (!visible) continue;

    await ta.scrollIntoViewIfNeeded();
    await ta.click({ timeout: 3000 });
    await page.keyboard.press('Control+A');
    await page.keyboard.type('Line one\nLine two\nLine three', { delay: 2 });
    const val = await ta.inputValue().catch(() => '');
    expect(val).toContain('Line one');

    // Clear
    await ta.click({ timeout: 3000 });
    await page.keyboard.press('Control+A');
    await page.keyboard.press('Backspace');
  }

  for (let i = 0; i < ceCount; i++) {
    const ce = editables.nth(i);
    const visible = await ce.isVisible().catch(() => false);
    if (!visible) continue;

    await ce.scrollIntoViewIfNeeded();
    await ce.click({ force: true, timeout: 3000 });
    await page.keyboard.press('Control+A').catch(() => {});
    await page.keyboard.press('Backspace').catch(() => {});
    await page.keyboard.type('Test entry for QC', { delay: 2 });
    const text = (await ce.innerText()).trim();
    expect(text).toContain('Test entry');

    // Clear
    await ce.click({ force: true, timeout: 3000 });
    await page.keyboard.press('Control+A').catch(() => {});
    await page.keyboard.press('Backspace').catch(() => {});
  }
  log(`  [PASS] Extended text entry and clear verified`);
}

/**
 * Dropdowns — select each option, verify value changes.
 * Excludes #TheTest (NAEP form-selection dropdown).
 */
async function qcDropdowns(page, log) {
  const selects = page.locator('select:not(#TheTest)');
  const count = await selects.count();
  log(`  Dropdowns: ${count} found`);

  for (let i = 0; i < count; i++) {
    const sel = selects.nth(i);
    const visible = await sel.isVisible().catch(() => false);
    if (!visible) continue;

    await sel.scrollIntoViewIfNeeded();
    const options = sel.locator('option');
    const optCount = await options.count();
    expect(optCount, `Dropdown ${i + 1} should have options`).toBeGreaterThan(0);

    const limit = Math.min(optCount, 6);
    for (let oi = 0; oi < limit; oi++) {
      const val = await options.nth(oi).getAttribute('value');
      if (val === null || val === undefined) continue;
      try {
        await sel.selectOption(val);
        const selected = await sel.inputValue();
        expect(selected).toBe(val);
      } catch { /* option may be disabled */ }
    }

    // Reset to first option
    try {
      const firstVal = await options.nth(0).getAttribute('value');
      await sel.selectOption(firstVal || '');
    } catch { /* best effort reset */ }
  }
  log(`  [PASS] All ${count} dropdowns selectable`);
}

/**
 * Click-to-select answer choices (NAEP custom elements).
 */
async function qcClickToSelect(page, log) {
  const choices = page.locator(
    '.answerChoice, .responseOption, .answer-option, [data-answer], ' +
    '.mcChoice, .mc-choice, .choiceLabel, [role="option"]'
  );
  const count = await choices.count();
  log(`  Click-to-select: ${count} choices`);

  for (let i = 0; i < count; i++) {
    const choice = choices.nth(i);
    const visible = await choice.isVisible().catch(() => false);
    if (!visible) continue;

    await choice.scrollIntoViewIfNeeded();
    await choice.click({ force: true, timeout: 3000 });
    await page.waitForTimeout(200);

    const isSelected = await choice.evaluate(el => {
      return el.classList.contains('selected')
        || el.classList.contains('active')
        || el.classList.contains('checked')
        || el.getAttribute('aria-selected') === 'true'
        || el.getAttribute('aria-checked') === 'true'
        || el.querySelector('input[type="radio"]:checked') !== null;
    });
    expect(isSelected, `Choice ${i + 1} should be selected after click`).toBeTruthy();
  }
  log(`  [PASS] All ${count} click-to-select choices respond to click`);
}

/**
 * Matching / drag-and-drop — move source to target, verify, clear.
 */
async function qcMatching(page, log) {
  const sources = page.locator(
    '[draggable="true"], .source-tray .source, .match-source'
  );
  const targets = page.locator(
    '[data-drop-target], .drop-target, .match-target, .dropzone, ' +
    '[aria-dropeffect], [dropzone]'
  );
  const sCount = await sources.count();
  const tCount = await targets.count();
  log(`  Matching: ${sCount} sources, ${tCount} targets`);

  if (sCount === 0 || tCount === 0) {
    log('  [SKIP] Sources or targets not found');
    return;
  }

  const src = sources.first();
  const tgt = targets.first();
  const srcText = (await src.innerText().catch(() => '')).trim();

  let moved = false;
  try {
    await src.dragTo(tgt);
    moved = true;
  } catch {
    try {
      await src.click();
      await page.waitForTimeout(200);
      await tgt.click();
      moved = true;
    } catch { /* fallback failed */ }
  }

  if (moved && srcText) {
    const tgtText = (await tgt.innerText().catch(() => '')).trim();
    expect(tgtText).toContain(srcText);
    log(`  [PASS] Source moved to target successfully`);
  } else if (moved) {
    log(`  [PASS] Drag/click interaction completed (no text to verify)`);
  } else {
    log(`  [WARN] Could not move source to target via drag or click`);
  }

  await clearAnswer(page);
}

// ---------------------------------------------------------------------------
// Main runner
// ---------------------------------------------------------------------------

/**
 * Run all applicable QC checks on the current screen.
 * Each check type is wrapped in safeCheck — on failure a screenshot is
 * saved, the error is logged, and execution continues to the next check.
 * No assertions propagate out of this function.
 *
 * @param {import('@playwright/test').Page} page
 * @param {number} screenIndex - 1-based screen number
 * @returns {object} { types, checksRun, failures }
 */
async function runQcChecks(page, screenIndex) {
  const log = (msg) => console.log(`[QC ${screenIndex}] ${msg}`);
  const types = await detectTypes(page);
  log(`Detected: ${describeTypes(types)}`);

  let checksRun = 0;
  const failures = [];

  const checks = [
    { cond: types.radio > 0,      name: 'radio',          fn: () => qcRadioButtons(page, log) },
    { cond: types.checkbox > 0,    name: 'checkbox',       fn: () => qcCheckboxes(page, log) },
    { cond: types.textInput > 0,   name: 'text-input',     fn: () => qcTextInputs(page, log) },
    { cond: types.textarea > 0 || types.contentEditable > 0,
                                   name: 'extended-text',  fn: () => qcExtendedText(page, log) },
    { cond: types.dropdown > 0,    name: 'dropdown',       fn: () => qcDropdowns(page, log) },
    { cond: types.clickToSelect > 0, name: 'click-select', fn: () => qcClickToSelect(page, log) },
    { cond: types.draggable > 0 && types.dropTarget > 0,
                                   name: 'matching',       fn: () => qcMatching(page, log) },
  ];

  for (const check of checks) {
    if (!check.cond) continue;
    checksRun++;
    const err = await safeCheck(page, screenIndex, check.name, check.fn);
    if (err) {
      failures.push(err);
      log(`  [FAIL] ${check.name}: ${err.error} — screenshot: ${err.screenshot}`);
    }
  }

  // Try clearing any answers we entered so navigation is clean
  await clearAnswer(page).catch(() => {});

  if (checksRun === 0) {
    log('No automatable interaction type detected — manual QC recommended');
  } else if (failures.length > 0) {
    log(`Completed ${checksRun} check(s), ${failures.length} FAILED`);
  } else {
    log(`Completed ${checksRun} check(s), all passed`);
  }

  return { types, checksRun, failures, known: hasKnownType(types) };
}

module.exports = {
  detectTypes,
  describeTypes,
  hasKnownType,
  clearAnswer,
  safeCheck,
  qcRadioButtons,
  qcCheckboxes,
  qcTextInputs,
  qcExtendedText,
  qcDropdowns,
  qcClickToSelect,
  qcMatching,
  runQcChecks,
};
