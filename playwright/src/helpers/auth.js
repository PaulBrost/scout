// SCOUT — Authentication Helper
// Handles login and session start for the assessment application.
// Supports environment config objects (from DB) or falls back to .env values.

const fs = require('fs');
const path = require('path');
const { startTestSession, skipIntroScreens } = require('./items');

const SESSION_PATH = path.resolve(__dirname, '../../auth/session.json');

/**
 * Log in to the assessment application.
 * Supports both password-only and username+password auth.
 * 
 * @param {import('@playwright/test').Page} page
 * @param {object} options
 * @param {string} options.password - Override default password
 * @param {object} options.env - Environment config from DB (base_url, credentials, auth_type)
 */
async function login(page, options = {}) {
  const envConfig = options.env;

  // Resolve config: DB environment takes priority, then .env fallback
  var url, password, username, authType, passwordSelector, submitSelector;
  if (envConfig) {
    var creds = envConfig.credentials || {};
    url = envConfig.base_url;
    authType = envConfig.auth_type || 'password_only';
    password = options.password || creds.password || '';
    username = creds.username || '';
    passwordSelector = creds.password_selector || '#_ctl0_Body_PasswordText';
    submitSelector = creds.submit_selector || '#_ctl0_Body_SubmitButton';
  } else {
    var config = require('../config');
    url = config.assessmentUrl;
    authType = config.assessmentUsername ? 'username_password' : 'password_only';
    password = options.password || config.assessmentPassword;
    username = config.assessmentUsername || '';
    passwordSelector = '#_ctl0_Body_PasswordText';
    submitSelector = '#_ctl0_Body_SubmitButton';
  }

  if (authType !== 'none' && !password) {
    throw new Error('SCOUT: Assessment password not configured. Set ASSESSMENT_PASSWORD in .env or configure in Environments.');
  }

  await page.goto(url);

  if (authType === 'none') return;

  // Check if we were redirected to a login page
  var currentUrl = page.url();
  var onLoginPage = currentUrl.includes('login') || currentUrl.includes('Login') || currentUrl.includes('Password');
  if (!onLoginPage) return; // Already authenticated

  await page.waitForSelector(passwordSelector, { timeout: 15000 });

  if (authType === 'username_password' && username) {
    var usernameSelector = (envConfig && envConfig.credentials && envConfig.credentials.username_selector)
      || '#_ctl0_Body_UserNameText';
    try {
      await page.fill(usernameSelector, username);
    } catch (e) {
      // Fallback: try common selectors
      await page.fill('input[type="text"]', username);
    }
  }

  await page.fill(passwordSelector, password);
  await page.click(submitSelector);

  // Wait for navigation away from the login page
  await page.waitForURL(url2 => {
    var u = url2.toString();
    return !u.includes('login') && !u.includes('Login') && !u.includes('Password');
  }, { timeout: 30000 });

  // If the login redirected elsewhere (e.g. dashboard), navigate back to the target URL
  if (!page.url().startsWith(url)) {
    await page.goto(url, { waitUntil: 'domcontentloaded' });
  }
}

/**
 * Full test setup: login → select test form → skip intro screens → land on item 1.
 * 
 * @param {import('@playwright/test').Page} page
 * @param {object} options
 * @param {string} options.formKey - Test form key (default: 'cra-form1')
 * @param {boolean} options.skipIntro - Skip intro screens (default: true)
 * @param {object} options.env - Environment config from DB
 */
async function loginAndStartTest(page, options = {}) {
  const formKey = options.formKey || 'cra-form1';
  const skipIntro = options.skipIntro !== false;

  // Auto-load env config from runner if not explicitly provided
  var envConfig = options.env;
  if (!envConfig && process.env.SCOUT_ENV_CONFIG) {
    try { envConfig = JSON.parse(process.env.SCOUT_ENV_CONFIG); } catch (e) { /* ignore */ }
  }

  // Resolve URL for session check
  var checkUrl;
  if (envConfig) {
    checkUrl = envConfig.base_url;
  } else {
    var config = require('../config');
    checkUrl = config.assessmentUrl;
  }

  // Try loading saved session state first
  if (await loadSession(page)) {
    await page.goto(checkUrl, { waitUntil: 'domcontentloaded' });
    var sessionUrl = page.url();
    if (!sessionUrl.includes('Password') && !sessionUrl.includes('login') && !sessionUrl.includes('Login')) {
      await startTestSession(page, formKey, envConfig);
      if (skipIntro) await skipIntroScreens(page, undefined, envConfig);
      return;
    }
  }

  await login(page, { env: envConfig });
  await saveSession(page);
  await startTestSession(page, formKey, envConfig);
  if (skipIntro) await skipIntroScreens(page, undefined, envConfig);
}

/**
 * Save the current browser session state (cookies) for reuse.
 * @param {import('@playwright/test').Page} page
 */
async function saveSession(page) {
  try {
    const dir = path.dirname(SESSION_PATH);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const state = await page.context().storageState();
    fs.writeFileSync(SESSION_PATH, JSON.stringify(state));
  } catch (err) {
    console.warn('SCOUT: Could not save session state:', err.message);
  }
}

/**
 * Load a previously saved session state.
 * @param {import('@playwright/test').Page} page
 * @returns {boolean} true if session was loaded successfully
 */
async function loadSession(page) {
  try {
    if (!fs.existsSync(SESSION_PATH)) return false;
    const stat = fs.statSync(SESSION_PATH);
    const ageHours = (Date.now() - stat.mtimeMs) / (1000 * 60 * 60);
    if (ageHours > 4) {
      fs.unlinkSync(SESSION_PATH);
      return false;
    }
    const state = JSON.parse(fs.readFileSync(SESSION_PATH, 'utf-8'));
    await page.context().addCookies(state.cookies || []);
    return true;
  } catch {
    return false;
  }
}

module.exports = { login, loginAndStartTest, saveSession, loadSession };
