// SCOUT — Test Scripts Routes
// Browse, view, and edit Playwright test files.

const router = require('express').Router();
const path = require('path');
const fs = require('fs');
const db = require('../../db');

const TESTS_DIR = path.resolve(__dirname, '../../../tests');

// Cache scanned test files (30s TTL)
let testCache = null;
let testCacheTime = 0;
const CACHE_TTL = 30000;

function getTestScripts() {
  const now = Date.now();
  if (testCache && now - testCacheTime < CACHE_TTL) return testCache;

  const cases = [];

  function scanDir(dir, prefix) {
    prefix = prefix || '';
    if (!fs.existsSync(dir)) return;
    var entries = fs.readdirSync(dir, { withFileTypes: true });

    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      if (entry.isDirectory()) {
        scanDir(path.join(dir, entry.name), prefix ? prefix + '/' + entry.name : entry.name);
        continue;
      }
      if (!entry.name.endsWith('.spec.js')) continue;

      var filePath = path.join(dir, entry.name);
      var relativePath = prefix ? prefix + '/' + entry.name : entry.name;
      var content = fs.readFileSync(filePath, 'utf-8');

      var testMatches = content.match(/\btest\s*\(/g) || [];
      var testCount = testMatches.length;

      var type = 'feature';
      var typeLabel = 'Feature';
      if (relativePath.includes('visual-regression') || content.includes('@visual')) {
        type = 'visual'; typeLabel = 'Visual Regression';
      } else if (relativePath.includes('content-validation') || content.includes('@content')) {
        type = 'content'; typeLabel = 'Content Validation';
      }

      var source = relativePath.includes('generated') ? 'ai' : 'manual';

      var describeMatch = content.match(/test\.describe\s*\(\s*['"`]([^'"`]+)/);
      var name = describeMatch ? describeMatch[1] : entry.name.replace('.spec.js', '');

      cases.push({ name, type, typeLabel, source, testCount, relativePath });
    }
  }

  scanDir(TESTS_DIR);
  testCache = cases;
  testCacheTime = now;
  return cases;
}

// Server-side API for paginated, sorted, filtered list
router.get('/api/list', async (req, res) => {
  try {
    var all = getTestScripts();
    var search = (req.query.search || '').toLowerCase().trim();
    var typeFilter = req.query.type || '';
    var sourceFilter = req.query.source || '';

    // Filter
    var filtered = all.filter(function(tc) {
      if (typeFilter && tc.type !== typeFilter) return false;
      if (sourceFilter && tc.source !== sourceFilter) return false;
      if (search && tc.name.toLowerCase().indexOf(search) === -1 && tc.relativePath.toLowerCase().indexOf(search) === -1) return false;
      return true;
    });

    // Sort
    var sort = req.query.sort || 'name';
    var dir = req.query.dir === 'desc' ? -1 : 1;
    var validSorts = { name: 'name', type: 'type', tests: 'testCount', file: 'relativePath', source: 'source' };
    var sortKey = validSorts[sort] || 'name';
    filtered.sort(function(a, b) {
      var av = a[sortKey]; var bv = b[sortKey];
      if (sortKey === 'testCount') return dir * (av - bv);
      av = (av || '').toLowerCase(); bv = (bv || '').toLowerCase();
      if (av < bv) return -dir;
      if (av > bv) return dir;
      return 0;
    });

    // Paginate
    var page = Math.max(1, parseInt(req.query.page) || 1);
    var pageSize = Math.min(500, Math.max(1, parseInt(req.query.pageSize) || 25));
    var total = filtered.length;
    var start = (page - 1) * pageSize;
    var rows = filtered.slice(start, start + pageSize);

    res.json({ rows, total, page, pageSize });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// List page
router.get('/', async (req, res) => {
  try {
    var result = await db.query(
      'SELECT a.id, a.name, e.name AS env_name FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id ORDER BY e.name, a.name'
    );
    res.render('test-cases', { assessments: result.rows });
  } catch (err) {
    res.render('test-cases', { assessments: [], error: err.message });
  }
});

// Delete a test script (registry entry + optionally file from disk)
router.delete('/script', async (req, res) => {
  var scriptPath = req.body.scriptPath;
  if (!scriptPath) return res.status(400).json({ error: 'scriptPath required' });
  try {
    // Remove from registry
    await db.query('DELETE FROM test_scripts WHERE script_path = $1', [scriptPath]);

    // Delete file from disk if it exists
    var fullPath = path.resolve(TESTS_DIR, scriptPath);
    if (fullPath.startsWith(TESTS_DIR) && fs.existsSync(fullPath)) {
      fs.unlinkSync(fullPath);
    }

    // Invalidate cache
    testCache = null;

    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// View/edit a specific test script — redirect to builder
router.get(/^\/(.+)$/, (req, res) => {
  const relativePath = req.params[0];
  res.redirect('/builder?file=' + encodeURIComponent(relativePath));
});

module.exports = router;
