// SCOUT — Async AI Worker
// Polls the database for test results with ai_status='pending_ai',
// runs AI analysis (text and/or vision), and writes results back.
// Designed to run as a standalone process or Docker container.

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../../.env') });

const db = require('../db');
const ai = require('../ai');
const fs = require('fs');

const POLL_INTERVAL = parseInt(process.env.AI_WORKER_POLL_INTERVAL || '5000', 10);
const BATCH_SIZE = parseInt(process.env.AI_WORKER_BATCH_SIZE || '5', 10);
const SHUTDOWN_TIMEOUT = 10000;

let running = true;

/**
 * Claim a batch of pending items for processing (atomic via UPDATE ... RETURNING).
 */
async function claimBatch() {
  const result = await db.query(`
    UPDATE test_results
    SET ai_status = 'analyzing'
    WHERE id IN (
      SELECT id FROM test_results
      WHERE ai_status = 'pending_ai'
      ORDER BY created_at ASC
      LIMIT $1
      FOR UPDATE SKIP LOCKED
    )
    RETURNING id, run_id, item_id, browser, device_profile, screenshot_path
  `, [BATCH_SIZE]);
  return result.rows;
}

/**
 * Run text analysis on the extracted text for an item.
 */
async function analyzeTextForItem(item, runId) {
  // The test result may have stored the extracted text in error_message or
  // we need to look at ai_analyses for previously captured input_summary.
  // For now, use item_id to query any previously stored text or skip.
  const existingText = await db.query(`
    SELECT input_summary FROM ai_analyses
    WHERE item_id = $1 AND analysis_type = 'text'
    ORDER BY created_at DESC LIMIT 1
  `, [item.item_id]);

  if (existingText.rows.length === 0) {
    // No text captured for this item yet — skip text analysis
    return null;
  }

  const text = existingText.rows[0].input_summary;
  if (!text || text.trim().length === 0) return null;

  try {
    const result = await ai.analyzeText(text);
    await db.query(`
      INSERT INTO ai_analyses (run_id, item_id, analysis_type, model, language, input_summary, output, issues_found, issue_count, duration_ms)
      VALUES ($1, $2, 'text', $3, 'English', $4, $5, $6, $7, $8)
    `, [
      runId, item.item_id, result.model, text.substring(0, 500),
      result.raw, result.issuesFound, result.issues.length, result.durationMs,
    ]);
    return result;
  } catch (err) {
    console.error(`  ✗ Text analysis failed for ${item.item_id}: ${err.message}`);
    return null;
  }
}

/**
 * Run vision analysis on the screenshot for an item.
 */
async function analyzeScreenshotForItem(item, runId) {
  if (!item.screenshot_path) return null;

  // Try to read the screenshot file
  let screenshotBuffer;
  try {
    screenshotBuffer = fs.readFileSync(item.screenshot_path);
  } catch {
    // Screenshot path might be relative — try common locations
    const alternatives = [
      path.resolve(__dirname, '../../', item.screenshot_path),
      path.resolve(__dirname, '../../baselines', item.screenshot_path),
      path.resolve(__dirname, '../../test-results', item.screenshot_path),
    ];
    for (const alt of alternatives) {
      try {
        screenshotBuffer = fs.readFileSync(alt);
        break;
      } catch { /* try next */ }
    }
  }

  if (!screenshotBuffer) {
    console.warn(`  ⚠ Screenshot not found for ${item.item_id}: ${item.screenshot_path}`);
    return null;
  }

  try {
    const context = `Assessment item ${item.item_id}, browser: ${item.browser}, device: ${item.device_profile}`;
    const result = await ai.analyzeScreenshot(screenshotBuffer, context);
    await db.query(`
      INSERT INTO ai_analyses (run_id, item_id, analysis_type, model, input_summary, output, issues_found, issue_count, duration_ms)
      VALUES ($1, $2, 'vision', $3, $4, $5, $6, $7, $8)
    `, [
      runId, item.item_id, result.model, context,
      result.raw, result.issuesFound, result.issues.length, result.durationMs,
    ]);
    return result;
  } catch (err) {
    console.error(`  ✗ Vision analysis failed for ${item.item_id}: ${err.message}`);
    return null;
  }
}

/**
 * Process a single claimed item.
 */
async function processItem(item) {
  const start = Date.now();
  console.log(`  → Processing ${item.item_id} [${item.browser}/${item.device_profile}]`);

  try {
    const [textResult, visionResult] = await Promise.allSettled([
      analyzeTextForItem(item, item.run_id),
      analyzeScreenshotForItem(item, item.run_id),
    ]);

    const textIssues = textResult.status === 'fulfilled' && textResult.value?.issuesFound ? textResult.value.issues.length : 0;
    const visionIssues = visionResult.status === 'fulfilled' && visionResult.value?.issuesFound ? visionResult.value.issues.length : 0;

    // Mark as completed
    await db.query(`
      UPDATE test_results SET ai_status = 'completed' WHERE id = $1
    `, [item.id]);

    const elapsed = Date.now() - start;
    console.log(`  ✓ ${item.item_id} done (${elapsed}ms) — text: ${textIssues} issues, vision: ${visionIssues} issues`);
  } catch (err) {
    console.error(`  ✗ ${item.item_id} error: ${err.message}`);
    // Revert to pending so it can be retried
    await db.query(`
      UPDATE test_results SET ai_status = 'pending_ai' WHERE id = $1
    `, [item.id]);
  }
}

/**
 * Main poll loop.
 */
async function pollLoop() {
  console.log('SCOUT AI Worker started');
  console.log(`  Provider: ${process.env.AI_PROVIDER || 'mock'}`);
  console.log(`  Poll interval: ${POLL_INTERVAL}ms`);
  console.log(`  Batch size: ${BATCH_SIZE}`);

  // Health check on startup
  try {
    const health = await ai.healthCheck();
    if (health.healthy) {
      console.log(`  AI health: ✓ ${health.provider}`);
    } else {
      console.warn(`  AI health: ✗ ${health.provider} — ${JSON.stringify(health.details)}`);
    }
  } catch (err) {
    console.error(`  AI health check failed: ${err.message}`);
  }

  while (running) {
    try {
      const batch = await claimBatch();

      if (batch.length > 0) {
        console.log(`\n[${new Date().toISOString()}] Claimed ${batch.length} item(s)`);
        for (const item of batch) {
          if (!running) break;
          await processItem(item);
        }
      }
    } catch (err) {
      console.error(`Poll error: ${err.message}`);
    }

    // Wait before next poll
    if (running) {
      await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL));
    }
  }

  console.log('SCOUT AI Worker stopped');
}

// Graceful shutdown
function shutdown(signal) {
  console.log(`\nReceived ${signal}, shutting down gracefully...`);
  running = false;
  setTimeout(() => {
    console.error('Forced shutdown after timeout');
    process.exit(1);
  }, SHUTDOWN_TIMEOUT);
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// Start
pollLoop()
  .then(() => {
    db.pool?.end();
    process.exit(0);
  })
  .catch(err => {
    console.error('Fatal error:', err);
    db.pool?.end();
    process.exit(1);
  });
