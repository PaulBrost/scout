// SCOUT — Database Health Check
// Quick connectivity test for the PostgreSQL database.

const db = require('./index');

async function checkHealth() {
  const result = await db.healthCheck();
  return result;
}

// Auto-run when called directly (node src/db/health.js)
if (require.main === module) {
  process.env.SCOUT_SKIP_VALIDATION = 'true';
  checkHealth().then(result => {
    console.log(JSON.stringify(result, null, 2));
    return db.close();
  }).then(() => {
    process.exit(0);
  }).catch(() => {
    process.exit(1);
  });
}

module.exports = { checkHealth };
