// SCOUT — Custom Playwright Reporter → PostgreSQL
// Records test results to the database as tests execute.

const { createTestRun, recordTestResult, recordAIAnalysis, completeTestRun } = require('../db/results');
const db = require('../db/index');

class ScoutDatabaseReporter {
  constructor(options = {}) {
    this.runId = null;
    this.options = options;
    this.results = { passed: 0, failed: 0, skipped: 0, errors: 0 };
  }

  async onBegin(config, suite) {
    try {
      const browsers = config.projects.map(p => p.name);
      this.runId = await createTestRun({
        trigger: process.env.SCOUT_TRIGGER || 'manual',
        config: {
          browsers,
          workers: config.workers,
          baselineVersion: process.env.BASELINE_VERSION || 'v2024',
          itemTier: process.env.ITEM_TIER || 'smoke',
        },
      });
      console.log(`SCOUT DB: Test run started — ${this.runId}`);
    } catch (err) {
      console.warn(`SCOUT DB: Could not create test run record — ${err.message}`);
      console.warn('          Results will not be saved to database. Tests will still execute.');
    }
  }

  async onTestEnd(test, result) {
    if (!this.runId) return;

    // Track counts
    if (result.status === 'passed') this.results.passed++;
    else if (result.status === 'failed' || result.status === 'timedOut') this.results.failed++;
    else if (result.status === 'skipped') this.results.skipped++;

    const projectName = test.parent?.project()?.name || 'unknown';
    const testId = deriveTestId(test);

    try {
      await recordTestResult(this.runId, {
        itemId: testId,
        browser: projectName,
        deviceProfile: projectName.includes('chromebook') ? 'chromebook' : 'desktop',
        status: result.status === 'timedOut' ? 'error' : result.status,
        durationMs: result.duration,
        errorMessage: result.error?.message || null,
        aiStatus: hasAIAttachments(result) ? 'completed' : 'none',
      });

      // Record AI analysis results from test attachments
      await recordAIAttachments(this.runId, testId, result);
    } catch (err) {
      console.warn(`SCOUT DB: Could not record result for "${testId}" — ${err.message}`);
    }
  }

  async onEnd(result) {
    if (!this.runId) return;

    try {
      await completeTestRun(this.runId, {
        status: result.status === 'passed' ? 'completed' : 'failed',
        ...this.results,
        total: this.results.passed + this.results.failed + this.results.skipped + this.results.errors,
      });
      console.log(`SCOUT DB: Test run completed — ${this.runId}`);
      console.log(`          Passed: ${this.results.passed} | Failed: ${this.results.failed} | Skipped: ${this.results.skipped}`);
    } catch (err) {
      console.warn(`SCOUT DB: Could not complete test run record — ${err.message}`);
    }

    try { await db.close(); } catch { /* ignore */ }
  }
}

/**
 * Derive a stable test ID from test metadata.
 * Maps test titles to item IDs for the database.
 */
function deriveTestId(test) {
  const title = test.title;

  // "Item N ..." or "item-N"
  const itemMatch = title.match(/[Ii]tem[\s-](\d+)/);
  if (itemMatch) return `item-${itemMatch[1]}`;

  // "All CRA Form 1 items ..." → category-level
  if (/all.*items/i.test(title)) return 'cra-form1-all';

  // "First 5 items ..." → vision subset
  if (/first.*items/i.test(title)) return 'cra-form1-vision';

  // Feature tests: use describe + title as slug
  const describe = test.parent?.title || '';
  const slug = `${describe}-${title}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80);
  return slug || 'unknown';
}

/**
 * Check if test result has AI analysis attachments.
 */
function hasAIAttachments(result) {
  return result.attachments?.some(a => a.name.startsWith('ai-'));
}

/**
 * Extract and record AI analysis data from test attachments.
 */
async function recordAIAttachments(runId, testId, result) {
  if (!result.attachments) return;

  for (const attachment of result.attachments) {
    if (!attachment.name.startsWith('ai-') && !attachment.name.startsWith('vision-')) continue;
    if (attachment.contentType !== 'application/json') continue;

    try {
      const data = JSON.parse(attachment.body.toString());
      const analysisType = attachment.name.startsWith('vision') ? 'vision' : 'text';

      await recordAIAnalysis(runId, {
        itemId: testId,
        analysisType,
        model: data.model || 'unknown',
        language: 'English',
        inputSummary: attachment.name,
        output: JSON.stringify(data),
        issuesFound: data.issuesFound || false,
        issueCount: data.issues?.length || 0,
        durationMs: data.durationMs || null,
      });
    } catch { /* skip unparseable attachments */ }
  }
}

module.exports = ScoutDatabaseReporter;
