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
  'gates-student-experience-form': 'tests/Gates_form1.xml|Pure/prefs/NAEP_Gates_2025.xml',
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
  // Look up form value: static map first, then fall back to envConfig.form_value
  // (which the runner populates from the assessment's form_value DB column)
  var formValue = TEST_FORMS[formKey];
  if (!formValue && envConfig && envConfig.form_value) {
    formValue = envConfig.form_value;
  }
  if (!formValue) throw new Error('SCOUT: Unknown test form "' + formKey + '". Add it to TEST_FORMS in items.js or set form_value on the assessment.');

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
 * Handles native alert() dialogs for "must answer" validation.
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

  // Handle NAEP "must answer" alert — only dismiss dialogs about answering
  let mustAnswerFired = false;
  const dialogHandler = async (dialog) => {
    const msg = (dialog.message() || '').toLowerCase();
    if (/answer|question|before continuing|respond/.test(msg)) {
      mustAnswerFired = true;
      await dialog.accept();
    } else {
      // Not a "must answer" dialog — accept but don't trigger answer logic
      await dialog.accept();
    }
  };
  page.on('dialog', dialogHandler);

  await page.click('#nextButton');
  await page.waitForTimeout(500);

  page.off('dialog', dialogHandler);

  if (mustAnswerFired) {
    await answerAndAdvance(page);
  }
}

/**
 * Click the next button (only when enabled).
 * Handles native alert() dialogs for "must answer" validation.
 * @param {import('@playwright/test').Page} page
 */
async function clickNext(page) {
  await page.waitForSelector('#nextButton', { state: 'visible', timeout: 10000 });

  // Handle NAEP "must answer" alert — only dismiss dialogs about answering
  let mustAnswerFired = false;
  const dialogHandler = async (dialog) => {
    const msg = (dialog.message() || '').toLowerCase();
    if (/answer|question|before continuing|respond/.test(msg)) {
      mustAnswerFired = true;
      await dialog.accept();
    } else {
      await dialog.accept();
    }
  };
  page.on('dialog', dialogHandler);

  await page.click('#nextButton');
  await page.waitForTimeout(500);

  page.off('dialog', dialogHandler);

  if (mustAnswerFired) {
    await answerAndAdvance(page);
  }
}

/**
 * When a "must answer" dialog was dismissed, provide a dummy answer and retry Next.
 * Handles standard HTML inputs and NAEP custom answer elements.
 * @param {import('@playwright/test').Page} page
 */
async function answerAndAdvance(page) {
  // Provide a dummy answer — try various input types
  await page.evaluate(() => {
    // Try radio buttons (most common for NAEP routing questions)
    const radios = document.querySelectorAll('input[type="radio"]');
    if (radios.length > 0) {
      radios[0].click();
      radios[0].dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }
    // Try NAEP custom answer choice elements (divs/spans with click handlers)
    const choices = document.querySelectorAll(
      '.answerChoice, .responseOption, .answer-option, ' +
      '[role="radio"], [role="option"], [data-answer], ' +
      '.mcChoice, .mc-choice, .choiceLabel'
    );
    if (choices.length > 0) {
      choices[0].click();
      return;
    }
    // Try checkboxes
    const checks = document.querySelectorAll('input[type="checkbox"]');
    if (checks.length > 0) {
      checks[0].click();
      checks[0].dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }
    // Try select dropdowns
    const selects = document.querySelectorAll('#item select, select');
    for (const sel of selects) {
      if (sel.options.length > 1 && sel.id !== 'TheTest') {
        sel.selectedIndex = 1;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        return;
      }
    }
    // Try text inputs
    const inputs = document.querySelectorAll(
      '#item input[type="text"], #item textarea, ' +
      'input[type="text"]:not([readonly]), textarea:not([readonly])'
    );
    if (inputs.length > 0) {
      inputs[0].value = 'test';
      inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
      inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }
    // Last resort: click any clickable element inside the item content area
    const itemEl = document.getElementById('item') || document.getElementById('theItem');
    if (itemEl) {
      const clickables = itemEl.querySelectorAll(
        'a, button, [onclick], [role="button"], label, td[onclick], div[onclick]'
      );
      if (clickables.length > 0) {
        clickables[0].click();
      }
    }
  });
  await page.waitForTimeout(500);

  // Retry clicking Next (with dialog handler in case answer wasn't accepted)
  let retryDialog = false;
  const retryHandler = async (dialog) => {
    retryDialog = true;
    await dialog.accept();
  };
  page.on('dialog', retryHandler);

  await page.waitForSelector('#nextButton', { state: 'attached', timeout: 5000 });
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

  page.off('dialog', retryHandler);
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
  answerAndAdvance,
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
