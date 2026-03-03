// SCOUT — Latest Run Report (CLI)
// Usage: npm run report:latest

process.env.SCOUT_SKIP_VALIDATION = 'true';
const db = require('../db/index');
const { getPassRateTrend } = require('../db/queries');

(async () => {
  try {
    const trend = await getPassRateTrend(5);
    if (trend.length === 0) {
      console.log('No completed test runs found.');
      return;
    }

    console.log('\n  SCOUT — Recent Test Runs\n');
    console.log('  ' + 'Run ID'.padEnd(38) + 'Date'.padEnd(22) + 'Pass'.padStart(6) + 'Fail'.padStart(6) + 'Total'.padStart(7) + '  Rate');
    console.log('  ' + '-'.repeat(90));

    for (const run of trend) {
      const date = new Date(run.started_at).toLocaleString();
      console.log(
        '  ' + run.id.padEnd(38) + date.padEnd(22) +
        String(run.passed).padStart(6) + String(run.failed).padStart(6) +
        String(run.total).padStart(7) + String(run.pass_pct + '%').padStart(7)
      );
    }
    console.log();
  } catch (err) {
    console.error('Error:', err.message);
  } finally {
    await db.close();
  }
})();
