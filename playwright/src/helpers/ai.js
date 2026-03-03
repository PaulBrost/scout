// SCOUT — AI Analysis Helpers
// Wraps the AI provider for use in Playwright tests.
// Handles graceful degradation when AI is unavailable.

const aiProvider = require('../ai');
const config = require('../config');

/**
 * Analyze assessment item text for spelling, grammar, and homophone issues.
 * Returns structured results suitable for test reporting.
 * 
 * @param {string} text - The extracted item text
 * @param {string} language - 'English' or 'Spanish'
 * @returns {Promise<object>} Analysis result
 */
async function analyzeItemText(text, language = 'English') {
  if (!config.aiTextEnabled) {
    return { issues: [], issuesFound: false, raw: 'AI text analysis disabled', model: 'none', durationMs: 0, skipped: true };
  }

  if (!text || text.trim().length < 10) {
    return { issues: [], issuesFound: false, raw: 'Text too short for analysis', model: 'none', durationMs: 0, skipped: true };
  }

  try {
    return await aiProvider.analyzeText(text, language);
  } catch (err) {
    console.warn(`SCOUT: AI text analysis failed — ${err.message}`);
    return {
      issues: [],
      issuesFound: false,
      raw: `AI analysis error: ${err.message}`,
      model: 'error',
      durationMs: 0,
      error: err.message,
    };
  }
}

/**
 * Analyze a screenshot for visual quality issues.
 * 
 * @param {Buffer} screenshotBuffer - PNG screenshot buffer
 * @param {string} context - Description for the AI (e.g., "Dark theme at 150% zoom")
 * @returns {Promise<object>} Vision analysis result
 */
async function analyzeItemScreenshot(screenshotBuffer, context = '') {
  if (!config.aiVisionEnabled) {
    return { issues: [], issuesFound: false, raw: 'AI vision analysis disabled', model: 'none', durationMs: 0, skipped: true };
  }

  try {
    return await aiProvider.analyzeScreenshot(screenshotBuffer, context);
  } catch (err) {
    console.warn(`SCOUT: AI vision analysis failed — ${err.message}`);
    return {
      issues: [],
      issuesFound: false,
      raw: `AI vision error: ${err.message}`,
      model: 'error',
      durationMs: 0,
      error: err.message,
    };
  }
}

/**
 * Compare text between two versions of an item.
 * 
 * @param {string} baselineText - Text from the baseline version
 * @param {string} currentText - Text from the current version
 * @param {string} language - 'English' or 'Spanish'
 * @returns {Promise<object>} Comparison result
 */
async function compareItemText(baselineText, currentText, language = 'English') {
  if (!config.aiTextEnabled) {
    return { differences: [], hasDifferences: false, raw: 'AI text analysis disabled', model: 'none', durationMs: 0, skipped: true };
  }

  try {
    return await aiProvider.compareText(baselineText, currentText, language);
  } catch (err) {
    console.warn(`SCOUT: AI text comparison failed — ${err.message}`);
    return {
      differences: [],
      hasDifferences: false,
      raw: `AI comparison error: ${err.message}`,
      model: 'error',
      durationMs: 0,
      error: err.message,
    };
  }
}

module.exports = { analyzeItemText, analyzeItemScreenshot, compareItemText };
