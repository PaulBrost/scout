// SCOUT — Dashboard Route
const router = require('express').Router();
const db = require('../../db');
const queries = require('../../db/queries');

router.get('/', async (req, res) => {
  try {
    // Get latest run
    const runsResult = await db.query(
      'SELECT * FROM test_runs ORDER BY started_at DESC LIMIT 1'
    );
    const latestRun = runsResult.rows[0] || null;

    // Get summary for latest run
    let stats = null;
    if (latestRun) {
      stats = await queries.getRunSummary(latestRun.id);
    }

    // Get pass rate trend
    const trend = await queries.getPassRateTrend(10);

    // Get pending AI flags
    const aiFlags = await queries.getPendingAIFlags();

    // Get 5 most recent runs with suite info
    const recentRunsResult = await db.query(`
      SELECT r.id, r.started_at, r.status, r.trigger_type, r.summary,
        s.name AS suite_name
      FROM test_runs r
      LEFT JOIN test_suites s ON r.suite_id = s.id
      ORDER BY r.started_at DESC LIMIT 5
    `);
    const recentRuns = recentRunsResult.rows;

    res.render('dashboard', { latestRun, stats, trend, aiFlags, recentRuns });
  } catch (err) {
    console.error('Dashboard error:', err.message);
    res.render('dashboard', { latestRun: null, stats: null, trend: [], aiFlags: [], recentRuns: [] });
  }
});

module.exports = router;
