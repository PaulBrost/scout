// SCOUT — Item Navigation & Feature Helpers
// Functions for navigating items and interacting with assessment features.
// Selectors mapped from discovery of rt.ets.org CRA assessment.

const config = require('../config');

// Available test forms — value attribute from the #TheTest dropdown
const TEST_FORMS = {
  'cra-form1': 'tests/craFY25_form1_AllBase.xml|Pure/prefs/NAEP_CRA_Sept2024.xml',
  'cra-form2': 'tests/craFY25_form2_AllVar.xml|Pure/prefs/NAEP_CRA_Sept2024.xml',
  'cra-form3': 'tests/craFY25_form3_OddVarEvenBase.xml|Pure/prefs/NAEP_CRA_Sept2024.xml',
  'cra-form4': 'tests/craFY25_form4_OddBaseEvenVar.xml|Pure/prefs/NAEP_CRA_Sept2024.xml',
  'math-fluency': 'tests/mathFluency.xml|Pure/prefs/NAEP_MF_2022.xml',
  'naep-id-4th': 'tests/naepID_4thGrade.xml|Pure/prefs/NAEP_ID_2022.xml',
  'naep-id-8th': 'tests/naepID_8thGrade.xml|Pure/prefs/NAEP_ID_2022.xml',
};

// Number of intro screens to skip before reaching actual assessment items
const INTRO_SCREENS = 5;

/**
 * Start a test session by selecting a form from the launcher dropdown.
 * Call this after login — it selects the form, submits, and waits for the test UI.
 * @param {import('@playwright/test').Page} page
 * @param {string} formKey - Key from TEST_FORMS (e.g., 'cra-form1')
 * @param {object} envConfig - Optional environment config from DB
 */
async function startTestSession(page, formKey = 'cra-form1', envConfig = null) {
  const formValue = TEST_FORMS[formKey];
  if (!formValue) throw new Error('SCOUT: Unknown test form "' + formKey + '"');

  // Resolve launcher selectors from env config or use defaults
  var launcherSelector = '#TheTest';
  var submitSelector = 'input[type="submit"]';
  if (envConfig && envConfig.launcher_config) {
    var lc = envConfig.launcher_config;
    launcherSelector = lc.launcher_selector || launcherSelector;
    submitSelector = lc.submit_selector || submitSelector;
  }

  await page.selectOption(launcherSelector, { value: formValue });
  await page.click(submitSelector);
  await page.waitForSelector('#item', { state: 'visible', timeout: 30000 });
  await page.waitForLoadState('networkidle');
}

/**
 * Skip past intro/tutorial screens to reach the first assessment item.
 * Force-enables the next button when it's disabled (audio check, video, etc.).
 * @param {import('@playwright/test').Page} page
 * @param {number} count - Number of intro screens to skip
 * @param {object} envConfig - Optional environment config from DB
 */
async function skipIntroScreens(page, count, envConfig = null) {
  var screens = count || INTRO_SCREENS;
  if (!count && envConfig && envConfig.launcher_config && envConfig.launcher_config.intro_screens != null) {
    screens = envConfig.launcher_config.intro_screens;
  }
  for (let i = 0; i < screens; i++) {
    await forceClickNext(page);
    await page.waitForTimeout(800);
  }
}

/**
 * Click the next button, force-enabling it if disabled.
 * Useful for skipping audio checks, tutorials, and other gated screens.
 * @param {import('@playwright/test').Page} page
 */
async function forceClickNext(page) {
  await page.waitForSelector('#nextButton', { state: 'attached', timeout: 15000 });
  await page.evaluate(() => {
    const btn = document.getElementById('nextButton');
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('disabledButton');
      btn.classList.add('enabledButton');
    }
  });
  await page.click('#nextButton');
  await page.waitForTimeout(500);

  // Check if a "must answer" dialog/overlay appeared
  const blocked = await page.evaluate(() => {
    const body = document.body.innerText || '';
    return /you need to answer|must answer|answer this question|before continuing/i.test(body);
  });

  if (blocked) {
    await dismissRequiredAnswer(page);
  }
}

/**
 * Click the next button (only when enabled).
 * If the assessment shows a "must answer" validation, dismiss it,
 * provide a dummy answer, and retry.
 * @param {import('@playwright/test').Page} page
 */
async function clickNext(page) {
  await page.waitForSelector('#nextButton', { state: 'visible', timeout: 10000 });
  await page.click('#nextButton');
  await page.waitForTimeout(500);

  // Check if a "must answer" dialog/overlay appeared
  const blocked = await page.evaluate(() => {
    // Look for common NAEP validation text patterns
    const body = document.body.innerText || '';
    return /you need to answer|must answer|answer this question|before continuing/i.test(body);
  });

  if (blocked) {
    await dismissRequiredAnswer(page);
  }
}

/**
 * Dismiss a "you must answer" validation screen by clicking continue/OK,
 * providing a dummy answer (first radio button, checkbox, or text input),
 * then clicking Next again.
 * @param {import('@playwright/test').Page} page
 */
async function dismissRequiredAnswer(page) {
  // 1) Dismiss the validation dialog — click any continue/OK button
  const dismissed = await page.evaluate(() => {
    // Look for buttons/links with "continue", "ok", "close" text
    const candidates = [...document.querySelectorAll('button, input[type="button"], a, .btn')];
    for (const el of candidates) {
      const text = (el.innerText || el.value || '').toLowerCase().trim();
      if (/^(continue|ok|close|go back)$/.test(text) || /continue/i.test(text)) {
        el.click();
        return true;
      }
    }
    return false;
  });
  await page.waitForTimeout(500);

  // 2) Provide a dummy answer — select first available input
  await page.evaluate(() => {
    // Try radio buttons first (most common for NAEP routing questions)
    const radios = document.querySelectorAll('#item input[type="radio"], #theItem input[type="radio"], input[type="radio"]');
    if (radios.length > 0) {
      radios[0].click();
      // Trigger change event in case the UI listens for it
      radios[0].dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }
    // Try checkboxes
    const checks = document.querySelectorAll('#item input[type="checkbox"], #theItem input[type="checkbox"]');
    if (checks.length > 0) {
      checks[0].click();
      checks[0].dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }
    // Try select dropdowns
    const selects = document.querySelectorAll('#item select, #theItem select');
    if (selects.length > 0 && selects[0].options.length > 1) {
      selects[0].selectedIndex = 1;
      selects[0].dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }
    // Try text inputs
    const inputs = document.querySelectorAll('#item input[type="text"], #item textarea, #theItem input[type="text"], #theItem textarea');
    if (inputs.length > 0) {
      inputs[0].value = 'test';
      inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
      return;
    }
  });
  await page.waitForTimeout(300);

  // 3) Retry clicking Next
  await page.waitForSelector('#nextButton', { state: 'visible', timeout: 5000 });
  await page.click('#nextButton');
  await page.waitForTimeout(500);
}

/**
 * Click the back button (only when enabled).
 * @param {import('@playwright/test').Page} page
 */
async function clickBack(page) {
  await page.click('#backButton');
  await page.waitForTimeout(500);
}

/**
 * Navigate to a specific item number (1-indexed) from the start of the assessment.
 * Skips intro screens, then advances to the target item.
 * @param {import('@playwright/test').Page} page
 * @param {number} itemNumber - 1-indexed item number (1 = first math question)
 */
async function navigateToItem(page, itemNumber) {
  await skipIntroScreens(page);
  // Now on item 1 — advance to target
  for (let i = 1; i < itemNumber; i++) {
    await clickNext(page);
  }
  await page.waitForSelector('#item', { state: 'visible', timeout: 10000 });
}

/**
 * Extract all visible text from the item content area.
 * @param {import('@playwright/test').Page} page
 * @returns {string} The item's text content
 */
async function extractItemText(page) {
  const el = page.locator('#item');
  if (await el.isVisible({ timeout: 3000 })) {
    return await el.innerText();
  }
  return '';
}

/**
 * Check if the next button is currently enabled.
 * @param {import('@playwright/test').Page} page
 * @returns {boolean}
 */
async function isNextEnabled(page) {
  return await page.evaluate(() => {
    const btn = document.getElementById('nextButton');
    return btn ? !btn.disabled && !btn.classList.contains('disabledButton') : false;
  });
}

/**
 * Check if the back button is currently enabled.
 * @param {import('@playwright/test').Page} page
 * @returns {boolean}
 */
async function isBackEnabled(page) {
  return await page.evaluate(() => {
    const btn = document.getElementById('backButton');
    return btn ? !btn.disabled && !btn.classList.contains('disabledButton') : false;
  });
}

/**
 * Set the browser zoom level via CSS zoom (no native zoom control on this assessment).
 * @param {import('@playwright/test').Page} page
 * @param {number} percent - Zoom level (50, 100, 150, 200)
 */
async function setZoom(page, percent) {
  await page.evaluate((level) => {
    document.body.style.zoom = (level / 100).toString();
  }, percent);
  await page.waitForTimeout(500);
}

/**
 * Open the calculator overlay.
 * @param {import('@playwright/test').Page} page
 * @returns {import('@playwright/test').Locator} The calculator container
 */
async function openCalculator(page) {
  await page.click('#CalculatorBlueGreenIcon');
  // Calculator keys are inside the page (not a separate panel), check for visibility
  const calc = page.locator('#KeyEquals');
  await calc.waitFor({ state: 'visible', timeout: 5000 });
  return page.locator('.CalcButton').first();
}

/**
 * Close the calculator overlay.
 * @param {import('@playwright/test').Page} page
 */
async function closeCalculator(page) {
  await page.click('#CalculatorBlueGreenIcon');
  await page.waitForTimeout(300);
}

/**
 * Open the help panel.
 * @param {import('@playwright/test').Page} page
 * @returns {import('@playwright/test').Locator} The help content panel
 */
async function openHelp(page) {
  await page.click('#helpButton');
  const help = page.locator('#theHelpContent');
  await help.waitFor({ state: 'visible', timeout: 5000 });
  return help;
}

/**
 * Close the help panel.
 * @param {import('@playwright/test').Page} page
 */
async function closeHelp(page) {
  await page.click('#helpButton');
  await page.waitForTimeout(300);
}

/**
 * Open the scratchwork (drawing) tool.
 * @param {import('@playwright/test').Page} page
 */
async function openScratchwork(page) {
  await page.click('#scratchworkButton');
  await page.waitForTimeout(300);
}

module.exports = {
  TEST_FORMS,
  INTRO_SCREENS,
  startTestSession,
  skipIntroScreens,
  forceClickNext,
  clickNext,
  clickBack,
  dismissRequiredAnswer,
  navigateToItem,
  extractItemText,
  isNextEnabled,
  isBackEnabled,
  setZoom,
  openCalculator,
  closeCalculator,
  openHelp,
  closeHelp,
  openScratchwork,
};
