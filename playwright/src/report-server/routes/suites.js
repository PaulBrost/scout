// SCOUT — Test Suites Routes
// CRUD and API for grouping test scripts into runnable suites.

const router = require('express').Router();
const db = require('../../db');
const path = require('path');
const fs = require('fs');
const executor = require('../lib/executor');

const TESTS_DIR = path.resolve(__dirname, '../../../tests');
const USE_MOCK = process.env.SCOUT_MOCK === '1';

// ── Mock Playwright log helpers ──────────────────────────

var MOCK_ERRORS = [
  {
    short: 'AssertionError: expect(locator).toBeVisible()',
    full: 'AssertionError: expect(locator).toBeVisible()\n\nLocator: getByRole(\'button\', { name: \'Submit\' })\nExpected: visible\nReceived: hidden\n\nCall log:\n  - waiting for getByRole(\'button\', { name: \'Submit\' })\n  -   locator resolved to <button class="btn-submit hidden">Submit</button>\n  -   unexpected value "hidden"\n\n    at tests/features/submit-button.spec.js:24:17'
  },
  {
    short: 'AssertionError: screenshot diff exceeded threshold (0.032 > 0.01)',
    full: 'AssertionError: Screenshot comparison failed\n\nExpected: baselines/v2025/chrome-desktop/item-042.png\nReceived: test-results/item-042-actual.png\n   Diff:  test-results/item-042-diff.png\n\nMax diff pixel ratio: 0.01\nActual diff ratio:    0.032 (3.2% of pixels differ)\n\nPixels changed: 4,891 of 152,064\nRegions affected: header area (y: 0-64), footer area (y: 680-768)\n\n    at tests/visual/item-042.spec.js:18:5'
  },
  {
    short: 'TimeoutError: locator.click: Timeout 30000ms exceeded',
    full: 'TimeoutError: locator.click: Timeout 30000ms exceeded.\n\nLocator: locator(\'#calculator-panel >> button.calc-equals\')\n\nCall log:\n  - waiting for locator(\'#calculator-panel >> button.calc-equals\')\n  -   locator resolved to 0 elements\n  -   waiting for locator(\'#calculator-panel >> button.calc-equals\')\n  -   locator resolved to 0 elements\n  -   ... (repeated 12 times)\n\n    at tests/features/calculator.spec.js:47:22'
  },
  {
    short: 'Error: expect(received).toContain(expected)',
    full: 'Error: expect(received).toContain(expected)\n\nExpected substring: "¿Cuál es la respuesta correcta?"\n  Received string:   "¿Cual es la respuesta correcta?"\n                           ^ missing accent on \'a\'\n\nThis may indicate a content regression in the Spanish translation.\nItem: SPA-MATH-2025-017, Language: es-US\n\n    at tests/content/spanish-spelling.spec.js:33:10'
  },
  {
    short: 'AssertionError: expect(locator).toHaveText(expected)',
    full: 'AssertionError: expect(locator).toHaveText(expected)\n\nLocator: locator(\'.help-panel-content p:first-child\')\nExpected: "Click on your answer choice."\nReceived: "Click on you answer choice."\n                       ^^^ missing \'r\' — possible typo "you" vs "your"\n\n    at tests/content/help-panel-text.spec.js:19:5'
  },
  {
    short: 'Error: page.goto: net::ERR_CONNECTION_REFUSED',
    full: 'Error: page.goto: net::ERR_CONNECTION_REFUSED at https://assessment.naep.local/items/087\n\nCall log:\n  - navigating to "https://assessment.naep.local/items/087"\n  -   request to https://assessment.naep.local/items/087 failed: net::ERR_CONNECTION_REFUSED\n\nPossible causes:\n  - Assessment server is not running or unreachable\n  - VPN/network connectivity issue\n  - Item URL has changed\n\n    at tests/workflow/item-navigation.spec.js:12:3'
  }
];

function generateMockLog(scriptPath, status, durationMs) {
  var steps = [];
  var t = 0;
  var filename = scriptPath.split('/').pop();

  steps.push('[' + t + 'ms] ▶ Running: ' + scriptPath);
  t += 50 + Math.floor(Math.random() * 100);
  steps.push('[' + t + 'ms] ▶ Browser launched (chromium)');
  t += 200 + Math.floor(Math.random() * 300);
  steps.push('[' + t + 'ms] ▶ page.goto(https://assessment.naep.local/login)');
  t += 800 + Math.floor(Math.random() * 400);
  steps.push('[' + t + 'ms] ✓ Navigation to login page (HTTP 200)');
  t += 100 + Math.floor(Math.random() * 200);
  steps.push('[' + t + 'ms] ▶ page.fill(#username, \'test_user\')');
  t += 50;
  steps.push('[' + t + 'ms] ▶ page.fill(#password, \'••••••••\')');
  t += 50;
  steps.push('[' + t + 'ms] ▶ page.click(button[type="submit"])');
  t += 600 + Math.floor(Math.random() * 500);
  steps.push('[' + t + 'ms] ✓ Login successful — redirected to /dashboard');

  // Navigation to test target
  t += 200 + Math.floor(Math.random() * 300);
  steps.push('[' + t + 'ms] ▶ page.goto(https://assessment.naep.local/items/042)');
  t += 500 + Math.floor(Math.random() * 800);
  steps.push('[' + t + 'ms] ✓ Item page loaded');

  if (filename.includes('visual') || Math.random() < 0.3) {
    t += 100;
    steps.push('[' + t + 'ms] ▶ page.screenshot({ fullPage: true })');
    t += 300 + Math.floor(Math.random() * 200);
    steps.push('[' + t + 'ms] ✓ Screenshot captured (1366×768)');
    t += 100;
    steps.push('[' + t + 'ms] ▶ page.screenshot({ path: \'test-results/item-042.png\', fullPage: true })');
  } else if (filename.includes('content') || filename.includes('spelling')) {
    t += 100;
    steps.push('[' + t + 'ms] ▶ page.locator(\'.item-content\').textContent()');
    t += 200;
    steps.push('[' + t + 'ms] ✓ Extracted text content (342 characters)');
    t += 50;
    steps.push('[' + t + 'ms] ▶ AI analysis request to ollama (qwen2.5:14b)');
    t += 2000 + Math.floor(Math.random() * 1500);
    steps.push('[' + t + 'ms] ✓ AI response received');
  } else {
    t += 100;
    steps.push('[' + t + 'ms] ▶ page.click(\'.feature-toggle\')');
    t += 200 + Math.floor(Math.random() * 200);
    steps.push('[' + t + 'ms] ✓ Feature panel opened');
    t += 100;
    steps.push('[' + t + 'ms] ▶ expect(locator).toBeVisible()');
  }

  if (status === 'passed') {
    t += 200;
    steps.push('[' + t + 'ms] ✓ Assertion passed');
    t += 100;
    steps.push('[' + t + 'ms] ▶ Browser closed');
    steps.push('[' + durationMs + 'ms] ✓ Test passed (' + (durationMs / 1000).toFixed(1) + 's)');
  } else {
    t += 200;
    steps.push('[' + t + 'ms] ✗ Assertion FAILED');
    t += 50;
    steps.push('[' + t + 'ms] ▶ Capturing failure screenshot...');
    t += 300;
    steps.push('[' + t + 'ms] ▶ Saving trace: test-results/' + filename.replace('.spec.js', '') + '/trace.zip');
    t += 100;
    steps.push('[' + t + 'ms] ▶ Browser closed');
    steps.push('[' + durationMs + 'ms] ✗ Test FAILED (' + (durationMs / 1000).toFixed(1) + 's)');
  }

  return steps.join('\n');
}

function pickMockError() {
  return MOCK_ERRORS[Math.floor(Math.random() * MOCK_ERRORS.length)];
}

// ── Helpers ──────────────────────────────────────────────

// Scan test script files (shared logic with test-cases route)
let scriptCache = null;
let scriptCacheTime = 0;
const CACHE_TTL = 30000;

function getTestScripts() {
  const now = Date.now();
  if (scriptCache && now - scriptCacheTime < CACHE_TTL) return scriptCache;
  const scripts = [];
  function scan(dir, prefix) {
    prefix = prefix || '';
    if (!fs.existsSync(dir)) return;
    var entries = fs.readdirSync(dir, { withFileTypes: true });
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (e.isDirectory()) { scan(path.join(dir, e.name), prefix ? prefix + '/' + e.name : e.name); continue; }
      if (!e.name.endsWith('.spec.js')) continue;
      var fp = path.join(dir, e.name);
      var rp = prefix ? prefix + '/' + e.name : e.name;
      var content = fs.readFileSync(fp, 'utf-8');
      var testCount = (content.match(/\btest\s*\(/g) || []).length;
      var type = 'feature', typeLabel = 'Feature';
      if (rp.includes('visual-regression') || content.includes('@visual')) { type = 'visual'; typeLabel = 'Visual Regression'; }
      else if (rp.includes('content-validation') || content.includes('@content')) { type = 'content'; typeLabel = 'Content Validation'; }
      var descMatch = content.match(/test\.describe\s*\(\s*['"`]([^'"`]+)/);
      var name = descMatch ? descMatch[1] : e.name.replace('.spec.js', '');
      scripts.push({ name, type, typeLabel, testCount, relativePath: rp });
    }
  }
  scan(TESTS_DIR);
  scriptCache = scripts;
  scriptCacheTime = now;
  return scripts;
}

// ── API: paginated list ──────────────────────────────────

router.get('/api/list', async (req, res) => {
  try {
    var page = Math.max(1, parseInt(req.query.page) || 1);
    var pageSize = Math.min(500, Math.max(1, parseInt(req.query.pageSize) || 25));
    var sort = req.query.sort || 'name';
    var dir = req.query.dir === 'desc' ? 'DESC' : 'ASC';
    var search = (req.query.search || '').trim();

    var validSorts = { name: 's.name', scripts: 'script_count', schedule: 's.schedule', updated: 's.updated_at' };
    var orderCol = validSorts[sort] || 's.name';

    var where = [];
    var params = [];
    if (search) {
      params.push('%' + search.toLowerCase() + '%');
      where.push('(LOWER(s.name) LIKE $' + params.length + ' OR LOWER(s.description) LIKE $' + params.length + ')');
    }

    var whereClause = where.length ? 'WHERE ' + where.join(' AND ') : '';

    // Count
    var countResult = await db.query('SELECT COUNT(*) FROM test_suites s ' + whereClause, params);
    var total = parseInt(countResult.rows[0].count);

    // Rows
    var offset = (page - 1) * pageSize;
    var rowParams = params.slice();
    rowParams.push(pageSize);
    rowParams.push(offset);

    var sql = `
      SELECT s.*,
        (SELECT COUNT(*) FROM test_suite_scripts ss WHERE ss.suite_id = s.id) AS script_count,
        tr.started_at AS last_run_at, tr.status AS last_run_status
      FROM test_suites s
      LEFT JOIN LATERAL (
        SELECT started_at, status FROM test_runs WHERE suite_id = s.id ORDER BY started_at DESC LIMIT 1
      ) tr ON true
      ${whereClause}
      ORDER BY ${orderCol} ${dir}
      LIMIT $${rowParams.length - 1} OFFSET $${rowParams.length}
    `;

    var result = await db.query(sql, rowParams);
    res.json({ rows: result.rows, total, page, pageSize });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── API: get scripts in a suite ──────────────────────────

router.get('/:id/scripts', async (req, res) => {
  try {
    var result = await db.query(
      'SELECT script_path, added_at FROM test_suite_scripts WHERE suite_id = $1 ORDER BY added_at',
      [req.params.id]
    );
    res.json({ scripts: result.rows });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── API: run a suite (mock execution) ────────────────────

router.post('/:id/run', async (req, res) => {
  try {
    var suiteId = req.params.id;

    // Get suite + scripts
    var suiteResult = await db.query('SELECT * FROM test_suites WHERE id = $1', [suiteId]);
    if (suiteResult.rows.length === 0) return res.status(404).json({ error: 'Suite not found' });
    var suite = suiteResult.rows[0];

    var scriptsResult = await db.query(
      'SELECT script_path FROM test_suite_scripts WHERE suite_id = $1', [suiteId]
    );
    if (scriptsResult.rows.length === 0) return res.status(400).json({ error: 'Suite has no scripts' });

    // Create test run
    var runResult = await db.query(
      `INSERT INTO test_runs (status, trigger_type, suite_id, config, notes)
       VALUES ('running', 'dashboard', $1, $2, $3)
       RETURNING id`,
      [suiteId, JSON.stringify({ browser_profiles: suite.browser_profiles }), 'Suite: ' + suite.name]
    );
    var runId = runResult.rows[0].id;

    // Create run script rows
    var scriptPaths = scriptsResult.rows.map(r => r.script_path);
    for (var i = 0; i < scriptPaths.length; i++) {
      await db.query(
        'INSERT INTO test_run_scripts (run_id, script_path, status) VALUES ($1, $2, $3)',
        [runId, scriptPaths[i], 'queued']
      );
    }

    // Execute in background (non-blocking)
    if (USE_MOCK) {
      // Mock execution for demo/dev
      setTimeout(async () => {
        try {
          var passed = 0, failed = 0;
          for (var j = 0; j < scriptPaths.length; j++) {
            var status = Math.random() < 0.8 ? 'passed' : 'failed';
            var duration = Math.floor(Math.random() * 8000) + 1000;
            var err = status === 'failed' ? pickMockError() : null;
            var errMsg = err ? err.short : null;
            var log = generateMockLog(scriptPaths[j], status, duration);
            if (err) log += '\n\n── Error Detail ──────────────────────\n' + err.full;
            await db.query(
              `UPDATE test_run_scripts SET status = $1, duration_ms = $2, error_message = $3,
               execution_log = $4, completed_at = now()
               WHERE run_id = $5 AND script_path = $6`,
              [status, duration, errMsg, log, runId, scriptPaths[j]]
            );
            if (status === 'passed') passed++; else failed++;
          }
          var runStatus = failed === 0 ? 'completed' : 'failed';
          await db.query(
            `UPDATE test_runs SET status = $1, completed_at = now(),
             summary = $2 WHERE id = $3`,
            [runStatus, JSON.stringify({ passed, failed, total: scriptPaths.length }), runId]
          );
        } catch (e) {
          console.error('Mock run error:', e.message);
          await db.query("UPDATE test_runs SET status = 'failed', completed_at = now() WHERE id = $1", [runId]);
        }
      }, 2000 + Math.random() * 2000);
    } else {
      // Real Playwright execution — pass recording options via env
      var execOptions = {};
      if (req.body && req.body.recordAll) {
        execOptions.env = { PW_VIDEO: 'on', PW_TRACE: 'on' };
      }
      executor.executeRun(runId, scriptPaths, execOptions).catch(function(e) {
        console.error('[Executor] Suite run error:', e.message);
        db.query("UPDATE test_runs SET status = 'failed', completed_at = now() WHERE id = $1", [runId]).catch(function() {});
      });
    }

    res.json({ runId, status: 'running', scripts: scriptPaths.length });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── API: run a single script (ad-hoc, no suite) ─────────

router.post('/run-script', async (req, res) => {
  try {
    var scriptPath = req.body.scriptPath;
    if (!scriptPath) return res.status(400).json({ error: 'scriptPath required' });

    var runResult = await db.query(
      `INSERT INTO test_runs (status, trigger_type, config, notes)
       VALUES ('running', 'manual', '{}', $1)
       RETURNING id`,
      ['Ad-hoc: ' + scriptPath]
    );
    var runId = runResult.rows[0].id;

    await db.query(
      'INSERT INTO test_run_scripts (run_id, script_path, status) VALUES ($1, $2, $3)',
      [runId, scriptPath, 'queued']
    );

    // Execute in background (non-blocking)
    if (USE_MOCK) {
      setTimeout(async () => {
        try {
          var status = Math.random() < 0.85 ? 'passed' : 'failed';
          var duration = Math.floor(Math.random() * 5000) + 800;
          var err = status === 'failed' ? pickMockError() : null;
          var errMsg = err ? err.short : null;
          var log = generateMockLog(scriptPath, status, duration);
          if (err) log += '\n\n── Error Detail ──────────────────────\n' + err.full;
          await db.query(
            `UPDATE test_run_scripts SET status = $1, duration_ms = $2, error_message = $3,
             execution_log = $4, completed_at = now()
             WHERE run_id = $5 AND script_path = $6`,
            [status, duration, errMsg, log, runId, scriptPath]
          );
          await db.query(
            `UPDATE test_runs SET status = $1, completed_at = now(),
             summary = $2 WHERE id = $3`,
            [status === 'passed' ? 'completed' : 'failed',
             JSON.stringify({ passed: status === 'passed' ? 1 : 0, failed: status === 'failed' ? 1 : 0, total: 1 }),
             runId]
          );
        } catch (e) {
          console.error('Mock script run error:', e.message);
        }
      }, 1500 + Math.random() * 2000);
    } else {
      // Real Playwright execution
      var execOptions = {};
      if (req.body && req.body.recordAll) {
        execOptions.env = { PW_VIDEO: 'on', PW_TRACE: 'on' };
      }
      executor.executeRun(runId, [scriptPath], execOptions).catch(function(e) {
        console.error('[Executor] Script run error:', e.message);
        db.query("UPDATE test_runs SET status = 'failed', completed_at = now() WHERE id = $1", [runId]).catch(function() {});
      });
    }

    res.json({ runId, status: 'running' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── Pages ────────────────────────────────────────────────

// List page
router.get('/', async (req, res) => {
  try {
    res.render('suites', {});
  } catch (err) {
    res.render('suites', { error: err.message });
  }
});

// New suite page
router.get('/new', async (req, res) => {
  try {
    res.render('suite-detail', { suite: null, scripts: getTestScripts() });
  } catch (err) {
    res.status(500).render('error', { error: err.message });
  }
});

// Suite detail / edit page
router.get('/:id', async (req, res) => {
  try {
    var result = await db.query('SELECT * FROM test_suites WHERE id = $1', [req.params.id]);
    if (result.rows.length === 0) return res.status(404).render('error', { error: 'Suite not found' });
    var suite = result.rows[0];

    var scriptsResult = await db.query(
      'SELECT script_path FROM test_suite_scripts WHERE suite_id = $1', [suite.id]
    );
    suite.scriptPaths = scriptsResult.rows.map(r => r.script_path);

    res.render('suite-detail', { suite, scripts: getTestScripts() });
  } catch (err) {
    res.status(500).render('error', { error: err.message });
  }
});

// Create suite
router.post('/', async (req, res) => {
  try {
    var { name, description, scripts, browser_profiles, schedule } = req.body;
    if (!name || !name.trim()) return res.status(400).json({ error: 'Name is required' });

    var profiles = browser_profiles && browser_profiles.length ? browser_profiles : ['chrome-desktop'];
    var sched = schedule && schedule.enabled ? schedule : null;

    var result = await db.query(
      `INSERT INTO test_suites (name, description, created_by, schedule, browser_profiles)
       VALUES ($1, $2, $3, $4, $5) RETURNING id`,
      [name.trim(), description || null, 'scout', sched ? JSON.stringify(sched) : null, profiles]
    );
    var suiteId = result.rows[0].id;

    // Add scripts
    if (scripts && scripts.length) {
      for (var i = 0; i < scripts.length; i++) {
        await db.query(
          'INSERT INTO test_suite_scripts (suite_id, script_path) VALUES ($1, $2) ON CONFLICT DO NOTHING',
          [suiteId, scripts[i]]
        );
      }
    }

    res.json({ id: suiteId, redirect: '/suites/' + suiteId });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Update suite
router.put('/:id', async (req, res) => {
  try {
    var { name, description, scripts, browser_profiles, schedule } = req.body;
    if (!name || !name.trim()) return res.status(400).json({ error: 'Name is required' });

    var profiles = browser_profiles && browser_profiles.length ? browser_profiles : ['chrome-desktop'];
    var sched = schedule && schedule.enabled ? schedule : null;

    await db.query(
      `UPDATE test_suites SET name = $1, description = $2, schedule = $3,
       browser_profiles = $4, updated_at = now() WHERE id = $5`,
      [name.trim(), description || null, sched ? JSON.stringify(sched) : null, profiles, req.params.id]
    );

    // Replace scripts
    await db.query('DELETE FROM test_suite_scripts WHERE suite_id = $1', [req.params.id]);
    if (scripts && scripts.length) {
      for (var i = 0; i < scripts.length; i++) {
        await db.query(
          'INSERT INTO test_suite_scripts (suite_id, script_path) VALUES ($1, $2)',
          [req.params.id, scripts[i]]
        );
      }
    }

    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Delete suite
router.delete('/:id', async (req, res) => {
  try {
    await db.query('DELETE FROM test_suites WHERE id = $1', [req.params.id]);
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
