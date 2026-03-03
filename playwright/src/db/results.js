// SCOUT — Test Result Recording
// Functions for writing test execution data to PostgreSQL.

const db = require('./index');

/**
 * Create a new test run record.
 * @param {object} options
 * @param {string} options.trigger - 'manual' | 'scheduled' | 'ci' | 'dashboard'
 * @param {object} options.config - Run configuration (browsers, items, baseline version)
 * @returns {Promise<string>} The new run ID
 */
async function createTestRun({ trigger = 'manual', config = {} } = {}) {
  const result = await db.query(
    `INSERT INTO test_runs (trigger_type, config) VALUES ($1, $2) RETURNING id`,
    [trigger, JSON.stringify(config)]
  );
  return result.rows[0].id;
}

/**
 * Record a single test result (one item × browser × device).
 * @param {string} runId - The test run ID
 * @param {object} result - Test result data
 */
async function recordTestResult(runId, result) {
  // Ensure the item exists in the registry
  await db.query(
    `INSERT INTO items (id, tier) VALUES ($1, 'smoke')
     ON CONFLICT (id) DO NOTHING`,
    [result.itemId]
  );

  await db.query(
    `INSERT INTO test_results (run_id, item_id, browser, device_profile, status, diff_pixel_ratio, screenshot_path, diff_image_path, duration_ms, error_message, ai_status)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
    [
      runId,
      result.itemId,
      result.browser,
      result.deviceProfile || 'desktop',
      result.status,
      result.diffPixelRatio || null,
      result.screenshotPath || null,
      result.diffImagePath || null,
      result.durationMs || null,
      result.errorMessage || null,
      result.aiStatus || 'none',
    ]
  );
}

/**
 * Record an AI analysis result.
 * @param {string} runId - The test run ID
 * @param {object} analysis - AI analysis data
 */
async function recordAIAnalysis(runId, analysis) {
  await db.query(
    `INSERT INTO ai_analyses (run_id, item_id, analysis_type, model, language, input_summary, output, issues_found, issue_count, duration_ms)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
    [
      runId,
      analysis.itemId,
      analysis.analysisType,
      analysis.model,
      analysis.language || null,
      analysis.inputSummary || null,
      analysis.output,
      analysis.issuesFound,
      analysis.issueCount || 0,
      analysis.durationMs || null,
    ]
  );
}

/**
 * Mark a test run as completed and store the summary.
 * @param {string} runId
 * @param {object} summary - Pass/fail counts, duration, etc.
 */
async function completeTestRun(runId, summary) {
  await db.query(
    `UPDATE test_runs SET status = $1, completed_at = now(), summary = $2 WHERE id = $3`,
    [summary.status || 'completed', JSON.stringify(summary), runId]
  );
}

/**
 * Get a test run with basic info.
 * @param {string} runId
 */
async function getTestRun(runId) {
  const result = await db.query(`SELECT * FROM test_runs WHERE id = $1`, [runId]);
  return result.rows[0] || null;
}

/**
 * Get the most recent test runs.
 * @param {number} limit
 */
async function getLatestRuns(limit = 10) {
  const result = await db.query(
    `SELECT * FROM test_runs ORDER BY started_at DESC LIMIT $1`,
    [limit]
  );
  return result.rows;
}

module.exports = {
  createTestRun,
  recordTestResult,
  recordAIAnalysis,
  completeTestRun,
  getTestRun,
  getLatestRuns,
};
