// SCOUT — Test Builder Routes
const router = require('express').Router();
const path = require('path');
const fs = require('fs');
const db = require('../../db');

const TESTS_DIR = path.resolve(__dirname, '../../../tests');

router.get('/', async (req, res) => {
  let fileContent = null;
  let filePath = null;
  let filename = null;
  let assessment = null;
  let scriptMeta = null;
  let runHistory = [];

  // If ?file= param is provided, load that test for editing
  if (req.query.file) {
    filePath = req.query.file;
    const fullPath = path.resolve(TESTS_DIR, filePath);

    // Security: ensure path stays within tests directory
    if (fullPath.startsWith(TESTS_DIR) && fs.existsSync(fullPath)) {
      fileContent = fs.readFileSync(fullPath, 'utf-8');
      filename = path.basename(filePath);
    }

    // Load script metadata (associations)
    try {
      var metaResult = await db.query(
        `SELECT ts.*, i.title AS item_title, i.numeric_id AS item_numeric_id,
                a.name AS assessment_name
         FROM test_scripts ts
         LEFT JOIN items i ON ts.item_id = i.id
         LEFT JOIN assessments a ON ts.assessment_id = a.id
         WHERE ts.script_path = $1`,
        [filePath]
      );
      if (metaResult.rows.length > 0) {
        scriptMeta = metaResult.rows[0];
      }
    } catch (e) { /* script not registered yet */ }

    // Load run history for this script
    try {
      var histResult = await db.query(
        `SELECT trs.id, trs.run_id, trs.status, trs.duration_ms, trs.error_message,
                trs.completed_at, trs.trace_path, trs.video_path,
                r.trigger_type, r.suite_id,
                s.name AS suite_name
         FROM test_run_scripts trs
         JOIN test_runs r ON r.id = trs.run_id
         LEFT JOIN test_suites s ON r.suite_id = s.id
         WHERE trs.script_path = $1
         ORDER BY trs.completed_at DESC NULLS LAST
         LIMIT 50`,
        [filePath]
      );
      runHistory = histResult.rows;
    } catch (e) { /* no history */ }
  }

  // Load associated assessment if provided (from query param or script metadata)
  var assessmentId = req.query.assessment || (scriptMeta && scriptMeta.assessment_id);
  if (assessmentId) {
    try {
      var result = await db.query(
        `SELECT a.id, a.name, a.subject, a.grade, e.name AS env_name
         FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id
         WHERE a.id = $1`, [assessmentId]
      );
      if (result.rows.length > 0) assessment = result.rows[0];
    } catch (e) { console.error('Builder assessment lookup error:', e.message); }
  }

  // Load items and assessments for association dropdowns
  var items = [];
  var assessments = [];
  try {
    var itemsResult = await db.query('SELECT numeric_id, id, title FROM items ORDER BY numeric_id');
    items = itemsResult.rows;
    var assResult = await db.query('SELECT id, name FROM assessments ORDER BY name');
    assessments = assResult.rows;
  } catch (e) { /* optional */ }

  var testType = req.query.type || null;
  var baselineVersion = req.query.baseline || null;

  res.render('builder', {
    fileContent, filePath, filename, assessment, testType, baselineVersion,
    scriptMeta, runHistory, items, assessments,
  });
});

module.exports = router;
