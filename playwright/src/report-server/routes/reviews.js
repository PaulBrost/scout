// SCOUT — Reviews Routes
const router = require('express').Router();
const db = require('../../db');

// Server-side paginated API
router.get('/api/list', async (req, res) => {
  try {
    var page = Math.max(1, parseInt(req.query.page) || 1);
    var pageSize = Math.min(500, Math.max(1, parseInt(req.query.pageSize) || 25));
    var sort = req.query.sort || 'flagged';
    var dir = req.query.dir === 'asc' ? 'ASC' : 'DESC';
    var search = (req.query.search || '').trim();
    var statusFilter = req.query.status || '';
    var typeFilter = req.query.type || '';

    var validSorts = {
      flagged: 'a.created_at', item: 'a.item_id', type: 'a.analysis_type',
      issues: 'a.issue_count', status: 'review_status'
    };
    var orderCol = validSorts[sort] || 'a.created_at';

    var where = ['a.issues_found = true'];
    var params = [];

    // Status filter: 'pending' shows unreviewed, 'reviewed' shows reviewed, '' shows all
    if (statusFilter === 'pending') {
      where.push('(rv.status IS NULL OR rv.status = \'pending\')');
    } else if (statusFilter === 'approved') {
      where.push("rv.status = 'approved'");
    } else if (statusFilter === 'dismissed') {
      where.push("rv.status = 'dismissed'");
    } else if (statusFilter === 'bug_filed') {
      where.push("rv.status = 'bug_filed'");
    }

    if (typeFilter) {
      params.push(typeFilter);
      where.push('a.analysis_type = $' + params.length);
    }
    if (search) {
      params.push('%' + search.toLowerCase() + '%');
      where.push('(LOWER(a.item_id) LIKE $' + params.length + ' OR LOWER(a.output) LIKE $' + params.length + ')');
    }

    var whereClause = 'WHERE ' + where.join(' AND ');

    var countSql = `SELECT COUNT(*) FROM ai_analyses a LEFT JOIN reviews rv ON rv.analysis_id = a.id ${whereClause}`;
    var countResult = await db.query(countSql, params);
    var total = parseInt(countResult.rows[0].count);

    var offset = (page - 1) * pageSize;
    var rowParams = params.slice();
    rowParams.push(pageSize);
    rowParams.push(offset);

    var sql = `
      SELECT a.id, a.run_id, a.item_id, a.analysis_type, a.model, a.output,
             a.issue_count, a.created_at, a.language,
             rv.id AS review_id, rv.status AS review_status, rv.reviewer, rv.notes AS review_notes, rv.reviewed_at,
             COALESCE(rv.status, 'pending') AS effective_status
      FROM ai_analyses a
      LEFT JOIN reviews rv ON rv.analysis_id = a.id
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

// Review action API (JSON)
router.post('/action', async (req, res) => {
  var { analysis_id, action, notes } = req.body;
  var reviewer = req.session?.username || 'scout';

  if (!analysis_id || !action) {
    return res.status(400).json({ error: 'analysis_id and action are required' });
  }

  var validActions = ['approved', 'dismissed', 'bug_filed'];
  if (validActions.indexOf(action) === -1) {
    return res.status(400).json({ error: 'Invalid action. Use: approved, dismissed, or bug_filed' });
  }

  try {
    // Upsert review record
    var existing = await db.query('SELECT id FROM reviews WHERE analysis_id = $1', [analysis_id]);
    if (existing.rows.length > 0) {
      await db.query(
        'UPDATE reviews SET status = $1, reviewer = $2, notes = $3, reviewed_at = now() WHERE analysis_id = $4',
        [action, reviewer, notes || null, analysis_id]
      );
    } else {
      await db.query(
        'INSERT INTO reviews (analysis_id, status, reviewer, notes, reviewed_at) VALUES ($1, $2, $3, $4, now())',
        [analysis_id, action, reviewer, notes || null]
      );
    }

    // If bug_filed, mark the associated test_result as 'failed' (if it exists and was 'passed')
    if (action === 'bug_filed') {
      var analysis = await db.query('SELECT run_id, item_id FROM ai_analyses WHERE id = $1', [analysis_id]);
      if (analysis.rows.length > 0) {
        var a = analysis.rows[0];
        await db.query(
          "UPDATE test_results SET status = 'failed' WHERE run_id = $1 AND item_id = $2 AND status = 'passed'",
          [a.run_id, a.item_id]
        );
      }
    }

    // Accept content type header to decide response format
    if (req.headers.accept && req.headers.accept.indexOf('application/json') >= 0) {
      res.json({ ok: true, action });
    } else {
      res.redirect('/reviews');
    }
  } catch (err) {
    if (req.headers.accept && req.headers.accept.indexOf('application/json') >= 0) {
      res.status(500).json({ error: err.message });
    } else {
      res.status(500).render('error', { error: err.message });
    }
  }
});

// Review queue page
router.get('/', async (req, res) => {
  try {
    res.render('reviews', {});
  } catch (err) {
    res.render('reviews', { error: err.message });
  }
});

module.exports = router;
