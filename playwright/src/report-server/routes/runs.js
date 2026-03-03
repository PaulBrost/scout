// SCOUT — Runs Routes
const router = require('express').Router();
const db = require('../../db');
const queries = require('../../db/queries');

// Server-side API for paginated, sorted, filtered list
router.get('/api/list', async (req, res) => {
  try {
    var page = Math.max(1, parseInt(req.query.page) || 1);
    var pageSize = Math.min(500, Math.max(1, parseInt(req.query.pageSize) || 25));
    var sort = req.query.sort || 'started';
    var dir = req.query.dir === 'asc' ? 'ASC' : 'DESC';
    var statusFilter = req.query.status || '';
    var triggerFilter = req.query.trigger || '';
    var search = (req.query.search || '').trim();

    var validSorts = {
      started: 'r.started_at', status: 'r.status', trigger: 'r.trigger_type', suite: 's.name'
    };
    var orderCol = validSorts[sort] || 'r.started_at';

    var where = [];
    var params = [];
    if (statusFilter) {
      params.push(statusFilter);
      where.push('r.status = $' + params.length);
    }
    if (triggerFilter) {
      params.push(triggerFilter);
      where.push('r.trigger_type = $' + params.length);
    }
    if (search) {
      params.push('%' + search.toLowerCase() + '%');
      where.push('(LOWER(r.notes) LIKE $' + params.length + ' OR LOWER(s.name) LIKE $' + params.length + ')');
    }

    var whereClause = where.length ? 'WHERE ' + where.join(' AND ') : '';

    var countResult = await db.query(
      'SELECT COUNT(*) FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id ' + whereClause, params
    );
    var total = parseInt(countResult.rows[0].count);

    var offset = (page - 1) * pageSize;
    var rowParams = params.slice();
    rowParams.push(pageSize);
    rowParams.push(offset);

    var sql = `
      SELECT r.id, r.started_at, r.completed_at, r.status, r.trigger_type, r.summary, r.notes,
        s.id AS suite_id, s.name AS suite_name,
        (SELECT COUNT(*) FROM test_run_scripts rs WHERE rs.run_id = r.id) AS script_count
      FROM test_runs r
      LEFT JOIN test_suites s ON r.suite_id = s.id
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

// List all runs
router.get('/', async (req, res) => {
  try {
    res.render('runs', {});
  } catch (err) {
    res.render('runs', { error: err.message });
  }
});

// Script result detail (for log/error modal)
router.get('/:runId/script/:scriptId', async (req, res) => {
  try {
    const result = await db.query(
      'SELECT * FROM test_run_scripts WHERE run_id = $1 AND id = $2',
      [req.params.runId, req.params.scriptId]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'Script result not found' });
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Run detail
router.get('/:id', async (req, res) => {
  try {
    const runResult = await db.query(
      `SELECT r.*, s.name AS suite_name, s.id AS suite_id
       FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id
       WHERE r.id = $1`, [req.params.id]
    );
    if (runResult.rows.length === 0) {
      return res.status(404).render('error', { error: 'Run not found' });
    }
    const run = runResult.rows[0];

    // Per-script results from test_run_scripts
    const scriptResults = await db.query(
      'SELECT * FROM test_run_scripts WHERE run_id = $1 ORDER BY completed_at DESC NULLS LAST, script_path',
      [run.id]
    );

    // Legacy per-item results (from older runs)
    const resultsResult = await db.query(
      'SELECT tr.*, i.numeric_id AS item_numeric_id FROM test_results tr LEFT JOIN items i ON i.id = tr.item_id WHERE tr.run_id = $1 ORDER BY tr.item_id, tr.browser',
      [run.id]
    );

    const analysesResult = await db.query(
      'SELECT * FROM ai_analyses WHERE run_id = $1 ORDER BY item_id',
      [run.id]
    );

    let summary = run.summary;
    if (typeof summary === 'string') try { summary = JSON.parse(summary); } catch(e) { summary = null; }
    if (!summary) {
      try { summary = await queries.getRunSummary(run.id); } catch(e) { summary = null; }
    }

    res.render('run-detail', {
      run,
      summary: summary || {},
      scriptResults: scriptResults.rows,
      results: resultsResult.rows,
      analyses: analysesResult.rows,
    });
  } catch (err) {
    res.status(500).render('error', { error: err.message });
  }
});

module.exports = router;
