// SCOUT — Items Routes (storyboard)
const router = require('express').Router();
const db = require('../../db');
const queries = require('../../db/queries');

// Server-side paginated API
router.get('/api/list', async (req, res) => {
  try {
    var page = Math.max(1, parseInt(req.query.page) || 1);
    var pageSize = Math.min(500, Math.max(1, parseInt(req.query.pageSize) || 25));
    var search = (req.query.search || '').trim();
    var envFilter = (req.query.env || '').trim();
    var assessFilter = (req.query.assessment || '').trim();
    var sort = req.query.sort || 'numeric_id';
    var dir = req.query.dir === 'desc' ? 'DESC' : 'ASC';

    var validSorts = { numeric_id: 'i.numeric_id', id: 'i.id', title: 'i.title', category: 'i.category', tier: 'i.tier', version: 'i.active_version', assessment: 'a.name', env: 'e.name' };
    var orderCol = validSorts[sort] || 'i.numeric_id';

    var where = [];
    var params = [];
    if (search) {
      params.push('%' + search.toLowerCase() + '%');
      var idx = params.length;
      where.push('(LOWER(i.id) LIKE $' + idx + ' OR LOWER(i.title) LIKE $' + idx + ' OR LOWER(a.name) LIKE $' + idx + ')');
    }
    if (envFilter) {
      params.push(envFilter);
      where.push('a.environment_id = $' + params.length);
    }
    if (assessFilter) {
      params.push(assessFilter);
      where.push('i.assessment_id = $' + params.length);
    }

    var whereClause = where.length ? 'WHERE ' + where.join(' AND ') : '';
    var joinClause = 'LEFT JOIN assessments a ON i.assessment_id = a.id LEFT JOIN environments e ON a.environment_id = e.id';

    var countResult = await db.query('SELECT COUNT(*) FROM items i ' + joinClause + ' ' + whereClause, params);
    var total = parseInt(countResult.rows[0].count);

    var offset = (page - 1) * pageSize;
    var rowParams = params.slice();
    rowParams.push(pageSize);
    rowParams.push(offset);

    var sql = 'SELECT i.numeric_id, i.id, i.title, i.category, i.tier, i.languages, i.active_version, i.assessment_id, ' +
      'a.name AS assessment_name, e.name AS env_name ' +
      'FROM items i ' + joinClause + ' ' + whereClause +
      ' ORDER BY ' + orderCol + ' ' + dir + ' NULLS LAST' +
      ' LIMIT $' + (rowParams.length - 1) + ' OFFSET $' + rowParams.length;

    var result = await db.query(sql, rowParams);
    res.json({ rows: result.rows, total: total, page: page, pageSize: pageSize });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Item detail page (by numeric ID)
router.get('/:numericId', async (req, res, next) => {
  var numericId = parseInt(req.params.numericId, 10);
  if (isNaN(numericId) || numericId < 1) return next();
  try {
    var itemResult = await db.query(
      'SELECT i.*, a.name AS assessment_name, e.name AS env_name FROM items i LEFT JOIN assessments a ON i.assessment_id = a.id LEFT JOIN environments e ON a.environment_id = e.id WHERE i.numeric_id = $1',
      [numericId]
    );
    if (itemResult.rows.length === 0) {
      return res.status(404).render('error', { error: 'Item not found' });
    }
    var item = itemResult.rows[0];

    // Find test scripts directly associated with this item
    var scriptsResult = await db.query(
      `SELECT ts.script_path, ts.category, ts.description,
              COUNT(DISTINCT trs.run_id) AS run_count,
              COUNT(*) FILTER (WHERE trs.status = 'passed') AS passed,
              COUNT(*) FILTER (WHERE trs.status = 'failed') AS failed,
              MAX(trs.completed_at) AS last_run
       FROM test_scripts ts
       LEFT JOIN test_run_scripts trs ON trs.script_path = ts.script_path
       WHERE ts.item_id = $1
       GROUP BY ts.script_path, ts.category, ts.description
       ORDER BY ts.script_path`,
      [item.id]
    );

    // Also find scripts that tested this item via runs (indirect link)
    var indirectResult = await db.query(
      `SELECT DISTINCT trs.script_path,
              COUNT(DISTINCT trs.run_id) AS run_count,
              COUNT(*) FILTER (WHERE trs.status = 'passed') AS passed,
              COUNT(*) FILTER (WHERE trs.status = 'failed') AS failed,
              MAX(trs.completed_at) AS last_run
       FROM test_run_scripts trs
       JOIN test_results tr ON tr.run_id = trs.run_id
       WHERE tr.item_id = $1
         AND trs.script_path NOT IN (SELECT script_path FROM test_scripts WHERE item_id = $1)
       GROUP BY trs.script_path
       ORDER BY last_run DESC NULLS LAST`,
      [item.id]
    );

    var allScripts = scriptsResult.rows.concat(indirectResult.rows);

    res.render('item-detail', { item, scripts: allScripts });
  } catch (err) {
    res.status(500).render('error', { error: err.message });
  }
});

// Delete item (cascades to results, analyses, baselines, reviews)
router.delete('/:numericId', async (req, res) => {
  var numericId = parseInt(req.params.numericId, 10);
  if (isNaN(numericId) || numericId < 1) return res.status(400).json({ error: 'Invalid ID' });
  try {
    var item = await db.query('SELECT id FROM items WHERE numeric_id = $1', [numericId]);
    if (item.rows.length === 0) return res.status(404).json({ error: 'Item not found' });
    var itemId = item.rows[0].id;

    await db.query('BEGIN');
    await db.query('DELETE FROM reviews WHERE result_id IN (SELECT id FROM test_results WHERE item_id = $1)', [itemId]);
    await db.query('DELETE FROM reviews WHERE analysis_id IN (SELECT id FROM ai_analyses WHERE item_id = $1)', [itemId]);
    await db.query('DELETE FROM test_results WHERE item_id = $1', [itemId]);
    await db.query('DELETE FROM ai_analyses WHERE item_id = $1', [itemId]);
    await db.query('DELETE FROM baselines WHERE item_id = $1', [itemId]);
    await db.query('DELETE FROM items WHERE id = $1', [itemId]);
    await db.query('COMMIT');
    res.json({ ok: true });
  } catch (err) {
    await db.query('ROLLBACK').catch(() => {});
    res.status(500).json({ error: err.message });
  }
});

router.get('/', async (req, res) => {
  const envResult = await db.query('SELECT id, name FROM environments ORDER BY is_default DESC, name');
  const asmResult = await db.query('SELECT id, name FROM assessments ORDER BY name');
  res.render('items-list', {
    environments: envResult.rows,
    assessments: asmResult.rows,
  });
});

module.exports = router;
