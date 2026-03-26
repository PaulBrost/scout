// SCOUT — Item Navigation & Feature Helpers
// Functions for navigating items and interacting with assessment features.
// Selectors are configurable via environment launcher_config.item_selectors.
// Defaults are mapped from discovery of rt.ets.org CRA assessment.

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

// Default selectors — can be overridden via launcher_config.item_selectors
const DEFAULT_SELECTORS = {
  next_button: '#nextButton',
  back_button: '#backButton',
  item_container: '#item',
  item_container_alt: '#theItem',
  calculator: '#CalculatorBlueGreenIcon',
  calculator_key: '#KeyEquals',
  help_button: '#helpButton',
  help_content: '#theHelpContent',
  scratchwork_button: '#scratchworkButton',
};

/**
 * Resolve a selector from launcher_config.item_selectors, falling back to default.
 */
function sel(envConfig, key) {
  if (envConfig && envConfig.launcher_config && envConfig.launcher_config.item_selectors) {
    var custom = envConfig.launcher_config.item_selectors[key];
    if (custom) return custom;
  }
  return DEFAULT_SELECTORS[key] || '';
}

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
  await page.waitForSelector(sel(envConfig, 'item_container'), { state: 'visible', timeout: 30000 });
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
    await forceClickNext(page, envConfig);
    await page.waitForTimeout(800);
  }
}

/**
 * Check for and dismiss a "must answer" modal — either a native alert() dialog
 * or a custom c3.net modal (#c4modalDialog). Returns true if one was found.
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<boolean>}
 */
async function dismissMustAnswerModal(page) {
  // Check for custom c3.net modal dialog (#c4modalDialog)
  const modalDismissed = await page.evaluate(() => {
    const modal = document.querySelector('#c4modalDialog');
    if (!modal) return 'no-element';
    const style = window.getComputedStyle(modal);
    const rect = modal.getBoundingClientRect();
    const msg = (modal.querySelector('#c4modalDialogMsgContainer') || {}).textContent || '';
    // Check if modal is visible — use getComputedStyle since offsetParent is null
    // for position:fixed elements even when visible
    if (style.display === 'none' || style.visibility === 'hidden') return 'hidden:' + style.display + '/' + style.visibility + ' msg:' + msg;
    if (rect.width === 0 && rect.height === 0) return 'zero-rect msg:' + msg;
    // Dismiss by clicking the OK button
    const okBtn = modal.querySelector('#c4modalDialogButton1');
    if (okBtn) okBtn.click();
    return true;
  });
  if (modalDismissed === true) {
    await page.waitForTimeout(500);
    return true;
  }
  return false;
}

/**
 * Click the next button, force-enabling it if disabled.
 * Handles native alert() dialogs and custom c3.net modals for "must answer" validation.
 * Useful for skipping audio checks, tutorials, and other gated screens.
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 */
async function forceClickNext(page, envConfig = null) {
  const nextSel = sel(envConfig, 'next_button');
  await page.waitForSelector(nextSel, { state: 'attached', timeout: 15000 });
  await page.evaluate((s) => {
    const btn = document.querySelector(s);
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('disabledButton');
      btn.classList.add('enabledButton');
    }
  }, nextSel);

  // Handle native "must answer" alert
  let mustAnswerFired = false;
  const dialogHandler = async (dialog) => {
    const msg = (dialog.message() || '').toLowerCase();
    if (/answer|question|before continuing|respond/.test(msg)) {
      mustAnswerFired = true;
    }
    await dialog.accept();
  };
  page.on('dialog', dialogHandler);

  await page.click(nextSel);
  await page.waitForTimeout(1000);

  page.off('dialog', dialogHandler);

  // Also check for custom c3.net modal dialog
  if (!mustAnswerFired) {
    mustAnswerFired = await dismissMustAnswerModal(page);
  }

  if (mustAnswerFired) {
    await answerAndAdvance(page, envConfig);
  }
}

/**
 * Click the next button (only when enabled).
 * Handles native alert() dialogs and custom c3.net modals for "must answer" validation.
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 */
async function clickNext(page, envConfig = null) {
  const nextSel = sel(envConfig, 'next_button');
  await page.waitForSelector(nextSel, { state: 'visible', timeout: 10000 });

  // Handle native "must answer" alert
  let mustAnswerFired = false;
  const dialogHandler = async (dialog) => {
    const msg = (dialog.message() || '').toLowerCase();
    if (/answer|question|before continuing|respond/.test(msg)) {
      mustAnswerFired = true;
    }
    await dialog.accept();
  };
  page.on('dialog', dialogHandler);

  await page.click(nextSel);
  await page.waitForTimeout(500);

  page.off('dialog', dialogHandler);

  // Also check for custom c3.net modal dialog
  if (!mustAnswerFired) {
    mustAnswerFired = await dismissMustAnswerModal(page);
  }

  if (mustAnswerFired) {
    await answerAndAdvance(page, envConfig);
  }
}

/**
 * When a "must answer" dialog was dismissed, provide a dummy answer and retry Next.
 * Handles standard HTML inputs and NAEP custom answer elements.
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 */
async function answerAndAdvance(page, envConfig = null) {
  const itemSel = sel(envConfig, 'item_container');
  const itemAltSel = sel(envConfig, 'item_container_alt');
  const nextSel = sel(envConfig, 'next_button');

  // Provide a dummy answer via page.evaluate to bypass modal overlay actionability
  // checks. Calls the c3.net framework handlers directly (clickSelect,
  // updateHistoryWCkslog) when available, falling back to DOM event dispatch.
  // Fills ALL visible input types — some screens require multiple answers.
  await page.evaluate(({ itemSel, itemAltSel }) => {
    let answered = false;

    // Try radio buttons — call clickSelect() if available (c3.net framework)
    const radios = document.querySelectorAll('input[type="radio"]');
    if (radios.length > 0) {
      const radio = radios[0];
      radio.checked = true;
      if (radio.onclick) {
        radio.onclick(new MouseEvent('click', { bubbles: true }));
      } else if (typeof clickSelect === 'function' && radio.id) {
        clickSelect(new MouseEvent('click', { bubbles: true }), radio.id);
      }
      radio.dispatchEvent(new Event('change', { bubbles: true }));
      answered = true;
    }

    // Try custom answer choice elements (includes c3.net distractorDiv/Label)
    if (!answered) {
      const choices = document.querySelectorAll(
        '.answerChoice, .responseOption, .answer-option, ' +
        '[role="radio"], [role="option"], [data-answer], ' +
        '.mcChoice, .mc-choice, .choiceLabel, ' +
        '.distractorDiv, .distractorLabel'
      );
      if (choices.length > 0) {
        // Click up to 2 choices to satisfy "select N groups" requirements
        choices[0].click();
        if (choices.length > 1) choices[1].click();
        answered = true;
      }
    }

    // Try checkboxes — select up to 2 to satisfy "select N groups" requirements.
    // Call clickSelect directly with the checkbox value (c3.net framework handler).
    const checks = document.querySelectorAll('input[type="checkbox"]');
    for (let ci = 0; ci < Math.min(checks.length, 2); ci++) {
      const cb = checks[ci];
      if (!cb.checked) {
        cb.checked = true;
        cb.dispatchEvent(new Event('change', { bubbles: true }));
        // Call c3.net clickSelect handler directly if available
        if (typeof clickSelect === 'function' && cb.value) {
          try { clickSelect(new MouseEvent('click', { bubbles: true }), cb.value); } catch (e) {}
        }
      }
      answered = true;
    }

    // Try select dropdowns
    const selects = document.querySelectorAll('select');
    for (const sel of selects) {
      if (sel.options.length > 1 && sel.id !== 'TheTest') {
        sel.selectedIndex = 1;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        answered = true;
        break;
      }
    }

    // Try textareas — call updateHistoryWCkslog() if available (c3.net framework)
    const textareas = document.querySelectorAll('textarea:not([readonly])');
    if (textareas.length > 0) {
      const ta = textareas[0];
      ta.value = 'test';
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      ta.dispatchEvent(new Event('change', { bubbles: true }));
      if (typeof updateHistoryWCkslog === 'function') {
        try { updateHistoryWCkslog(new Event('input'), ta, false, false, true); } catch (e) {}
      }
      answered = true;
    }

    // Try text inputs
    const textInputs = document.querySelectorAll('input[type="text"]:not([readonly])');
    if (textInputs.length > 0) {
      textInputs[0].value = 'test';
      textInputs[0].dispatchEvent(new Event('input', { bubbles: true }));
      textInputs[0].dispatchEvent(new Event('change', { bubbles: true }));
      answered = true;
    }

    // Last resort: click any clickable element inside the item content area
    if (!answered) {
      const itemEl = document.querySelector(itemSel) || document.querySelector(itemAltSel);
      if (itemEl) {
        const clickables = itemEl.querySelectorAll(
          'a, button, [onclick], [role="button"], label, td[onclick], div[onclick]'
        );
        if (clickables.length > 0) {
          clickables[0].click();
        }
      }
    }
  }, { itemSel, itemAltSel });
  await page.waitForTimeout(500);

  // Retry clicking Next — use force:true to bypass any brief modal overlay
  // that might intercept pointer events during the transition.
  let retryDialog = false;
  const retryHandler = async (dialog) => {
    retryDialog = true;
    await dialog.accept();
  };
  page.on('dialog', retryHandler);

  await page.waitForSelector(nextSel, { state: 'attached', timeout: 5000 });
  await page.evaluate((s) => {
    const btn = document.querySelector(s);
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('disabledButton');
      btn.classList.add('enabledButton');
    }
  }, nextSel);
  await page.click(nextSel, { force: true });
  await page.waitForTimeout(1000);

  page.off('dialog', retryHandler);

  // Dismiss custom modal if it reappeared (answer wasn't fully accepted)
  await dismissMustAnswerModal(page);
}

/**
 * Click the back button (only when enabled).
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 */
async function clickBack(page, envConfig = null) {
  await page.click(sel(envConfig, 'back_button'));
  await page.waitForTimeout(500);
}

/**
 * Navigate to a specific item number (1-indexed) from the start of the assessment.
 * Skips intro screens, then advances to the target item.
 * @param {import('@playwright/test').Page} page
 * @param {number} itemNumber - 1-indexed item number (1 = first math question)
 * @param {object} envConfig - Optional environment config from DB
 */
async function navigateToItem(page, itemNumber, envConfig = null) {
  await skipIntroScreens(page, null, envConfig);
  // Now on item 1 — advance to target
  for (let i = 1; i < itemNumber; i++) {
    await clickNext(page, envConfig);
  }
  await page.waitForSelector(sel(envConfig, 'item_container'), { state: 'visible', timeout: 10000 });
}

/**
 * Extract all visible text from the item content area.
 * Automatically emits a [SCOUT_TEXT] marker so SCOUT can detect that page text
 * was captured and use it for AI text analysis.
 * @param {import('@playwright/test').Page} page
 * @param {string} [label] - Optional label (e.g., screen number or item ID)
 * @param {object} [envConfig] - Optional environment config from DB
 * @returns {string} The item's text content
 */
async function extractItemText(page, label, envConfig = null) {
  const itemSel = sel(envConfig, 'item_container');
  const el = page.locator(itemSel);
  let text = '';
  if (await el.isVisible({ timeout: 3000 })) {
    text = await el.innerText();
  }
  if (text && text.trim()) {
    const payload = JSON.stringify({
      label: label || '',
      text: text.trim(),
    });
    console.log(`[SCOUT_TEXT] ${payload}`);
  }
  return text;
}

/**
 * Check if the next button is currently enabled.
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 * @returns {boolean}
 */
async function isNextEnabled(page, envConfig = null) {
  const nextSel = sel(envConfig, 'next_button');
  return await page.evaluate((s) => {
    const btn = document.querySelector(s);
    return btn ? !btn.disabled && !btn.classList.contains('disabledButton') : false;
  }, nextSel);
}

/**
 * Check if the back button is currently enabled.
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 * @returns {boolean}
 */
async function isBackEnabled(page, envConfig = null) {
  const backSel = sel(envConfig, 'back_button');
  return await page.evaluate((s) => {
    const btn = document.querySelector(s);
    return btn ? !btn.disabled && !btn.classList.contains('disabledButton') : false;
  }, backSel);
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
 * @param {object} envConfig - Optional environment config from DB
 * @returns {import('@playwright/test').Locator} The calculator container
 */
async function openCalculator(page, envConfig = null) {
  await page.click(sel(envConfig, 'calculator'));
  const calc = page.locator(sel(envConfig, 'calculator_key'));
  await calc.waitFor({ state: 'visible', timeout: 5000 });
  return page.locator('.CalcButton').first();
}

/**
 * Close the calculator overlay.
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 */
async function closeCalculator(page, envConfig = null) {
  await page.click(sel(envConfig, 'calculator'));
  await page.waitForTimeout(300);
}

/**
 * Open the help panel.
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 * @returns {import('@playwright/test').Locator} The help content panel
 */
async function openHelp(page, envConfig = null) {
  await page.click(sel(envConfig, 'help_button'));
  const help = page.locator(sel(envConfig, 'help_content'));
  await help.waitFor({ state: 'visible', timeout: 5000 });
  return help;
}

/**
 * Close the help panel.
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 */
async function closeHelp(page, envConfig = null) {
  await page.click(sel(envConfig, 'help_button'));
  await page.waitForTimeout(300);
}

/**
 * Open the scratchwork (drawing) tool.
 * @param {import('@playwright/test').Page} page
 * @param {object} envConfig - Optional environment config from DB
 */
async function openScratchwork(page, envConfig = null) {
  await page.click(sel(envConfig, 'scratchwork_button'));
  await page.waitForTimeout(300);
}

/**
 * If a video is present on the current screen, skip it by clicking near the end of the progress bar.
 * Uses the video_progress_selector from launcher_config. If not configured, tries common selectors.
 * @param {import('@playwright/test').Page} page
 * @param {object} launcherConfig - launcher_config from environment
 */
async function skipVideoIfPresent(page, launcherConfig = {}) {
  const selectors = [
    launcherConfig.video_progress_selector,
    'video',                          // HTML5 <video> element
    '.video-progress',                // Common progress bar class
    '[class*="progress-bar"]',        // Progress bar variations
  ].filter(Boolean);

  for (const sel of selectors) {
    try {
      const el = page.locator(sel).first();
      const isVisible = await el.isVisible({ timeout: 1000 });
      if (!isVisible) continue;

      if (sel === 'video') {
        // For HTML5 video, seek to near the end via JS
        await page.evaluate(() => {
          const video = document.querySelector('video');
          if (video && video.duration) {
            video.currentTime = video.duration - 0.5;
          }
        });
        await page.waitForTimeout(1500);
        return true;
      } else {
        // For progress bars, click near the end (95% from left)
        const box = await el.boundingBox();
        if (box && box.width > 10) {
          await page.mouse.click(box.x + box.width * 0.95, box.y + box.height / 2);
          await page.waitForTimeout(1500);
          return true;
        }
      }
    } catch {
      // Selector not found, try next
    }
  }
  return false;
}

/**
 * Navigate through ALL screens (intro + items + end) of an assessment.
 * Calls onScreen on each screen before advancing. Detects end of assessment via
 * configurable selectors or when Next cannot be clicked.
 *
 * Config read from envConfig.launcher_config:
 *   - end_indicator: CSS selector for element visible on the final screen
 *   - done_button: CSS selector for OK/Done/Finish button on end screen
 *   - video_progress_selector: CSS selector for video progress bar
 *   - max_screens: safety limit (default 100)
 *   - item_selectors.next_button: CSS selector for the Next button (default #nextButton)
 *   - item_selectors.item_container: CSS selector for the item content area (default #item)
 *   - interactive_panels: array of {buttons: [...selectors], back_button: selector}
 *       On each screen, if any of the buttons are visible, click each one in sequence,
 *       wait for content, click back_button, then repeat for the next button.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object|null} envConfig - Environment config from SCOUT_ENV_CONFIG
 * @param {function} onScreen - async callback(page, screenIndex) called on each screen
 * @returns {Promise<number>} Total number of screens visited
 */
async function navigateAllScreens(page, envConfig, onScreen) {
  const lc = (envConfig && envConfig.launcher_config) || {};
  const maxScreens = lc.max_screens || 100;
  const nextSel = sel(envConfig, 'next_button');
  const itemSel = sel(envConfig, 'item_container');
  const itemAltSel = sel(envConfig, 'item_container_alt');
  let screenIndex = 1;

  while (screenIndex <= maxScreens) {
    await page.waitForLoadState('networkidle');

    // Handle video screens — seek to end before screenshotting
    await skipVideoIfPresent(page, lc);

    // Capture page text for AI analysis (extractItemText emits [SCOUT_TEXT] automatically)
    await extractItemText(page, `Screen ${screenIndex}`, envConfig);

    // Call user's callback on this screen
    await onScreen(page, screenIndex);

    // Handle interactive panels (e.g., Buggy Islands data menu buttons)
    // Click each button, wait for content, click back, then repeat for next button
    if (lc.interactive_panels) {
      for (const panel of lc.interactive_panels) {
        // Check if the first button in the panel exists on this screen
        const firstBtn = page.locator(panel.buttons[0]);
        if (await firstBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
          process.stderr.write(`[SCOUT] Screen ${screenIndex}: interactive panel detected, cycling ${panel.buttons.length} buttons\n`);
          for (const btnSel of panel.buttons) {
            const btn = page.locator(btnSel);
            if (await btn.isVisible({ timeout: 2000 }).catch(() => false)) {
              await btn.click();
              await page.waitForTimeout(1000);
              await page.waitForLoadState('networkidle');
              // Click back button to return to the menu
              if (panel.back_button) {
                const backBtn = page.locator(panel.back_button);
                if (await backBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
                  await backBtn.click();
                  await page.waitForTimeout(1000);
                  await page.waitForLoadState('networkidle');
                }
              }
            }
          }
        }
      }
    }

    // Pre-fill any required answers BEFORE clicking Next — ensures the
    // assessment's internal validation passes on the first attempt.
    // Handle radios (click 1) and checkboxes (click up to 2) separately.
    const uncheckedRadio = page.locator('.distractorInput[type="radio"]:not(:checked)');
    if (await uncheckedRadio.count() > 0) {
      await uncheckedRadio.first().click({ force: true });
      await page.waitForTimeout(300);
    }
    const uncheckedCb = page.locator('.distractorInput[type="checkbox"]:not(:checked)');
    for (let cbi = 0; cbi < Math.min(await uncheckedCb.count(), 2); cbi++) {
      await page.locator('.distractorInput[type="checkbox"]:not(:checked)').first().click({ force: true });
      await page.waitForTimeout(300);
    }
    // Note: Do NOT click [onclick] elements pre-emptively — some assessments
    // (e.g., Buggy Islands) use expandable panels that open overlays blocking
    // navigation. The interactive_panels config handles specific button sequences.
    // Fill empty textareas
    const emptyTextareas = page.locator('textarea:not([readonly])');
    for (let ti = 0; ti < await emptyTextareas.count(); ti++) {
      const ta = emptyTextareas.nth(ti);
      const val = await ta.inputValue();
      if (!val || val.trim().length === 0) {
        await ta.fill('test');
        await page.waitForTimeout(300);
      }
    }

    // Check if we've reached the end indicator
    if (lc.end_indicator) {
      try {
        const endEl = page.locator(lc.end_indicator);
        if (await endEl.isVisible({ timeout: 1000 })) {
          // Click done/OK button if configured
          if (lc.done_button) {
            try {
              const doneBtn = page.locator(lc.done_button);
              if (await doneBtn.isVisible({ timeout: 2000 })) {
                await doneBtn.click();
                await page.waitForTimeout(500);
              }
            } catch { /* done button not found */ }
          }
          break;
        }
      } catch { /* end indicator not visible, continue */ }
    }

    // Snapshot the page text content (not innerHTML) before advancing so we can
    // detect if Next actually moved to a new screen. Using textContent avoids false
    // positives from input state changes (radio checked, textarea filled by answerAndAdvance).
    const contentBefore = await page.evaluate(({ s1, s2 }) => {
      const el = document.querySelector(s1) || document.querySelector(s2) || document.body;
      return el.innerText.substring(0, 1000);
    }, { s1: itemSel, s2: itemAltSel });

    // Try to advance — use clickNext (respects button state) for content screens
    // so the assessment's internal state machine works properly. Only fall back to
    // forceClickNext when the button is disabled (intro/audio/video gates).
    try {
      const nextExists = await page.locator(nextSel).count();
      if (nextExists === 0) break; // No next button at all — we're done

      // Check if next button is visible and not permanently hidden
      const nextVisible = await page.locator(nextSel).isVisible({ timeout: 2000 });
      if (!nextVisible) break;

      const isDisabled = await page.evaluate((s) => {
        const btn = document.querySelector(s);
        return btn ? btn.disabled || btn.classList.contains('disabledButton') : true;
      }, nextSel);

      if (isDisabled) {
        await forceClickNext(page, envConfig);
      } else {
        await clickNext(page, envConfig);
      }
    } catch {
      // Can't advance — end of assessment
      break;
    }

    // Wait for any transition, then check if the page actually changed
    await page.waitForTimeout(800);
    const contentAfter = await page.evaluate(({ s1, s2 }) => {
      const el = document.querySelector(s1) || document.querySelector(s2) || document.body;
      return el.innerText.substring(0, 1000);
    }, { s1: itemSel, s2: itemAltSel });

    if (contentBefore === contentAfter) {
      // Page didn't change with normal clickNext — try forceClickNext to bypass
      // the assessment's internal state check (e.g., "must read content" screens).
      await dismissMustAnswerModal(page);
      try {
        await forceClickNext(page, envConfig);
        await page.waitForTimeout(800);
      } catch { /* ignore */ }

      const contentRetry = await page.evaluate(({ s1, s2 }) => {
        const el = document.querySelector(s1) || document.querySelector(s2) || document.body;
        return el.innerText.substring(0, 1000);
      }, { s1: itemSel, s2: itemAltSel });
      if (contentBefore !== contentRetry) {
        screenIndex++;
        continue;
      }

      // Page still didn't change — we've reached the end of the assessment
      process.stderr.write(`[SCOUT] Screen ${screenIndex} appears to be the last screen (content unchanged after Next)\n`);
      break;
    }

    screenIndex++;
  }

  return screenIndex;
}

module.exports = {
  TEST_FORMS,
  INTRO_SCREENS,
  DEFAULT_SELECTORS,
  startTestSession,
  skipIntroScreens,
  forceClickNext,
  clickNext,
  clickBack,
  answerAndAdvance,
  navigateToItem,
  extractItemText,
  extractAndLogItemText: extractItemText,  // alias for backward compat
  isNextEnabled,
  isBackEnabled,
  setZoom,
  openCalculator,
  closeCalculator,
  openHelp,
  closeHelp,
  openScratchwork,
  skipVideoIfPresent,
  navigateAllScreens,
};
