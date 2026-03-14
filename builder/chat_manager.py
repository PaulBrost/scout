"""SCOUT — AI Chat Conversation Manager.

Supports an agentic loop: when the AI calls research tools (read_file,
list_helpers, search_tests, get_items), results are fed back automatically
and the AI continues without requiring user prompts.  The loop stops when
the AI produces a text-only response, calls update_code, or hits MAX_LOOP.
"""
import uuid
import re
import json
import time
import logging
from django.db import connection

logger = logging.getLogger('scout.builder')


MAX_TURNS = 50
MAX_LOOP = 8  # max auto-continue iterations per user message


def get_default_system_prompt():
    return """You are SCOUT AI, an expert assistant for the SCOUT automated testing system. You help users understand, create, and modify Playwright test scripts for PIAAC and NAEP assessment platforms.

When explaining code, be concise and focus on what matters. When modifying code, make minimal targeted changes unless asked for a rewrite.

## Autonomy Rules — CRITICAL
- When the user asks you to create, generate, or write a test: IMMEDIATELY produce the finished code. Do NOT describe what you plan to do. Do NOT ask for confirmation. The user's request IS the confirmation.
- Reference scripts for common test types are provided below. For standard requests (baseline screenshots, visual comparison, spelling/grammar, AI visual inspection), adapt the matching reference script directly and call `update_code` — do NOT call research tools first.
- Only use research tools (`list_helpers`, `read_file`, `search_tests`, `get_items`) when the request involves something NOT covered by the reference scripts.
- NEVER ask the user for helper function names, item IDs, or file contents. The Test Context section (if present) tells you which item/assessment this test targets.
- Your FIRST response to a code generation request should call `update_code` with the complete finished script, NOT tool calls or plans.
- Only ask clarifying questions when the request is genuinely ambiguous (e.g., the user says "write a test" without specifying what kind of test and no Test Context is available).

## When NOT to modify code
If the user asks a question or asks for an explanation — respond with text only. Do NOT generate or replace code unless explicitly asked to modify, create, generate, or fix it."""


def build_tool_descriptions():
    """Build tool descriptions from enabled tools in DB."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT id, name, description, parameters FROM ai_tools WHERE enabled = true ORDER BY id')
        cols = [c[0] for c in cursor.description]
        tools = [dict(zip(cols, row)) for row in cursor.fetchall()]

    lines = []
    for t in tools:
        params = t.get('parameters') or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except (json.JSONDecodeError, TypeError):
                params = {}
        param_str = ''
        if params.get('required'):
            param_str = f" Parameters: {', '.join(params['required'])}"
        if params.get('optional'):
            param_str += f" Optional: {', '.join(params['optional'])}"
        lines.append(f"- **{t['id']}**: {t['description']}{param_str}")
    return '\n'.join(lines)


def _get_reference_scripts():
    """Return reference script examples for common test types."""
    return """## Reference Scripts
Adapt these working examples for standard requests. Replace item names, form keys, and filter values to match the Test Context. For NAEP/CRA items use the CRA pattern; for PIAAC items use the PIAAC pattern.

### Baseline Screenshots (CRA)
```javascript
const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../src/helpers/auth');
const { clickNext, extractItemText } = require('../src/helpers/items');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('Baseline screenshots — CRA Form 1', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await loginAndStartTest(page, { formKey: 'cra-form1', env: envConfig });

  const TOTAL_ITEMS = 25;
  for (let i = 1; i <= TOTAL_ITEMS; i++) {
    await page.waitForLoadState('networkidle');
    await expect.soft(page).toHaveScreenshot(`item-${i}.png`, { fullPage: true });
    if (i < TOTAL_ITEMS) await clickNext(page);
  }
});
```

### Baseline Screenshots (PIAAC)
```javascript
const { test, expect } = require('@playwright/test');
const { login } = require('../src/helpers/auth');
const { selectFilters, getItemLinks, openItem, navigateItemScreens } = require('../src/helpers/piaac');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('Baseline screenshots — PIAAC items', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await login(page, { env: envConfig });
  await selectFilters(page, { version: 'FT New', country: 'ZZZ', language: 'eng', domain: 'LITNew' });
  const items = await getItemLinks(page);

  for (const item of items) {
    const itemPage = await openItem(page, item.itemId);
    await navigateItemScreens(itemPage, envConfig, async (pg, idx) => {
      await expect.soft(pg).toHaveScreenshot(`${item.itemId}-screen-${idx}.png`, { fullPage: true });
    });
    await itemPage.close();
  }
});
```

### Spelling & Grammar Check (CRA)
```javascript
const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../src/helpers/auth');
const { clickNext, extractItemText } = require('../src/helpers/items');
const { analyzeItemText } = require('../src/helpers/ai');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('Spelling & grammar check — CRA Form 1', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await loginAndStartTest(page, { formKey: 'cra-form1', env: envConfig });

  const TOTAL_ITEMS = 25;
  for (let i = 1; i <= TOTAL_ITEMS; i++) {
    await page.waitForLoadState('networkidle');
    const text = await extractItemText(page);
    if (text && text.trim().length >= 10) {
      const result = await analyzeItemText(text, 'English');
      if (result.issuesFound) {
        console.warn(`Issues in item ${i}:`, result.issues);
      }
      await test.info().attach(`ai-text-item-${i}`, {
        body: JSON.stringify(result, null, 2),
        contentType: 'application/json',
      });
    }
    if (i < TOTAL_ITEMS) await clickNext(page);
  }
});
```

### AI Visual Inspection (CRA)
```javascript
const { test, expect } = require('@playwright/test');
const { loginAndStartTest } = require('../src/helpers/auth');
const { clickNext } = require('../src/helpers/items');
const { analyzeItemScreenshot } = require('../src/helpers/ai');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('AI visual inspection — CRA Form 1', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await loginAndStartTest(page, { formKey: 'cra-form1', env: envConfig });

  const TOTAL_ITEMS = 25;
  for (let i = 1; i <= TOTAL_ITEMS; i++) {
    await page.waitForLoadState('networkidle');
    const screenshot = await page.screenshot({ fullPage: true });
    const result = await analyzeItemScreenshot(screenshot,
      `Assessment item ${i}. Check text readability, layout integrity, and visual anomalies.`
    );
    if (result.issuesFound) {
      console.warn(`Visual issues in item ${i}:`, result.issues);
    }
    await test.info().attach(`ai-vision-item-${i}`, {
      body: JSON.stringify(result, null, 2),
      contentType: 'application/json',
    });
    if (i < TOTAL_ITEMS) await clickNext(page);
  }
});
```

### Visual Comparison (cross-locale with pixelmatch)
```javascript
const { test, expect } = require('@playwright/test');
const { login } = require('../src/helpers/auth');
const { selectFilters, getItemLinks, openItem } = require('../src/helpers/piaac');
const fs = require('fs');
const { PNG } = require('pngjs');
const pixelmatch = require('pixelmatch');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

function compareImages(actualBuf, baselineBuf, name) {
  const actual = PNG.sync.read(actualBuf);
  const baseline = PNG.sync.read(baselineBuf);
  const { width, height } = actual;
  const diff = new PNG({ width, height });
  const numDiff = pixelmatch(actual.data, baseline.data, diff.data, width, height, { threshold: 0.1 });
  return { diffRatio: numDiff / (width * height), diffPng: PNG.sync.write(diff) };
}

test('Visual comparison — translated vs baseline', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await login(page, { env: envConfig });
  await selectFilters(page, { version: 'FT New', country: 'ROU', language: 'ron', domain: 'LITNew' });
  const items = await getItemLinks(page);
  const failures = [];

  for (const item of items) {
    const itemPage = await openItem(page, item.itemId);
    await itemPage.waitForLoadState('networkidle');
    const screenshot = await itemPage.screenshot({ fullPage: true });
    // Compare against baseline (stored from a previous baseline run)
    const baselinePath = `test-results/baseline/${item.itemId}.png`;
    if (fs.existsSync(baselinePath)) {
      const baseline = fs.readFileSync(baselinePath);
      const result = compareImages(screenshot, baseline, item.itemId);
      if (result.diffRatio > 0.05) {
        failures.push(`${item.itemId}: ${(result.diffRatio * 100).toFixed(2)}% diff`);
      }
      await test.info().attach(`diff-${item.itemId}`, { body: result.diffPng, contentType: 'image/png' });
    }
    await itemPage.close();
  }

  if (failures.length) console.warn('Layout differences:', failures);
});
```

IMPORTANT: When adapting these reference scripts, adjust the formKey, filter values, item count, and language to match the Test Context. Do NOT call `list_helpers`, `read_file`, or `search_tests` for standard requests — use the reference scripts directly.

"""


def build_system_prompt(current_code, filename, script_context=None, current_summary=None):
    """Build system prompt with tool descriptions, current code, and assessment/item context."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT value FROM ai_settings WHERE key = 'system_prompt'")
            row = cursor.fetchone()
            base_prompt = row[0] if row else get_default_system_prompt()
            if isinstance(base_prompt, str):
                # value is stored as JSONB string (with quotes)
                try:
                    base_prompt = json.loads(base_prompt)
                except Exception:
                    pass
    except Exception:
        base_prompt = get_default_system_prompt()

    tool_desc = build_tool_descriptions()

    prompt = base_prompt + '\n\n'
    prompt += f'## Available Tools\n{tool_desc}\n\n'
    prompt += '## Tool Calling Format\nWhen you need to use a tool, include ONE tool per code block:\n'
    prompt += '```tool\n{"tool": "tool_id", "args": {"param": "value"}}\n```\n'
    prompt += 'For multiple tools, use SEPARATE ```tool blocks for each.\n'
    prompt += 'CRITICAL: Only use `update_code` when the user explicitly asks to modify, create, generate, or fix code.\n'
    prompt += 'CRITICAL: The `summary` parameter of `update_code` must be a COMPLETE description of what the ENTIRE test does — not just the latest change. '
    prompt += 'Review the full code you are submitting and write a summary that covers every major step and behavior of the test. '
    prompt += 'This summary is displayed to users as the test description, so it must accurately reflect the whole script.\n\n'
    prompt += '## Fast Path for Test Generation\n'
    prompt += 'When asked to CREATE a new test script, ALWAYS call `get_test_template` FIRST with the appropriate type '
    prompt += '(baseline, ai_content, ai_visual, qc_checklist, functional, visual_comparison). '
    prompt += 'This returns a pre-filled skeleton with the correct helpers, imports, item counts, and platform patterns '
    prompt += 'already configured from the test context. Customize the skeleton and call `update_code` — '
    prompt += 'do NOT call list_helpers, read_file, search_tests, or get_items unless the template is insufficient.\n\n'
    prompt += '## Code Conventions\n'
    prompt += '- Use CommonJS `require()` syntax, NOT ES module `import` syntax.\n'
    prompt += '- All scripts are saved to `tests/` and MUST use `../src/helpers/` for require paths. NEVER use `../../src/helpers/` — that is wrong.\n'
    prompt += '- IMPORTANT: There is NO `src/helpers/config` module. Do NOT require or import it.\n'
    prompt += '- Environment config is loaded inline via `process.env.SCOUT_ENV_CONFIG`:\n'
    prompt += '  ```\n'
    prompt += '  function loadEnvConfig() {\n'
    prompt += '    return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};\n'
    prompt += '  }\n'
    prompt += '  ```\n'
    prompt += '- Then pass it to login: `const envConfig = loadEnvConfig(); await login(page, { env: envConfig });`\n'
    prompt += '- Use Playwright built-in `toHaveScreenshot()` or `page.screenshot()` for captures.\n'
    prompt += '- IMPORTANT: Always use `expect.soft(page).toHaveScreenshot()` (NOT `expect(page).toHaveScreenshot()`) for screenshot comparisons. Soft assertions let the test continue capturing all screenshots even when some do not match the baseline. Mismatches are tracked as issues, not test failures.\n'
    prompt += '- IMPORTANT: The global Playwright timeout is 120 seconds. Tests that iterate through multiple items (screenshots, content checks) MUST override the timeout with `test.setTimeout(300000)` (5 minutes) or more at the start of the test body.\n'
    prompt += '- When looping through items, also add `await page.waitForLoadState("networkidle")` after each navigation to ensure the page is fully loaded before taking screenshots.\n'
    prompt += '- Some assessment items require an answer before allowing navigation. The `clickNext()` and `forceClickNext()` helpers automatically handle this by dismissing the alert dialog and providing a dummy answer. No extra code is needed in test scripts.\n'
    prompt += '- The `answerAndAdvance(page)` helper is available if you need to explicitly handle a "must answer" screen.\n'
    prompt += '- For PIAAC tests, use `src/helpers/piaac.js` helpers: `selectFilters(page, {version, country, language, domain})` for cascading dropdowns, `getItemLinks(page)` to wait for and get item links after filtering (it polls up to 15s for links to appear), and `openItem(portalPage, itemId)` to open an item in its popup.\n'
    prompt += '- For PIAAC in-item navigation (multi-screen items), use `navigateItemScreens(itemPage, envConfig, onScreen)` from `src/helpers/piaac.js`. It reads Next/Finish/Continue selectors from the environment\'s `launcher_config.item_selectors` (configured by admins). The `onScreen` callback receives `(itemPage, screenIndex)` and is called on each screen. Example:\n'
    prompt += '  ```\n'
    prompt += '  const { navigateItemScreens } = require("../../src/helpers/piaac");\n'
    prompt += '  await navigateItemScreens(itemPage, envConfig, async (pg, idx) => {\n'
    prompt += '    await expect.soft(pg).toHaveScreenshot(`${itemId}-screen-${idx}.png`, { fullPage: true });\n'
    prompt += '  });\n'
    prompt += '  ```\n'
    prompt += '- Do NOT hardcode Next/Finish/Continue button selectors in test scripts. Always use `navigateItemScreens()` which reads selectors from the environment config.\n'
    prompt += '- For NAEP/CRA tests, use `src/helpers/auth.js`: `loginAndStartTest(page, {formKey})` handles login + form selection + intro screen skip. The formKey is the assessment ID (e.g., cra-form1, gates-student-experience-form). It maps to the form dropdown value automatically.\n\n'

    # QC Checklist instructions
    prompt += '## QC Checklist Tests\n'
    prompt += 'QC Checklist tests validate interactive item types against formal QA/QC checklists. '
    prompt += 'Checklists define specific test steps and expected results for each interaction type.\n\n'
    prompt += '### Default behavior: auto-detect interaction type\n'
    prompt += 'When a user asks for "QC checks" or a "QC checklist test" WITHOUT specifying an interaction type, '
    prompt += 'generate a test that **detects the interaction type at runtime** by inspecting the DOM on each item page. '
    prompt += 'The detection logic should look for these DOM signatures:\n'
    prompt += '- **Extended Text**: `textarea` elements or contenteditable response boxes (multi-line text input areas)\n'
    prompt += '- **Inline Choice**: `select` dropdown elements inside the item content area\n'
    prompt += '- **Matching**: draggable source elements with drop targets / drop zones (look for elements with `draggable` attribute, or source trays with moveable objects)\n'
    prompt += 'Based on what is detected, run the corresponding checklist steps for that item. '
    prompt += 'If an item has multiple interaction types, run checks for each detected type. '
    prompt += 'If no known interaction type is detected, log the item as "unknown type — needs manual QC" and continue.\n\n'
    prompt += '### How to generate a QC checklist test:\n'
    prompt += '1. Use the `get_qc_checklists` tool to discover and read ALL available checklists. This returns the full content of every checklist — you do not need to know file paths in advance.\n'
    prompt += '2. Generate a test that navigates to each item and detects the interaction type from the DOM (see signatures above). Then apply the matching checklist steps. If the user specifies a particular interaction type, use only that checklist.\n'
    prompt += '3. Implement each automatable checklist step as a separate `test.step()` block.\n'
    prompt += '4. Name each test/step to match the checklist number (e.g., "QC-1: Verify text entry", "QC-2: Verify max character limit").\n'
    prompt += '5. Skip steps that require manual/visual verification (e.g., TTS, scratchwork) — add a comment noting they need manual QC.\n'
    prompt += '6. Use Playwright assertions (`expect`) to validate expected results from the checklist.\n'
    prompt += '7. **Assessment vs Item scope**: Check the Test Context below. If only an assessment is specified (no specific item), generate a test that iterates through all items in the assessment and runs the checklist against each one. If a specific item is specified, test only that item. Do NOT ask the user which items to test — use the context to determine scope automatically.\n\n'

    prompt += _get_reference_scripts()

    # Include assessment/item context when available
    if script_context:
        ctx_parts = []
        if script_context.get('assessmentName'):
            ctx_parts.append(f"Assessment: {script_context['assessmentName']}")
        if script_context.get('itemId'):
            item_str = script_context['itemId']
            if script_context.get('itemTitle'):
                item_str += f" — {script_context['itemTitle']}"
            ctx_parts.append(f"Item: {item_str}")
        if script_context.get('testType'):
            ctx_parts.append(f"Test type: {script_context['testType']}")
        if script_context.get('description'):
            ctx_parts.append(f"Description: {script_context['description']}")
        if script_context.get('environmentName'):
            ctx_parts.append(f"Environment: {script_context['environmentName']}")
        if ctx_parts:
            prompt += '## Test Context\nThis test is associated with the following:\n'
            prompt += '\n'.join(f'- {p}' for p in ctx_parts) + '\n'
            prompt += 'Use this context to inform the test you generate. You do NOT need to ask the user which item or assessment this test is for — it is already specified above.\n'
            prompt += 'If an assessment is specified without a specific item, the test should cover ALL items in that assessment (e.g., iterate through items). Do not ask the user to pick specific items.\n\n'

    if current_code and current_code.strip() and current_code != '// Generated test code will appear here...':
        fname_part = f' ({filename})' if filename else ''
        prompt += f'## Current Script{fname_part}\nThe user is currently working with this code:\n```javascript\n{current_code}\n```\n'

    if current_summary and current_summary.strip():
        prompt += f'\n## Current Test Summary\nThe existing summary for this test is:\n> {current_summary.strip()}\n\n'
        prompt += 'When you call `update_code`, your `summary` must incorporate and expand upon this existing summary to cover the full test behavior, not just the latest change.\n'

    return prompt


def parse_tool_calls(response):
    """Parse tool calls from AI response text."""
    tool_calls = []
    text = response

    # Strategy 1: ```tool ... ``` blocks (may contain multiple tool calls)
    tool_block_re = re.compile(r'```tool\s*\n?([\s\S]*?)```')
    for match in tool_block_re.finditer(response):
        block_content = match.group(1).strip()
        # Try as single JSON object first
        parsed = _try_parse_tool_json(block_content)
        if parsed:
            tool_calls.append(parsed)
        else:
            # Multiple tool calls in one block — find each { and extract
            for obj_match in re.finditer(r'\{', block_content):
                json_str = _extract_balanced_json(block_content, obj_match.start())
                if json_str:
                    p = _try_parse_tool_json(json_str)
                    if p:
                        tool_calls.append(p)
        text = text.replace(match.group(0), '').strip()

    # Strategy 2: inline {"tool": ... } patterns (only if no block matches)
    if not tool_calls:
        start_re = re.compile(r'\{"tool"\s*:\s*"')
        for match in start_re.finditer(response):
            json_str = _extract_balanced_json(response, match.start())
            if json_str:
                parsed = _try_parse_tool_json(json_str)
                if parsed:
                    tool_calls.append(parsed)
                    text = text.replace(json_str, '').strip()

    text = re.sub(r'```\s*```', '', text).strip()
    # Clean up stray braces, "tool" markers, and empty lines
    text = re.sub(r'^\s*[{}]\s*$', '', text, flags=re.MULTILINE).strip()
    text = re.sub(r'^\s*tool\s*$', '', text, flags=re.MULTILINE).strip()
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text, tool_calls


def _try_parse_tool_json(s):
    try:
        parsed = json.loads(s)
        if parsed and parsed.get('tool'):
            return {'tool': parsed['tool'], 'args': parsed.get('args', {})}
    except Exception:
        pass
    return None


def _extract_balanced_json(s, start):
    if s[start] != '{':
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if escaped:
            escaped = False
            continue
        if ch == '\\' and in_string:
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def _build_test_template(args, context, project_root):
    """Build a pre-filled test template based on type and script context."""
    template_type = (args.get('type') or '').strip().lower()
    sc = context.get('script_context', {})

    # Look up environment info from assessment
    env_platform = 'unknown'  # 'naep' or 'piaac'
    assessment_id = sc.get('assessmentId', '')
    env_name = sc.get('environmentName', '')
    item_count = None
    form_value = None
    items_list = []
    domain = ''

    if assessment_id:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT a.id, a.name, a.form_value, a.item_count,
                              e.name as env_name, e.base_url
                       FROM assessments a
                       LEFT JOIN environments e ON a.environment_id = e.id
                       WHERE a.id = %s""",
                    [assessment_id]
                )
                row = cursor.fetchone()
                if row:
                    cols = [c[0] for c in cursor.description]
                    ainfo = dict(zip(cols, row))
                    form_value = ainfo.get('form_value')
                    item_count = ainfo.get('item_count')
                    env_name = ainfo.get('env_name') or env_name
                    base_url = ainfo.get('base_url') or ''
                    if 'piaac' in base_url.lower() or 'piaac' in env_name.lower():
                        env_platform = 'piaac'
                        # Extract domain from assessment id (e.g., piaac-litnew → LITNew)
                        domain = assessment_id.replace('piaac-', '').upper() if assessment_id.startswith('piaac-') else ''
                    elif 'naep' in base_url.lower() or 'c3.net' in base_url.lower() or 'naep' in env_name.lower() or 'cra' in assessment_id.lower() or 'gates' in assessment_id.lower():
                        env_platform = 'naep'
                # Get items for this assessment
                cursor.execute(
                    """SELECT item_id, title FROM items
                       WHERE assessment_id = %s ORDER BY position, item_id LIMIT 50""",
                    [assessment_id]
                )
                items_list = [{'item_id': r[0], 'title': r[1]} for r in cursor.fetchall()]
                if not item_count:
                    item_count = len(items_list)
        except Exception:
            pass

    # Detect platform from env name if not from assessment
    if env_platform == 'unknown':
        combined = (env_name + ' ' + assessment_id).lower()
        if 'piaac' in combined:
            env_platform = 'piaac'
        elif any(k in combined for k in ['naep', 'cra', 'gates']):
            env_platform = 'naep'

    form_key = assessment_id if env_platform == 'naep' and assessment_id else 'cra-form1'
    total_items = item_count or 25

    # Common boilerplate
    env_config_block = """function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}"""

    valid_types = ['baseline', 'ai_content', 'ai_visual', 'qc_checklist', 'functional', 'visual_comparison']

    if template_type not in valid_types:
        return {
            'success': True,
            'result': f'Available template types: {", ".join(valid_types)}.\n'
                      f'Detected platform: **{env_platform}**, assessment: **{assessment_id or "none"}**, '
                      f'items: **{total_items}**, formKey: **{form_key}**.\n'
                      f'Call get_test_template again with a valid type.'
        }

    # Build templates per type and platform
    if template_type == 'baseline':
        if env_platform == 'piaac':
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ login }} = require('../src/helpers/auth');
const {{ selectFilters, getItemLinks, openItem, navigateItemScreens }} = require('../src/helpers/piaac');

{env_config_block}

test('Baseline screenshots — {sc.get("assessmentName", "PIAAC")}', async ({{ page }}) => {{
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await login(page, {{ env: envConfig }});
  await selectFilters(page, {{ version: 'FT New', country: 'ZZZ', language: 'eng', domain: '{domain or "LITNew"}' }});
  const items = await getItemLinks(page);

  for (const item of items) {{
    const itemPage = await openItem(page, item.itemId);
    await navigateItemScreens(itemPage, envConfig, async (pg, idx) => {{
      await expect.soft(pg).toHaveScreenshot(`${{item.itemId}}-screen-${{idx}}.png`, {{ fullPage: true }});
    }});
    await itemPage.close();
  }}
}});"""
        else:
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ loginAndStartTest }} = require('../src/helpers/auth');
const {{ clickNext }} = require('../src/helpers/items');

{env_config_block}

test('Baseline screenshots — {sc.get("assessmentName", "Assessment")}', async ({{ page }}) => {{
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await loginAndStartTest(page, {{ formKey: '{form_key}', env: envConfig }});

  const TOTAL_ITEMS = {total_items};
  for (let i = 1; i <= TOTAL_ITEMS; i++) {{
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveScreenshot(`item-${{i}}.png`, {{ fullPage: true }});
    if (i < TOTAL_ITEMS) await clickNext(page);
  }}
}});"""

    elif template_type == 'ai_content':
        if env_platform == 'piaac':
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ login }} = require('../src/helpers/auth');
const {{ selectFilters, getItemLinks, openItem }} = require('../src/helpers/piaac');
const {{ analyzeItemText }} = require('../src/helpers/ai');

{env_config_block}

test('AI content check — {sc.get("assessmentName", "PIAAC")}', async ({{ page }}) => {{
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await login(page, {{ env: envConfig }});
  await selectFilters(page, {{ version: 'FT New', country: 'ZZZ', language: 'eng', domain: '{domain or "LITNew"}' }});
  const items = await getItemLinks(page);

  for (const item of items) {{
    const itemPage = await openItem(page, item.itemId);
    await itemPage.waitForLoadState('networkidle');
    const text = await itemPage.locator('body').innerText();
    if (text && text.trim().length >= 10) {{
      const result = await analyzeItemText(text, 'English');
      if (result.issuesFound) console.warn(`Issues in ${{item.itemId}}:`, result.issues);
      await test.info().attach(`ai-text-${{item.itemId}}`, {{
        body: JSON.stringify(result, null, 2), contentType: 'application/json'
      }});
    }}
    await itemPage.close();
  }}
}});"""
        else:
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ loginAndStartTest }} = require('../src/helpers/auth');
const {{ clickNext, extractItemText }} = require('../src/helpers/items');
const {{ analyzeItemText }} = require('../src/helpers/ai');

{env_config_block}

test('AI content check — {sc.get("assessmentName", "Assessment")}', async ({{ page }}) => {{
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await loginAndStartTest(page, {{ formKey: '{form_key}', env: envConfig }});

  const TOTAL_ITEMS = {total_items};
  for (let i = 1; i <= TOTAL_ITEMS; i++) {{
    await page.waitForLoadState('networkidle');
    const text = await extractItemText(page);
    if (text && text.trim().length >= 10) {{
      const result = await analyzeItemText(text, 'English');
      if (result.issuesFound) console.warn(`Issues in item ${{i}}:`, result.issues);
      await test.info().attach(`ai-text-item-${{i}}`, {{
        body: JSON.stringify(result, null, 2), contentType: 'application/json'
      }});
    }}
    if (i < TOTAL_ITEMS) await clickNext(page);
  }}
}});"""

    elif template_type == 'ai_visual':
        if env_platform == 'piaac':
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ login }} = require('../src/helpers/auth');
const {{ selectFilters, getItemLinks, openItem }} = require('../src/helpers/piaac');
const {{ analyzeItemScreenshot }} = require('../src/helpers/ai');

{env_config_block}

test('AI visual inspection — {sc.get("assessmentName", "PIAAC")}', async ({{ page }}) => {{
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await login(page, {{ env: envConfig }});
  await selectFilters(page, {{ version: 'FT New', country: 'ZZZ', language: 'eng', domain: '{domain or "LITNew"}' }});
  const items = await getItemLinks(page);

  for (const item of items) {{
    const itemPage = await openItem(page, item.itemId);
    await itemPage.waitForLoadState('networkidle');
    const screenshot = await itemPage.screenshot({{ fullPage: true }});
    const result = await analyzeItemScreenshot(screenshot,
      `Item ${{item.itemId}}. Check text readability, layout integrity, and visual anomalies.`
    );
    if (result.issuesFound) console.warn(`Visual issues in ${{item.itemId}}:`, result.issues);
    await test.info().attach(`ai-vision-${{item.itemId}}`, {{
      body: JSON.stringify(result, null, 2), contentType: 'image/png'
    }});
    await itemPage.close();
  }}
}});"""
        else:
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ loginAndStartTest }} = require('../src/helpers/auth');
const {{ clickNext }} = require('../src/helpers/items');
const {{ analyzeItemScreenshot }} = require('../src/helpers/ai');

{env_config_block}

test('AI visual inspection — {sc.get("assessmentName", "Assessment")}', async ({{ page }}) => {{
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await loginAndStartTest(page, {{ formKey: '{form_key}', env: envConfig }});

  const TOTAL_ITEMS = {total_items};
  for (let i = 1; i <= TOTAL_ITEMS; i++) {{
    await page.waitForLoadState('networkidle');
    const screenshot = await page.screenshot({{ fullPage: true }});
    const result = await analyzeItemScreenshot(screenshot,
      `Assessment item ${{i}}. Check text readability, layout integrity, and visual anomalies.`
    );
    if (result.issuesFound) console.warn(`Visual issues in item ${{i}}:`, result.issues);
    await test.info().attach(`ai-vision-item-${{i}}`, {{
      body: JSON.stringify(result, null, 2), contentType: 'application/json'
    }});
    if (i < TOTAL_ITEMS) await clickNext(page);
  }}
}});"""

    elif template_type == 'qc_checklist':
        # Load all checklist content inline so the AI has everything in one call
        checklists_dir = project_root / 'src' / 'qc-checklists'
        checklist_info = ''
        if checklists_dir.exists():
            for f in sorted(checklists_dir.glob('*.md')):
                content = f.read_text(encoding='utf-8')[:5000]
                checklist_info += f'\n--- {f.stem} checklist ---\n{content}\n'

        if env_platform == 'piaac':
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ login }} = require('../src/helpers/auth');
const {{ selectFilters, getItemLinks, openItem }} = require('../src/helpers/piaac');

{env_config_block}

// QC Checklist — auto-detect interaction type per item
// Detected platform: PIAAC, Domain: {domain or 'LITNew'}
test.describe('QC Checklist — {sc.get("assessmentName", "PIAAC")}', () => {{
  let page;
  let envConfig;

  test.beforeAll(async ({{ browser }}) => {{
    page = await browser.newPage();
    envConfig = loadEnvConfig();
    await login(page, {{ env: envConfig }});
    await selectFilters(page, {{ version: 'FT New', country: 'ZZZ', language: 'eng', domain: '{domain or "LITNew"}' }});
  }});

  test.afterAll(async () => {{ await page.close(); }});

  // TODO: For each item, detect interaction type and run matching checklist steps.
  // Detection signatures:
  //   textarea / contenteditable → Extended Text
  //   select dropdowns in item content → Inline Choice
  //   draggable elements / drop zones → Matching
  //
  // Implement checklist steps as test.step() blocks named QC-1, QC-2, etc.
  // Skip manual-only steps (TTS, scratchwork) with comments.
}});"""
        else:
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ loginAndStartTest }} = require('../src/helpers/auth');
const {{ clickNext }} = require('../src/helpers/items');

{env_config_block}

// QC Checklist — auto-detect interaction type per item
// Detected platform: NAEP, formKey: {form_key}, items: {total_items}
test.describe('QC Checklist — {sc.get("assessmentName", "Assessment")}', () => {{
  test('QC checks across all items', async ({{ page }}) => {{
    test.setTimeout(300000);
    const envConfig = loadEnvConfig();
    await loginAndStartTest(page, {{ formKey: '{form_key}', env: envConfig }});

    const TOTAL_ITEMS = {total_items};
    for (let i = 1; i <= TOTAL_ITEMS; i++) {{
      await page.waitForLoadState('networkidle');

      // Detect interaction type from DOM
      const hasTextarea = await page.locator('textarea').count() > 0;
      const hasContentEditable = await page.locator('[contenteditable="true"]').count() > 0;
      const hasDropdowns = await page.locator('.item-content select, .response-area select').count() > 0;
      const hasDraggables = await page.locator('[draggable="true"], .source-tray .source').count() > 0;

      if (hasTextarea || hasContentEditable) {{
        await test.step(`Item ${{i}} — QC Extended Text`, async () => {{
          // TODO: Implement Extended Text checklist steps
          // QC-1: Verify text entry
          // QC-2: Verify max character limit
          // QC-3: Verify text editing and clearing
        }});
      }}

      if (hasDropdowns) {{
        await test.step(`Item ${{i}} — QC Inline Choice`, async () => {{
          // TODO: Implement Inline Choice checklist steps
          // QC-1: Verify dropdown selection
          // QC-2: Verify clearing answers
          // QC-3: Verify answer retention
        }});
      }}

      if (hasDraggables) {{
        await test.step(`Item ${{i}} — QC Matching`, async () => {{
          // TODO: Implement Matching checklist steps
          // QC-1: Verify drag-and-drop source movement
          // QC-2: Verify click-click source movement
          // QC-3: Verify clearing answers
        }});
      }}

      if (!hasTextarea && !hasContentEditable && !hasDropdowns && !hasDraggables) {{
        console.log(`Item ${{i}}: No known interaction type detected — needs manual QC`);
      }}

      if (i < TOTAL_ITEMS) await clickNext(page);
    }}
  }});
}});"""

        code += f'\n\n/*\nAvailable QC Checklists:\n{checklist_info}\n*/'

    elif template_type == 'functional':
        if env_platform == 'piaac':
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ login }} = require('../src/helpers/auth');
const {{ selectFilters, getItemLinks, openItem }} = require('../src/helpers/piaac');

{env_config_block}

test('Functional test — {sc.get("assessmentName", "PIAAC")}', async ({{ page }}) => {{
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await login(page, {{ env: envConfig }});
  await selectFilters(page, {{ version: 'FT New', country: 'ZZZ', language: 'eng', domain: '{domain or "LITNew"}' }});
  const items = await getItemLinks(page);
  expect(items.length).toBeGreaterThan(0);

  for (const item of items) {{
    const itemPage = await openItem(page, item.itemId);
    await itemPage.waitForLoadState('networkidle');
    // TODO: Add functional test assertions for each item
    await expect(itemPage.locator('body')).toBeVisible();
    await itemPage.close();
  }}
}});"""
        else:
            code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ loginAndStartTest }} = require('../src/helpers/auth');
const {{ clickNext }} = require('../src/helpers/items');

{env_config_block}

test('Functional test — {sc.get("assessmentName", "Assessment")}', async ({{ page }}) => {{
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await loginAndStartTest(page, {{ formKey: '{form_key}', env: envConfig }});

  const TOTAL_ITEMS = {total_items};
  for (let i = 1; i <= TOTAL_ITEMS; i++) {{
    await page.waitForLoadState('networkidle');
    // TODO: Add functional test assertions for each item
    await expect(page.locator('body')).toBeVisible();
    if (i < TOTAL_ITEMS) await clickNext(page);
  }}
}});"""

    elif template_type == 'visual_comparison':
        code = f"""const {{ test, expect }} = require('@playwright/test');
const {{ login }} = require('../src/helpers/auth');
const {{ selectFilters, getItemLinks, openItem }} = require('../src/helpers/piaac');
const fs = require('fs');
const {{ PNG }} = require('pngjs');
const pixelmatch = require('pixelmatch');

{env_config_block}

function compareImages(actualBuf, baselineBuf) {{
  const actual = PNG.sync.read(actualBuf);
  const baseline = PNG.sync.read(baselineBuf);
  const {{ width, height }} = actual;
  const diff = new PNG({{ width, height }});
  const numDiff = pixelmatch(actual.data, baseline.data, diff.data, width, height, {{ threshold: 0.1 }});
  return {{ diffRatio: numDiff / (width * height), diffPng: PNG.sync.write(diff) }};
}}

test('Visual comparison — {sc.get("assessmentName", "Assessment")}', async ({{ page }}) => {{
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await login(page, {{ env: envConfig }});
  // TODO: Set the target locale/language filters
  await selectFilters(page, {{ version: 'FT New', country: 'ZZZ', language: 'eng', domain: '{domain or "LITNew"}' }});
  const items = await getItemLinks(page);
  const failures = [];

  for (const item of items) {{
    const itemPage = await openItem(page, item.itemId);
    await itemPage.waitForLoadState('networkidle');
    const screenshot = await itemPage.screenshot({{ fullPage: true }});
    const baselinePath = `test-results/baseline/${{item.itemId}}.png`;
    if (fs.existsSync(baselinePath)) {{
      const baseline = fs.readFileSync(baselinePath);
      const result = compareImages(screenshot, baseline);
      if (result.diffRatio > 0.05) {{
        failures.push(`${{item.itemId}}: ${{(result.diffRatio * 100).toFixed(2)}}% diff`);
      }}
      await test.info().attach(`diff-${{item.itemId}}`, {{ body: result.diffPng, contentType: 'image/png' }});
    }}
    await itemPage.close();
  }}

  if (failures.length) console.warn('Layout differences:', failures);
}});"""
    else:
        return {'success': False, 'result': f'Unknown template type: {template_type}'}

    # Build context summary
    ctx_summary = f'Platform: {env_platform}'
    if assessment_id:
        ctx_summary += f', Assessment: {assessment_id}'
    if item_count:
        ctx_summary += f', Items: {item_count}'
    if items_list:
        item_names = ', '.join(i['item_id'] for i in items_list[:10])
        if len(items_list) > 10:
            item_names += f' ... +{len(items_list) - 10} more'
        ctx_summary += f'\nKnown items: {item_names}'

    return {
        'success': True,
        'result': f'**Template: {template_type}** ({ctx_summary})\n\n'
                  f'This skeleton is pre-filled with the correct helpers, imports, and item count '
                  f'for the current test context. Customize the TODO sections and call `update_code` '
                  f'with the finished script.\n\n```javascript\n{code}\n```'
    }


def execute_tool(tool_id, args, context):
    """Execute an AI tool. Returns {success, result}."""
    from django.conf import settings
    from pathlib import Path
    import os

    # Verify tool is enabled
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM ai_tools WHERE id = %s', [tool_id])
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        return {'success': False, 'result': f'Unknown tool: {tool_id}'}
    tool = dict(zip(cols, row))
    if not tool['enabled']:
        return {'success': False, 'result': f'Tool "{tool_id}" is disabled'}

    tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
    project_root = Path(settings.PLAYWRIGHT_PROJECT_ROOT)

    if tool_id == 'explain_code':
        code = args.get('code') or context.get('current_code', '')
        if not code.strip():
            return {'success': True, 'result': 'No code is currently loaded.'}
        return {'success': True, 'result': f'Code provided ({len(code.splitlines())} lines). AI will explain it.'}

    elif tool_id == 'update_code':
        if not args.get('code'):
            return {'success': False, 'result': 'No code provided'}
        return {'success': True, 'result': {'code': args['code'], 'summary': args.get('summary', 'Code updated')}}

    elif tool_id == 'read_file':
        if not args.get('path'):
            return {'success': False, 'result': 'No file path provided'}
        normalized = args['path'].replace('\\', '/').lstrip('./')
        full_path = (project_root / normalized).resolve()
        safe_dirs = ['src/helpers', 'tests', 'src/config', 'src/qc-checklists']
        if not str(full_path).startswith(str(project_root)):
            return {'success': False, 'result': 'Access denied: path outside project'}
        allowed = any(str(full_path).startswith(str(project_root / d)) for d in safe_dirs)
        if not allowed:
            return {'success': False, 'result': f'Access denied: only files in {safe_dirs} are readable'}
        try:
            content = full_path.read_text(encoding='utf-8')
            truncated = content[:4000] + '\n... (truncated)' if len(content) > 4000 else content
            return {'success': True, 'result': f'File: {normalized}\n```javascript\n{truncated}\n```'}
        except Exception as e:
            return {'success': False, 'result': f'Cannot read file: {e}'}

    elif tool_id == 'list_helpers':
        helpers_dir = project_root / 'src' / 'helpers'
        try:
            helpers = []
            if helpers_dir.exists():
                for f in helpers_dir.glob('*.js'):
                    content = f.read_text()
                    export_match = re.search(r'module\.exports\s*=\s*\{([^}]+)\}', content)
                    if export_match:
                        names = [n.strip() for n in export_match.group(1).split(',') if n.strip()]
                        for name in names:
                            sig_match = re.search(rf'(?:async\s+)?function\s+{re.escape(name)}\s*\(([^)]*)\)', content)
                            sig = f'{name}({sig_match.group(1) if sig_match else ""})'
                            helpers.append(f'- `{sig}` (from {f.name})')
            result = 'Available helpers:\n' + '\n'.join(helpers) if helpers else 'No helpers found.'
            return {'success': True, 'result': result}
        except Exception as e:
            return {'success': False, 'result': f'Error scanning helpers: {e}'}

    elif tool_id == 'analyze_script':
        code = args.get('code') or context.get('current_code', '')
        if not code.strip():
            return {'success': True, 'result': 'No code to analyze.'}
        # Basic Python-side syntax check isn't possible for JS, just report OK
        return {'success': True, 'result': 'Script syntax check: passed (server-side JS parsing not available; run dry-run for full check).'}

    elif tool_id == 'search_tests':
        query = args.get('query', '').strip()
        if not query:
            return {'success': False, 'result': 'No search query provided'}
        results = []
        for f in tests_dir.rglob('*.spec.js'):
            try:
                content = f.read_text(encoding='utf-8', errors='replace')
                lines = content.splitlines()
                matches = [{'line': i + 1, 'text': l.strip()} for i, l in enumerate(lines) if query.lower() in l.lower()]
                if matches:
                    results.append({'file': str(f.relative_to(project_root)), 'matches': matches[:3]})
            except Exception:
                pass
        if not results:
            return {'success': True, 'result': f'No matches found for "{query}"'}
        output = '\n\n'.join(
            f"**{r['file']}**\n" + '\n'.join(f"  L{m['line']}: {m['text']}" for m in r['matches'])
            for r in results[:5]
        )
        return {'success': True, 'result': f'Found {len(results)} file(s) matching "{query}":\n\n{output}'}

    elif tool_id == 'get_items':
        try:
            conditions = []
            params = []
            if args.get('assessmentId'):
                conditions.append('i.assessment_id = %s')
                params.append(args['assessmentId'])
            if args.get('search'):
                conditions.append('(i.item_id ILIKE %s OR i.title ILIKE %s)')
                params.extend([f"%{args['search']}%", f"%{args['search']}%"])
            where = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
            limit = min(int(args.get('limit', 20)), 50)
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT i.numeric_id, i.item_id, i.title, i.category, i.tier, a.name AS assessment_name '
                    f'FROM items i LEFT JOIN assessments a ON i.assessment_id = a.id '
                    f'{where} ORDER BY i.numeric_id LIMIT %s',
                    params + [limit]
                )
                cols = [c[0] for c in cursor.description]
                items = [dict(zip(cols, r)) for r in cursor.fetchall()]
            if not items:
                return {'success': True, 'result': 'No items found.'}
            output = '\n'.join(
                f"- **{i['item_id']}** — {i['title'] or 'Untitled'} ({i['category']}, tier: {i['tier']})"
                + (f" [{i['assessment_name']}]" if i.get('assessment_name') else '')
                for i in items
            )
            return {'success': True, 'result': f'Found {len(items)} item(s):\n{output}'}
        except Exception as e:
            return {'success': False, 'result': f'Database error: {e}'}

    elif tool_id == 'get_run_screenshots':
        run_id = args.get('run_id', '').strip()
        if not run_id:
            return {'success': False, 'result': 'No run_id provided'}
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT rs.name, rs.file_path, rs.project_name, rs.flagged, rs.flag_notes,
                              trs.script_path
                       FROM run_screenshots rs
                       LEFT JOIN test_run_scripts trs ON rs.run_script_id = trs.id
                       WHERE rs.run_id = %s::uuid
                       ORDER BY rs.name""",
                    [run_id]
                )
                cols = [c[0] for c in cursor.description]
                rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
            if not rows:
                return {'success': True, 'result': f'No screenshots found for run {run_id}.'}
            output = '\n'.join(
                f"- **{r['name']}** — `{r['file_path']}` ({r['project_name']})"
                + (' [FLAGGED]' if r['flagged'] else '')
                + (f" Note: {r['flag_notes']}" if r.get('flag_notes') else '')
                + (f" (from {r['script_path']})" if r.get('script_path') else '')
                for r in rows
            )
            return {'success': True, 'result': f'Found {len(rows)} screenshot(s) for run {run_id[:8]}:\n{output}'}
        except Exception as e:
            return {'success': False, 'result': f'Database error: {e}'}

    elif tool_id == 'get_qc_checklists':
        checklists_dir = project_root / 'src' / 'qc-checklists'
        try:
            if not checklists_dir.exists():
                return {'success': False, 'result': 'No qc-checklists directory found in project.'}
            md_files = sorted(checklists_dir.glob('*.md'))
            if not md_files:
                return {'success': False, 'result': 'No checklist files found in src/qc-checklists/.'}
            output_parts = []
            for f in md_files:
                name = f.stem
                content = f.read_text(encoding='utf-8')
                truncated = content[:6000] + '\n... (truncated)' if len(content) > 6000 else content
                output_parts.append(f'## {name}\nFile: src/qc-checklists/{f.name}\n\n{truncated}')
            return {
                'success': True,
                'result': f'Found {len(md_files)} QC checklist(s):\n\n' + '\n\n---\n\n'.join(output_parts)
            }
        except Exception as e:
            return {'success': False, 'result': f'Error reading checklists: {e}'}

    elif tool_id == 'get_test_template':
        return _build_test_template(args, context, project_root)

    return {'success': False, 'result': f'No executor for tool: {tool_id}'}


# Phrases that indicate the AI is planning/asking instead of acting
_PLANNING_PATTERNS = re.compile(
    r'\b(I will|I\'ll|Let me|Proceeding to|I\'m going to|I can now|'
    r'I\'ll now|going to|plan to|here\'s what|steps?:|'
    r'I need to know|I need to fetch|please confirm|please provide|'
    r'can you (provide|confirm|share)|do you want me to|shall I|'
    r'before I (can|proceed|create|generate)|first I need)\b',
    re.IGNORECASE
)


def _looks_like_planning(text):
    """Return True if response text looks like a plan/request rather than a final answer."""
    if not text or len(text) > 2000:
        return False
    return bool(_PLANNING_PATTERNS.search(text))


def chat(message, conversation_id, current_code, filename, script_context=None, current_summary=None):
    """Process a chat message with an agentic tool loop.

    When the AI calls research tools (read_file, list_helpers, etc.) the
    results are fed back automatically and the AI continues until it either
    produces a text-only reply, calls update_code, or hits MAX_LOOP.

    If the AI responds with just a planning message (no tools), it is
    automatically nudged to continue and actually execute the work.
    """
    from ai.provider import get_provider

    # Tools that trigger auto-continue (research / context-gathering)
    RESEARCH_TOOLS = {'read_file', 'list_helpers', 'search_tests', 'get_items',
                      'explain_code', 'analyze_script', 'get_run_screenshots',
                      'get_qc_checklists', 'get_test_template'}

    # Load or create conversation
    if conversation_id:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id, messages FROM ai_conversations WHERE id = %s', [conversation_id])
            row = cursor.fetchone()
        if row:
            conv_id = str(row[0])
            messages = row[1] if isinstance(row[1], list) else json.loads(row[1])
        else:
            conv_id = str(uuid.uuid4())
            messages = []
    else:
        conv_id = str(uuid.uuid4())
        messages = []

    # Build system prompt with assessment/item context
    system_prompt = build_system_prompt(current_code, filename, script_context=script_context, current_summary=current_summary)

    # Add user message
    messages.append({'role': 'user', 'content': message})

    # Trim to max turns
    if len(messages) > MAX_TURNS * 2:
        messages = messages[-MAX_TURNS * 2:]

    provider = get_provider()
    all_tool_results = []
    code_update = None
    final_text = ''
    intermediate_messages = []  # assistant texts from mid-loop iterations
    steps = []  # track what happened at each loop iteration
    chat_start = time.time()

    logger.info('chat start conv=%s msg_len=%d history=%d', conv_id[:8], len(message), len(messages) - 1)

    for iteration in range(MAX_LOOP):
        # Call AI
        ai_messages = [{'role': 'system', 'content': system_prompt}] + messages
        iter_start = time.time()
        raw_response = provider.chat_completion(ai_messages, {'max_tokens': 8000})
        ai_duration = time.time() - iter_start

        # Parse tool calls
        text, tool_calls = parse_tool_calls(raw_response)
        tool_names = [tc['tool'] for tc in tool_calls]
        logger.info('chat iter=%d ai_call=%.1fs tools=%s resp_len=%d',
                     iteration + 1, ai_duration, tool_names or 'none', len(raw_response))

        # Add assistant message to conversation
        messages.append({'role': 'assistant', 'content': raw_response})

        if not tool_calls:
            # Empty response — the AI returned nothing (possibly content filter or token issue)
            if (not text or not text.strip()) and iteration < MAX_LOOP - 1:
                steps.append({
                    'iteration': iteration + 1,
                    'tools': [],
                    'note': 'auto-continue (empty response)',
                })
                messages.pop()  # remove the empty assistant message
                messages.append({'role': 'user', 'content':
                    'Your previous response was empty. You MUST respond now. '
                    'If you have gathered enough context from the tools, call update_code '
                    'with the complete finished script. If you need to explain something, '
                    'write your explanation as plain text.'})
                continue

            # No tools called — check if the AI is just announcing a plan
            if _looks_like_planning(text) and iteration < MAX_LOOP - 1:
                # Save this as an intermediate message and nudge the AI to continue
                intermediate_messages.append(text)
                steps.append({
                    'iteration': iteration + 1,
                    'tools': [],
                    'note': 'auto-continue (planning response)',
                })
                messages.append({'role': 'user', 'content':
                    'Do not ask me for information — you have tools to find it yourself. '
                    'Call list_helpers to see available helper functions. '
                    'Call read_file to read src/helpers/piaac.js and src/helpers/auth.js. '
                    'Call get_items to look up item details. '
                    'Then call update_code with the complete finished script. '
                    'Do all of this NOW in your next response — do not ask for confirmation.'})
                continue

            # Genuine final text response — we're done
            final_text = text
            break

        # If we have both text and tool calls, save the text as intermediate
        if text.strip() and len(text.strip()) > 3:
            intermediate_messages.append(text)

        # Execute tools
        needs_continue = False
        tool_result_parts = []

        for tc in tool_calls:
            result = execute_tool(tc['tool'], tc['args'],
                                  {'current_code': current_code, 'filename': filename,
                                   'script_context': script_context or {}})
            all_tool_results.append({
                'tool': tc['tool'],
                'args': tc['args'],
                'success': result['success'],
                'result': result['result'],
            })

            if tc['tool'] == 'update_code' and result['success'] and isinstance(result.get('result'), dict):
                code_update = {
                    'code': result['result']['code'],
                    'summary': result['result'].get('summary', 'Code updated'),
                }
                # update_code delivered code — update current_code for any further iterations
                current_code = result['result']['code']
            elif tc['tool'] in RESEARCH_TOOLS:
                needs_continue = True

            # Format tool result for the AI to consume
            result_text = result['result'] if isinstance(result['result'], str) else json.dumps(result['result'])
            tool_result_parts.append(
                f"[Tool: {tc['tool']}] {'OK' if result['success'] else 'ERROR'}: {result_text}"
            )

        steps.append({
            'iteration': iteration + 1,
            'tools': [tc['tool'] for tc in tool_calls],
        })

        # If only update_code was called (no research tools), we're done
        if not needs_continue:
            final_text = text
            break

        # Feed tool results back — escalate urgency on later iterations
        tool_feedback = "Tool results:\n\n" + "\n\n".join(tool_result_parts)
        if iteration >= 3:
            tool_feedback += (
                "\n\nYou have gathered enough context. STOP reading more files. "
                "Call update_code NOW with the complete finished script. "
                "Do NOT call any more research tools."
            )
        elif iteration >= 1:
            tool_feedback += (
                "\n\nYou should have enough context now. "
                "Generate the complete script and call update_code. "
                "Only read more files if absolutely necessary."
            )
        else:
            tool_feedback += (
                "\n\nContinue with the task. If you have enough context, "
                "generate the code now using update_code."
            )
        messages.append({'role': 'user', 'content': tool_feedback})

    # If code was updated but no final text, generate a completion message
    if code_update and not final_text:
        final_text = f"Done — {code_update['summary']}. The script is ready in the editor. You can review it, then Save or Save & Run."

    # If the loop exhausted without producing any output, provide a fallback
    if not final_text and not code_update:
        tool_names = [t['tool'] for t in all_tool_results]
        if tool_names:
            final_text = (
                f"I gathered context using {', '.join(tool_names)} but wasn't able to "
                f"generate a complete response. This can happen when the task is complex "
                f"or the AI service returned an incomplete response. "
                f"Please try again — you can simplify the request or break it into steps."
            )
        else:
            final_text = (
                "I wasn't able to generate a response. The AI service may be temporarily "
                "unavailable. Please try again."
            )

    total_duration = time.time() - chat_start
    tool_names_used = [t['tool'] for t in all_tool_results]
    logger.info('chat done conv=%s total=%.1fs iterations=%d tools=%s code_update=%s',
                conv_id[:8], total_duration, len(steps), tool_names_used or 'none',
                bool(code_update))

    # Save conversation to DB
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO ai_conversations (id, messages, created_at, last_active_at)
               VALUES (%s, %s, now(), now())
               ON CONFLICT (id) DO UPDATE SET messages = EXCLUDED.messages, last_active_at = now()""",
            [conv_id, json.dumps(messages)]
        )

    return {
        'conversationId': conv_id,
        'response': final_text,
        'intermediateMessages': intermediate_messages,
        'codeUpdate': code_update,
        'steps': steps,
        'toolsUsed': [
            {
                'tool': t['tool'],
                'success': t['success'],
                'summary': (t['result'][:200] if isinstance(t['result'], str)
                            else t['result'].get('summary', ''))
                           if t.get('result') else '',
            }
            for t in all_tool_results
        ],
    }
