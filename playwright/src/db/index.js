// SCOUT — Database Connection Pool
// Manages PostgreSQL connections using the pg library.

const { Pool } = require('pg');
const config = require('../config');

let pool = null;

function getPool() {
  if (!pool) {
    pool = new Pool({
      connectionString: config.databaseUrl,
      max: 10,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 5000,
    });

    pool.on('error', (err) => {
      console.error('SCOUT: Unexpected database pool error:', err.message);
    });
  }
  return pool;
}

/**
 * Execute a parameterized SQL query.
 * @param {string} sql - SQL statement with $1, $2... placeholders
 * @param {Array} params - Parameter values
 * @returns {Promise<import('pg').QueryResult>}
 */
async function query(sql, params = []) {
  const client = await getPool().connect();
  try {
    return await client.query(sql, params);
  } finally {
    client.release();
  }
}

/**
 * Execute multiple queries in a transaction.
 * @param {function} fn - Async function receiving a client
 */
async function transaction(fn) {
  const client = await getPool().connect();
  try {
    await client.query('BEGIN');
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

/**
 * Check database connectivity.
 * @returns {Promise<{healthy: boolean, details: object}>}
 */
async function healthCheck() {
  try {
    const result = await query('SELECT NOW() as time, current_database() as db');
    return {
      healthy: true,
      details: {
        database: result.rows[0].db,
        serverTime: result.rows[0].time,
      },
    };
  } catch (err) {
    return {
      healthy: false,
      details: { error: err.message },
    };
  }
}

/**
 * Gracefully close the connection pool.
 */
async function close() {
  if (pool) {
    await pool.end();
    pool = null;
  }
}

module.exports = { query, transaction, healthCheck, close, get pool() { return pool; } };
