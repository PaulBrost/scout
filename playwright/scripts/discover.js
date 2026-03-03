// SCOUT — Discovery Script v2
// Force-navigates past intro/audio screens to reach actual assessment items.

const { chromium } = require('playwright');
const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../.env') });

async function forceNext(page) {
  await page.evaluate(() => {
    const btn = document.getElementById('nextButton');
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('disabledButton');
      btn.classList.add('enabledButton');
    }
  });
  await page.click('#nextButton');
  await page.waitForTimeout(1500);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // Login
  await page.goto(process.env.ASSESSMENT_URL);
  await page.waitForSelector('#_ctl0_Body_PasswordText', { timeout: 15000 });
  await page.fill('#_ctl0_Body_PasswordText', process.env.ASSESSMENT_PASSWORD);
  await page.click('#_ctl0_Body_SubmitButton');
  await page.waitForURL(url => !url.toString().includes('Password'), { timeout: 30000 });

  // Select CRA Form 1
  await page.selectOption('#TheTest', { value: 'tests/craFY25_form1_AllBase.xml|Pure/prefs/NAEP_CRA_Sept2024.xml' });
  await page.click('input[type="submit"]');
  await page.waitForLoadState('networkidle', { timeout: 30000 });
  console.log('Test started');

  for (let screenNum = 1; screenNum <= 35; screenNum++) {
    const state = await page.evaluate(() => {
      const item = document.getElementById('item');
      const next = document.getElementById('nextButton');
      const heading = document.getElementById('headingText');
      const helpBtn = document.getElementById('helpButton');
      const calcBtn = document.getElementById('CalculatorBlueGreenIcon');
      const allBtns = [...document.querySelectorAll('button')]
        .filter(b => b.offsetWidth > 0)
        .map(b => b.id || b.textContent.trim().substring(0, 20));
      // Check for input types (radio, text, select, textarea)
      const inputs = [...document.querySelectorAll('#item input, #item select, #item textarea, #item [role="radio"], #item [role="checkbox"]')]
        .map(e => ({ tag: e.tagName, type: e.type || e.getAttribute('role'), id: e.id, name: e.name }));
      return {
        text: item ? item.innerText.substring(0, 400) : '',
        nextEnabled: next ? !next.disabled && !next.classList.contains('disabledButton') : false,
        heading: heading ? heading.innerText : '',
        helpVisible: helpBtn ? helpBtn.offsetWidth > 0 : false,
        calcVisible: calcBtn ? calcBtn.offsetWidth > 0 : false,
        visibleButtons: allBtns,
        inputs: inputs,
        hasImages: item ? item.querySelectorAll('img').length : 0,
      };
    });

    const isIntro = !state.heading && !state.helpVisible && state.inputs.length === 0;
    const label = isIntro ? '[INTRO]' : '[ITEM]';

    console.log('\n--- Screen ' + screenNum + ' ' + label + ' ---');
    console.log('Heading: "' + state.heading + '"');
    console.log('Help:', state.helpVisible, '| Calc:', state.calcVisible, '| Images:', state.hasImages);
    console.log('Buttons:', state.visibleButtons.join(', '));
    if (state.inputs.length) console.log('Inputs:', JSON.stringify(state.inputs));
    console.log('Text:', state.text.replace(/\n/g, ' ').substring(0, 250));

    await page.screenshot({
      path: path.resolve(__dirname, '../test-results/discovery-screen-' + String(screenNum).padStart(2, '0') + '.png'),
      fullPage: true,
    });

    // Force next if disabled (skip audio checks, tutorials, etc.)
    if (!state.nextEnabled) {
      console.log('  -> Force-clicking next');
    }
    try {
      await forceNext(page);
    } catch (e) {
      console.log('  -> Failed:', e.message.substring(0, 80));
      break;
    }
  }

  await browser.close();
  console.log('\nDone.');
})();
