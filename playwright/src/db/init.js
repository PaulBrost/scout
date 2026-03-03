// SCOUT — Database Initializer
// Runs schema.sql against the configured PostgreSQL database.

const fs = require('fs');
const path = require('path');

// Skip config validation — we only need DATABASE_URL
process.env.SCOUT_SKIP_VALIDATION = 'true';
const db = require('./index');

async function init() {
  console.log('SCOUT: Initializing database schema...');

  const schemaPath = path.resolve(__dirname, 'schema.sql');
  const sql = fs.readFileSync(schemaPath, 'utf-8');

  try {
    const health = await db.healthCheck();
    if (!health.healthy) {
      console.error('❌ Cannot connect to database:', health.details.error);
      console.error('   Check DATABASE_URL in .env');
      process.exit(1);
    }

    console.log(`   Connected to: ${health.details.database}`);
    await db.query(sql);
    console.log('✅ Schema initialized successfully.');
    console.log('   Tables: test_runs, items, test_results, ai_analyses, reviews, baselines');
  } catch (err) {
    console.error('❌ Schema initialization failed:', err.message);
    process.exit(1);
  } finally {
    await db.close();
  }
}

init();
