// SCOUT — AI Flags Report (CLI)
// Usage: npm run report:ai-flags

process.env.SCOUT_SKIP_VALIDATION = 'true';
const db = require('../db/index');
const { getPendingAIFlags } = require('../db/queries');

(async () => {
  try {
    const flags = await getPendingAIFlags();
    if (flags.length === 0) {
      console.log('\n  ✅ No pending AI flags — all items clean or already reviewed.\n');
      return;
    }

    console.log('\n  SCOUT — AI-Flagged Items Pending Review\n');
    console.log('  ' + 'Item'.padEnd(27) + 'Type'.padEnd(10) + 'Model'.padEnd(22) + 'Issues'.padStart(6) + '  Date');
    console.log('  ' + '-'.repeat(85));

    for (const f of flags) {
      const date = new Date(f.created_at).toLocaleDateString();
      console.log(
        '  ' + f.item_id.padEnd(27) + f.analysis_type.padEnd(10) +
        f.model.padEnd(22) + String(f.issue_count).padStart(6) + '  ' + date
      );

      // Show issue details
      try {
        const data = JSON.parse(f.output);
        if (data.issues) {
          for (const issue of data.issues) {
            const desc = issue.text
              ? `${issue.type}: "${issue.text}" → "${issue.suggestion}"`
              : `${issue.type}: ${issue.detail}`;
            console.log('    └─ %s', desc);
          }
        }
      } catch { /* skip unparseable */ }
    }
    console.log();
  } catch (err) {
    console.error('Error:', err.message);
  } finally {
    await db.close();
  }
})();
