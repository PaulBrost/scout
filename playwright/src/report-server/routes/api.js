// SCOUT — API Routes (JSON endpoints for client-side features)
const router = require('express').Router();
const path = require('path');
const fs = require('fs');
const db = require('../../db');
const queries = require('../../db/queries');
const chatManager = require('../lib/chat-manager');

// AI Chat — multi-turn conversation with tool calling
router.post('/builder/chat', async (req, res) => {
  const { message, conversationId, currentCode, filename } = req.body;
  if (!message) {
    return res.status(400).json({ error: 'Message is required' });
  }

  try {
    const result = await chatManager.chat(message, conversationId, currentCode, filename);
    res.json(result);
  } catch (err) {
    console.error('Chat error:', err.message);
    res.json({ error: err.message, conversationId: conversationId || null });
  }
});

// AI Test Builder — generate test code (legacy, kept for backward compat)
router.post('/builder/generate', async (req, res) => {
  const { description, existingCode, filename } = req.body;
  if (!description) {
    return res.status(400).json({ error: 'Description is required' });
  }

  try {
    const ai = require('../../ai');
    const context = await buildTestBuilderContext();
    if (existingCode) {
      context.existingCode = existingCode;
      context.filename = filename;
    }
    const code = await ai.generateTest(description, context);
    res.json({ code, model: process.env.AI_PROVIDER });
  } catch (err) {
    console.error('Test builder error:', err.message);
    res.json({ error: err.message });
  }
});

// AI Test Builder — save generated test
router.post('/builder/save', async (req, res) => {
  const { code } = req.body;
  if (!code) {
    return res.status(400).json({ error: 'No code to save' });
  }

  try {
    const testsDir = path.resolve(__dirname, '../../../tests/generated');
    if (!fs.existsSync(testsDir)) {
      fs.mkdirSync(testsDir, { recursive: true });
    }

    const filename = `generated-${Date.now()}.spec.js`;
    const filepath = path.join(testsDir, filename);
    fs.writeFileSync(filepath, code);

    res.json({ path: `tests/generated/${filename}` });
  } catch (err) {
    res.json({ error: err.message });
  }
});

// Test case save (from editor)
router.post('/test-cases/save', (req, res) => {
  const { path: filePath, content } = req.body;
  if (!filePath || content == null) {
    return res.status(400).json({ error: 'Path and content are required' });
  }

  const testsDir = path.resolve(__dirname, '../../../tests');
  const fullPath = path.resolve(testsDir, filePath);

  // Security: ensure path stays within tests directory
  if (!fullPath.startsWith(testsDir)) {
    return res.status(403).json({ error: 'Access denied' });
  }

  try {
    fs.writeFileSync(fullPath, content, 'utf-8');
    // Auto-register in test_scripts table
    db.query(
      "INSERT INTO test_scripts (script_path, browser, viewport, test_type, tags, ai_config, created_at, updated_at) VALUES ($1, 'chromium', '1920x1080', 'functional', '[]'::jsonb, '{}'::jsonb, now(), now()) ON CONFLICT (script_path) DO UPDATE SET updated_at = now()",
      [filePath]
    ).catch(function() {});
    res.json({ success: true, path: filePath });
  } catch (err) {
    res.json({ error: err.message });
  }
});

// Dry run — validate script syntax without executing
router.post('/test-cases/dry-run', (req, res) => {
  const { code } = req.body;
  if (!code) return res.status(400).json({ error: 'No code provided' });

  try {
    // Use Node's vm module to check for syntax errors without executing
    const vm = require('vm');
    new vm.Script(code, { filename: 'dry-run.spec.js' });
    res.json({ success: true, message: 'Syntax valid — no errors found' });
  } catch (err) {
    var loc = err.stack ? err.stack.split('\n').slice(0, 3).join('\n') : err.message;
    res.json({ error: loc });
  }
});

// Dashboard data API
router.get('/runs/latest', async (req, res) => {
  try {
    const result = await db.query(
      'SELECT * FROM test_runs ORDER BY started_at DESC LIMIT 1'
    );
    const run = result.rows[0];
    if (!run) return res.json({ run: null });

    const summary = await queries.getRunSummary(run.id);
    res.json({ run, summary });
  } catch (err) {
    res.json({ error: err.message });
  }
});

router.get('/trend', async (req, res) => {
  try {
    const trend = await queries.getPassRateTrend(parseInt(req.query.limit || '10', 10));
    res.json({ trend });
  } catch (err) {
    res.json({ error: err.message });
  }
});

router.get('/ai-flags', async (req, res) => {
  try {
    const flags = await queries.getPendingAIFlags();
    res.json({ flags });
  } catch (err) {
    res.json({ error: err.message });
  }
});

/**
 * Build context for the AI test builder — scans helpers for available functions.
 */
async function buildTestBuilderContext() {
  const helpersDir = path.resolve(__dirname, '../../helpers');
  const helpers = {};

  try {
    const files = fs.readdirSync(helpersDir).filter(f => f.endsWith('.js'));
    for (const file of files) {
      const content = fs.readFileSync(path.join(helpersDir, file), 'utf-8');
      // Extract exported function names and JSDoc comments
      const exports = [];
      const exportMatch = content.match(/module\.exports\s*=\s*\{([^}]+)\}/);
      if (exportMatch) {
        const names = exportMatch[1].split(',').map(s => s.trim()).filter(Boolean);
        for (const name of names) {
          // Find the function and its preceding JSDoc
          const funcRegex = new RegExp(`(/\\*\\*[\\s\\S]*?\\*/)?\\s*(?:async\\s+)?function\\s+${name}`, 'm');
          const match = content.match(funcRegex);
          exports.push({
            name,
            doc: match?.[1] || null,
          });
        }
      }
      helpers[file] = exports;
    }
  } catch { /* ignore */ }

  return { helpers };
}

// ── Update script associations (item/assessment) ───────
router.post('/test-cases/associate', async (req, res) => {
  try {
    var scriptPath = req.body.scriptPath;
    if (!scriptPath) return res.status(400).json({ error: 'scriptPath required' });

    var itemId = req.body.itemId || null;
    var assessmentId = req.body.assessmentId || null;
    var category = req.body.category || null;
    var description = req.body.description || null;

    // Upsert into test_scripts
    await db.query(
      `INSERT INTO test_scripts (script_path, item_id, assessment_id, category, description, browser, viewport, test_type, tags, ai_config, created_at, updated_at)
       VALUES ($1, $2, $3, $4, $5, 'chromium', '1920x1080', 'functional', '[]'::jsonb, '{}'::jsonb, now(), now())
       ON CONFLICT (script_path) DO UPDATE SET
         item_id = EXCLUDED.item_id,
         assessment_id = EXCLUDED.assessment_id,
         category = COALESCE(EXCLUDED.category, test_scripts.category),
         description = COALESCE(EXCLUDED.description, test_scripts.description),
         updated_at = now()`,
      [scriptPath, itemId, assessmentId, category, description]
    );

    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
