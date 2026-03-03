// SCOUT — Pre-built Analytical Queries
// Commonly used queries for result analysis and dashboard.

const db = require('./index');

/**
 * Get new failures — items that failed in the latest run but passed in the previous.
 */
async function getNewFailures() {
  const result = await db.query(`
    WITH latest AS (
      SELECT id FROM test_runs WHERE status = 'completed' ORDER BY started_at DESC LIMIT 1
    ), previous AS (
      SELECT id FROM test_runs WHERE status = 'completed' ORDER BY started_at DESC OFFSET 1 LIMIT 1
    )
    SELECT curr.item_id, curr.browser, curr.diff_pixel_ratio, curr.error_message
    FROM test_results curr
    JOIN latest ON curr.run_id = latest.id
    JOIN test_results prev ON prev.item_id = curr.item_id
        AND prev.browser = curr.browser
        AND prev.device_profile = curr.device_profile
    JOIN previous ON prev.run_id = previous.id
    WHERE curr.status = 'failed' AND prev.status = 'passed'
    ORDER BY curr.item_id, curr.browser
  `);
  return result.rows;
}

/**
 * Get items that fail in one browser but pass in another.
 * @param {string} runId
 */
async function getCrossBrowserFailures(runId) {
  const result = await db.query(`
    SELECT f.item_id, f.browser AS failed_in, p.browser AS passed_in
    FROM test_results f
    JOIN test_results p ON f.run_id = p.run_id AND f.item_id = p.item_id
    WHERE f.run_id = $1
      AND f.status = 'failed'
      AND p.status = 'passed'
    ORDER BY f.item_id
  `, [runId]);
  return result.rows;
}

/**
 * Get pass rate trend over the last N runs.
 * @param {number} limit
 */
async function getPassRateTrend(limit = 10) {
  const result = await db.query(`
    SELECT r.id, r.started_at,
           COUNT(*) FILTER (WHERE tr.status = 'passed') AS passed,
           COUNT(*) FILTER (WHERE tr.status = 'failed') AS failed,
           COUNT(*) AS total,
           ROUND(100.0 * COUNT(*) FILTER (WHERE tr.status = 'passed') / NULLIF(COUNT(*), 0), 1) AS pass_pct
    FROM test_runs r
    JOIN test_results tr ON tr.run_id = r.id
    WHERE r.status = 'completed'
    GROUP BY r.id, r.started_at
    ORDER BY r.started_at DESC
    LIMIT $1
  `, [limit]);
  return result.rows;
}

/**
 * Get all AI-flagged items pending review.
 */
async function getPendingAIFlags() {
  const result = await db.query(`
    SELECT a.item_id, a.analysis_type, a.model, a.output, a.issue_count,
           a.created_at, rv.status AS review_status
    FROM ai_analyses a
    LEFT JOIN reviews rv ON rv.analysis_id = a.id
    WHERE a.issues_found = true
      AND (rv.status IS NULL OR rv.status = 'pending')
    ORDER BY a.created_at DESC
  `);
  return result.rows;
}

/**
 * Get full history for a specific item across all runs.
 * @param {string} itemId
 */
async function getItemHistory(itemId) {
  const result = await db.query(`
    SELECT tr.run_id, r.started_at, tr.browser, tr.device_profile,
           tr.status, tr.diff_pixel_ratio, tr.duration_ms
    FROM test_results tr
    JOIN test_runs r ON r.id = tr.run_id
    WHERE tr.item_id = $1
    ORDER BY r.started_at DESC, tr.browser
  `, [itemId]);
  return result.rows;
}

/**
 * Get run summary with counts.
 * @param {string} runId
 */
async function getRunSummary(runId) {
  const result = await db.query(`
    SELECT
      COUNT(*) AS total,
      COUNT(*) FILTER (WHERE status = 'passed') AS passed,
      COUNT(*) FILTER (WHERE status = 'failed') AS failed,
      COUNT(*) FILTER (WHERE status = 'skipped') AS skipped,
      COUNT(*) FILTER (WHERE status = 'error') AS errors,
      COUNT(DISTINCT item_id) AS items_tested,
      COUNT(DISTINCT browser) AS browsers_tested
    FROM test_results
    WHERE run_id = $1
  `, [runId]);
  return result.rows[0];
}

module.exports = {
  getNewFailures,
  getCrossBrowserFailures,
  getPassRateTrend,
  getPendingAIFlags,
  getItemHistory,
  getRunSummary,
};
