// SCOUT — Admin Routes
const router = require('express').Router();
const db = require('../../db');

// AI Settings page
router.get('/ai', async (req, res) => {
  try {
    const [settingsResult, toolsResult] = await Promise.all([
      db.query('SELECT * FROM ai_settings ORDER BY key'),
      db.query('SELECT * FROM ai_tools ORDER BY category, name'),
    ]);

    const settings = {};
    for (const row of settingsResult.rows) {
      settings[row.key] = row.value;
    }

    res.render('admin-ai', {
      settings,
      tools: toolsResult.rows,
      provider: process.env.AI_PROVIDER || 'mock',
      success: req.query.success || null,
    });
  } catch (err) {
    res.status(500).render('error', { error: err.message });
  }
});

// Save system prompt
router.post('/ai/prompt', async (req, res) => {
  const { prompt } = req.body;
  try {
    await db.query(
      `INSERT INTO ai_settings (key, value, updated_at) VALUES ('system_prompt', $1::jsonb, NOW())
       ON CONFLICT (key) DO UPDATE SET value = $1::jsonb, updated_at = NOW()`,
      [JSON.stringify(prompt)]
    );
    res.redirect('/admin/ai?success=prompt');
  } catch (err) {
    res.status(500).render('error', { error: err.message });
  }
});

// Toggle tool enabled/disabled
router.post('/ai/tools/:toolId/toggle', async (req, res) => {
  const { toolId } = req.params;
  try {
    await db.query(
      'UPDATE ai_tools SET enabled = NOT enabled WHERE id = $1',
      [toolId]
    );
    res.json({ success: true });
  } catch (err) {
    res.json({ error: err.message });
  }
});

// Save AI settings (max turns, tool calling enabled)
router.post('/ai/settings', async (req, res) => {
  const { max_conversation_turns, tool_calling_enabled } = req.body;
  try {
    if (max_conversation_turns !== undefined) {
      await db.query(
        `INSERT INTO ai_settings (key, value, updated_at) VALUES ('max_conversation_turns', $1::jsonb, NOW())
         ON CONFLICT (key) DO UPDATE SET value = $1::jsonb, updated_at = NOW()`,
        [JSON.stringify(parseInt(max_conversation_turns, 10) || 50)]
      );
    }
    if (tool_calling_enabled !== undefined) {
      await db.query(
        `INSERT INTO ai_settings (key, value, updated_at) VALUES ('tool_calling_enabled', $1::jsonb, NOW())
         ON CONFLICT (key) DO UPDATE SET value = $1::jsonb, updated_at = NOW()`,
        [JSON.stringify(tool_calling_enabled === 'true')]
      );
    }
    res.redirect('/admin/ai?success=settings');
  } catch (err) {
    res.status(500).render('error', { error: err.message });
  }
});

module.exports = router;
