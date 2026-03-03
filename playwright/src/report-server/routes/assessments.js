// SCOUT — Assessments Routes
// Lists assessment forms and their related test cases.
// Reads assessment data from the database (linked to environments).

const router = require('express').Router();
const path = require('path');
const fs = require('fs');
const db = require('../../db');

const TESTS_DIR = path.resolve(__dirname, '../../../tests');

// Cache test scan results (refreshed on page load, not per-row)
var _testCache = null;
var _testCacheTime = 0;
function getTestCache() {
  if (_testCache && Date.now() - _testCacheTime < 30000) return _testCache;
  _testCache = {};
  if (!fs.existsSync(TESTS_DIR)) return _testCache;
  function scan(dir, prefix) {
    var entries = fs.readdirSync(dir, { withFileTypes: true });
    for (var entry of entries) {
      if (entry.isDirectory()) { scan(path.join(dir, entry.name), prefix ? prefix + '/' + entry.name : entry.name); continue; }
      if (!entry.name.endsWith('.spec.js')) continue;
      var content = fs.readFileSync(path.join(dir, entry.name), 'utf-8');
      var rp = prefix ? prefix + '/' + entry.name : entry.name;
      var descMatch = content.match(/test\.describe\s*\(\s*['"`]([^'"`]+)/);
      var testCount = (content.match(/\btest\s*\(/g) || []).length;
      var info = { name: descMatch ? descMatch[1] : entry.name.replace('.spec.js', ''), relativePath: rp, testCount: testCount };
      // Index by every form key mentioned
      var formMatches = content.match(/['"]cra-form[1-4]['"]|['"]math-fluency['"]|['"]naep-id-(?:4|8)th['"]/g) || [];
      formMatches.forEach(function(m) { var k = m.replace(/['"]/g, ''); if (!_testCache[k]) _testCache[k] = []; _testCache[k].push(info); });
      if (content.includes('startTestSession') || content.includes('loginAndStartTest')) {
        if (!_testCache['cra-form1']) _testCache['cra-form1'] = [];
        if (!_testCache['cra-form1'].find(function(t) { return t.relativePath === rp; })) _testCache['cra-form1'].push(info);
      }
    }
  }
  scan(TESTS_DIR, '');
  _testCacheTime = Date.now();
  return _testCache;
}

// Allowed sort columns mapped to SQL expressions
const SORT_MAP = {
  name: 'a.name',
  subject: 'a.subject',
  grade: 'a.grade',
  year: 'a.year',
  items: 'a.item_count',
  env: 'e.name',
};

// Server-side paginated API
router.get('/api/list', async (req, res) => {
  var page = Math.max(1, parseInt(req.query.page) || 1);
  var pageSize = Math.min(500, Math.max(1, parseInt(req.query.pageSize) || 25));
  var search = (req.query.search || '').trim();
  var envFilter = (req.query.env || '').trim();
  var sortCol = SORT_MAP[req.query.sort] || 'a.name';
  var sortDir = req.query.dir === 'desc' ? 'DESC' : 'ASC';

  var whereClauses = [];
  var params = [];
  if (search) {
    params.push('%' + search + '%');
    var idx = params.length;
    whereClauses.push('(a.name ILIKE $' + idx + ' OR a.subject ILIKE $' + idx + ' OR a.grade ILIKE $' + idx + ' OR a.year ILIKE $' + idx + ' OR e.name ILIKE $' + idx + ')');
  }
  if (envFilter) {
    params.push(envFilter);
    whereClauses.push('a.environment_id = $' + params.length);
  }
  var where = whereClauses.length ? 'WHERE ' + whereClauses.join(' AND ') : '';

  // Count
  var countResult = await db.query('SELECT count(*) FROM assessments a JOIN environments e ON a.environment_id = e.id ' + where, params);
  var total = parseInt(countResult.rows[0].count);

  // Data
  var offset = (page - 1) * pageSize;
  var dataParams = params.slice();
  dataParams.push(pageSize);
  dataParams.push(offset);
  var dataResult = await db.query(
    'SELECT a.id, a.name, a.subject, a.grade, a.year, a.item_count, e.name AS env_name ' +
    'FROM assessments a JOIN environments e ON a.environment_id = e.id ' +
    where + ' ORDER BY ' + sortCol + ' ' + sortDir + ' NULLS LAST ' +
    'LIMIT $' + (dataParams.length - 1) + ' OFFSET $' + dataParams.length,
    dataParams
  );

  // Attach test counts from cache
  var cache = getTestCache();
  var rows = dataResult.rows.map(function(r) {
    var tests = cache[r.id] || [];
    return { id: r.id, name: r.name, subject: r.subject, grade: r.grade, year: r.year, item_count: r.item_count, env_name: r.env_name, test_count: tests.length };
  });

  res.json({ rows: rows, total: total, page: page, pageSize: pageSize });
});

// List page (renders shell, data loaded via JS)
router.get('/', async (req, res) => {
  var envResult = await db.query('SELECT id, name FROM environments ORDER BY is_default DESC, name');
  res.render('assessments', { environments: envResult.rows });
});

// Assessment detail
router.get('/:id', async (req, res) => {
  const result = await db.query(`
    SELECT a.*, e.name AS env_name, e.base_url AS env_url, e.id AS env_id
    FROM assessments a
    JOIN environments e ON a.environment_id = e.id
    WHERE a.id = $1
  `, [req.params.id]);
  if (result.rows.length === 0) {
    return res.status(404).render('error', { error: 'Assessment not found' });
  }
  var assessment = result.rows[0];
  assessment.itemCount = assessment.item_count;
  var cache = getTestCache();
  var testCases = cache[assessment.id] || [];
  res.render('assessment-detail', { assessment, testCases });
});

// Delete assessment (cascades to items, results, analyses, baselines, reviews)
router.delete('/:id', async (req, res) => {
  try {
    var check = await db.query('SELECT id FROM assessments WHERE id = $1', [req.params.id]);
    if (check.rows.length === 0) return res.status(404).json({ error: 'Assessment not found' });

    await db.query('BEGIN');
    // Cascade through items belonging to this assessment
    await db.query('DELETE FROM reviews WHERE result_id IN (SELECT tr.id FROM test_results tr JOIN items i ON tr.item_id = i.id WHERE i.assessment_id = $1)', [req.params.id]);
    await db.query('DELETE FROM reviews WHERE analysis_id IN (SELECT aa.id FROM ai_analyses aa JOIN items i ON aa.item_id = i.id WHERE i.assessment_id = $1)', [req.params.id]);
    await db.query('DELETE FROM test_results WHERE item_id IN (SELECT id FROM items WHERE assessment_id = $1)', [req.params.id]);
    await db.query('DELETE FROM ai_analyses WHERE item_id IN (SELECT id FROM items WHERE assessment_id = $1)', [req.params.id]);
    await db.query('DELETE FROM baselines WHERE item_id IN (SELECT id FROM items WHERE assessment_id = $1)', [req.params.id]);
    await db.query('DELETE FROM items WHERE assessment_id = $1', [req.params.id]);
    // test_scripts.assessment_id SET NULL handled by FK
    await db.query('DELETE FROM assessments WHERE id = $1', [req.params.id]);
    await db.query('COMMIT');
    res.json({ ok: true });
  } catch (err) {
    await db.query('ROLLBACK').catch(() => {});
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
