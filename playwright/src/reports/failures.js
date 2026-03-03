// SCOUT — Failure Report (CLI)
// Usage: npm run report:failures

process.env.SCOUT_SKIP_VALIDATION = 'true';
const db = require('../db/index');
const { getNewFailures } = require('../db/queries');

(async () => {
  try {
    const failures = await getNewFailures();
    if (failures.length === 0) {
      console.log('\n  ✅ No new failures — all previously passing items still pass.\n');
      return;
    }

    console.log('\n  SCOUT — New Failures (passed before, failing now)\n');
    console.log('  ' + 'Item'.padEnd(32) + 'Browser'.padEnd(20) + 'Diff Ratio'.padEnd(12) + 'Error');
    console.log('  ' + '-'.repeat(90));

    for (const f of failures) {
      console.log(
        '  ' + f.item_id.padEnd(32) + f.browser.padEnd(20) +
        String(f.diff_pixel_ratio ?? 'N/A').padEnd(12) +
        (f.error_message || '').slice(0, 50)
      );
    }
    console.log();
  } catch (err) {
    console.error('Error:', err.message);
  } finally {
    await db.close();
  }
})();
