/**
 * SCOUT — Test Data Helper
 *
 * Reads test data sets linked to the current test script via the
 * SCOUT_TEST_DATA environment variable (set by executor/runner.py).
 *
 * Data is organized by type: { credentials: [...], inputs: [...], items: [...], custom: [...] }
 * Each entry has: { name, assessment_id, item_id, description, entries: [...] }
 *
 * Usage:
 *   const { loadTestData, getCredentials, getInputs } = require('../src/helpers/testdata');
 *   const creds = getCredentials();          // first credentials dataset
 *   const creds = getCredentials('Admin');   // credentials dataset named "Admin"
 *   const all = loadTestData();              // all linked datasets by type
 */

const fs = require('fs');

let _cache = null;

/**
 * Load all linked test data sets, organized by data_type.
 * Returns an object like { credentials: [...], inputs: [...], ... }
 * Each array entry: { name, assessment_id, item_id, description, entries: [] }
 *
 * @param {string} [name] - Optional: filter to datasets matching this name
 * @returns {object} Test data organized by type
 */
function loadTestData(name) {
  if (!_cache) {
    const dataPath = process.env.SCOUT_TEST_DATA;
    if (!dataPath) return {};
    try {
      _cache = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));
    } catch (e) {
      console.warn('[SCOUT] Failed to load test data:', e.message);
      return {};
    }
  }

  if (!name) return _cache;

  // Filter all types to only datasets matching the name
  const filtered = {};
  for (const [type, datasets] of Object.entries(_cache)) {
    const matches = datasets.filter(d => d.name === name);
    if (matches.length > 0) filtered[type] = matches;
  }
  return filtered;
}

/**
 * Get a credentials dataset by name.
 * Returns the dataset object { name, entries, ... } or null.
 *
 * @param {string} [name] - Dataset name. If omitted, returns the first credentials dataset.
 * @returns {object|null}
 */
function getCredentials(name) {
  return _getByType('credentials', name);
}

/**
 * Get a test inputs dataset by name.
 *
 * @param {string} [name] - Dataset name. If omitted, returns the first inputs dataset.
 * @returns {object|null}
 */
function getInputs(name) {
  return _getByType('inputs', name);
}

/**
 * Get an item list dataset by name.
 *
 * @param {string} [name] - Dataset name. If omitted, returns the first items dataset.
 * @returns {object|null}
 */
function getItemList(name) {
  return _getByType('items', name);
}

/**
 * Get a custom dataset by name.
 *
 * @param {string} [name] - Dataset name. If omitted, returns the first custom dataset.
 * @returns {object|null}
 */
function getCustomData(name) {
  return _getByType('custom', name);
}

function _getByType(type, name) {
  const data = loadTestData();
  const datasets = data[type] || [];
  if (!name) return datasets[0] || null;
  return datasets.find(d => d.name === name) || null;
}

module.exports = { loadTestData, getCredentials, getInputs, getItemList, getCustomData };
