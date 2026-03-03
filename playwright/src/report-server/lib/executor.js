// SCOUT — Playwright Execution Engine
// Spawns real Playwright test processes, captures output, parses results.

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const db = require('../../db');

const PROJECT_ROOT = path.resolve(__dirname, '../../../');
const TESTS_DIR = path.join(PROJECT_ROOT, 'tests');
const RESULTS_DIR = path.join(PROJECT_ROOT, 'test-results');
const SCRIPT_TIMEOUT = parseInt(process.env.SCOUT_SCRIPT_TIMEOUT) || 180000; // 3 min default

/**
 * Scan test-results/ for trace and video artifacts belonging to a test script.
 * Playwright puts artifacts in test-results/<test-name>-<project>/ dirs.
 * Returns { tracePath, videoPath } with paths relative to project root (for static serving).
 */
function findArtifacts(scriptPath) {
  var tracePath = null;
  var videoPath = null;

  try {
    if (!fs.existsSync(RESULTS_DIR)) return { tracePath, videoPath };

    // Playwright names artifact dirs based on test file: e.g. tests/foo.spec.js → foo-spec-js-<project>/
    // We scan all subdirs for trace.zip and *.webm files
    var basename = path.basename(scriptPath, path.extname(scriptPath)).replace(/\./g, '-');
    var entries = fs.readdirSync(RESULTS_DIR, { withFileTypes: true });

    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      if (!entry.isDirectory()) continue;
      // Match directories that start with the script basename (case-insensitive)
      if (!entry.name.toLowerCase().startsWith(basename.toLowerCase())) continue;

      var dirPath = path.join(RESULTS_DIR, entry.name);
      var files = fs.readdirSync(dirPath);

      for (var j = 0; j < files.length; j++) {
        var file = files[j];
        if (!tracePath && file === 'trace.zip') {
          tracePath = 'test-results/' + entry.name + '/trace.zip';
        }
        if (!videoPath && (file.endsWith('.webm') || file.endsWith('.mp4'))) {
          videoPath = 'test-results/' + entry.name + '/' + file;
        }
      }
    }
  } catch (e) {
    // Non-critical — artifacts are optional
  }

  return { tracePath: tracePath, videoPath: videoPath };
}

/**
 * Execute a single Playwright test script.
 * Returns { status, durationMs, errorMessage, executionLog, jsonReport }
 */
async function executeScript(scriptPath, options) {
  options = options || {};
  var project = options.project || '';
  var timeout = options.timeout || SCRIPT_TIMEOUT;

  var fullPath = path.join(TESTS_DIR, scriptPath);
  if (!fs.existsSync(fullPath)) {
    return {
      status: 'error',
      durationMs: 0,
      errorMessage: 'Script not found: ' + fullPath,
      executionLog: 'Error: Script file does not exist at ' + fullPath,
      jsonReport: null,
    };
  }

  // Ensure test-results dir exists for JSON report
  var resultsDir = path.join(PROJECT_ROOT, 'test-results');
  if (!fs.existsSync(resultsDir)) fs.mkdirSync(resultsDir, { recursive: true });

  // Temp file for JSON report
  var jsonFile = path.join(resultsDir, 'run-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8) + '.json');

  // Build playwright command args
  var args = ['playwright', 'test', fullPath, '--reporter=list,json'];

  if (project) {
    args.push('--project=' + project);
  }

  if (!options.retries) {
    args.push('--retries=0');
  }

  return new Promise(function(resolve) {
    var stdout = '';
    var stderr = '';
    var startTime = Date.now();
    var timedOut = false;

    var env = Object.assign({}, process.env, {
      PLAYWRIGHT_JSON_OUTPUT_NAME: jsonFile,
      FORCE_COLOR: '0',
      CI: '1',
    });

    if (options.env) {
      Object.assign(env, options.env);
    }

    var proc = spawn('npx', args, {
      cwd: PROJECT_ROOT,
      env: env,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: process.platform === 'win32',
    });

    var timer = setTimeout(function() {
      timedOut = true;
      proc.kill('SIGTERM');
      setTimeout(function() { try { proc.kill('SIGKILL'); } catch(e) {} }, 5000);
    }, timeout);

    proc.stdout.on('data', function(chunk) { stdout += chunk.toString(); });
    proc.stderr.on('data', function(chunk) { stderr += chunk.toString(); });

    proc.on('close', function(code) {
      clearTimeout(timer);
      var durationMs = Date.now() - startTime;

      // Build execution log
      var log = [];
      log.push('[0ms] ▶ Running: npx ' + args.join(' '));
      log.push('[0ms] ▶ CWD: ' + PROJECT_ROOT);
      if (project) log.push('[0ms] ▶ Project: ' + project);
      log.push('');

      if (stdout.trim()) {
        log.push('── Playwright Output ─────────────────');
        log.push(stdout.trim());
      }
      if (stderr.trim()) {
        log.push('');
        log.push('── Stderr ────────────────────────────');
        log.push(stderr.trim());
      }

      log.push('');
      log.push('[' + durationMs + 'ms] ' + (timedOut ? '✗ TIMED OUT' : code === 0 ? '✓ Passed' : '✗ Failed (exit code ' + code + ')') + ' (' + (durationMs / 1000).toFixed(1) + 's)');

      var executionLog = log.join('\n');

      // Parse JSON report if available
      var jsonReport = null;
      try {
        if (fs.existsSync(jsonFile)) {
          jsonReport = JSON.parse(fs.readFileSync(jsonFile, 'utf8'));
          fs.unlinkSync(jsonFile);
        }
      } catch (e) {
        // JSON report parsing failed — still have stdout
      }

      // Determine status and error message
      var status, errorMessage;
      if (timedOut) {
        status = 'error';
        errorMessage = 'Timeout: Script exceeded ' + (timeout / 1000) + 's limit';
      } else if (code === 0) {
        status = 'passed';
        errorMessage = null;
      } else {
        status = 'failed';
        errorMessage = extractErrorMessage(stdout, stderr, jsonReport);
      }

      // Scan for trace/video artifacts
      var artifacts = findArtifacts(scriptPath);

      resolve({
        status: status,
        durationMs: durationMs,
        errorMessage: errorMessage,
        executionLog: executionLog,
        jsonReport: jsonReport,
        exitCode: code,
        tracePath: artifacts.tracePath,
        videoPath: artifacts.videoPath,
      });
    });

    proc.on('error', function(err) {
      clearTimeout(timer);
      resolve({
        status: 'error',
        durationMs: Date.now() - startTime,
        errorMessage: 'Process error: ' + err.message,
        executionLog: 'Failed to spawn process: ' + err.message,
        jsonReport: null,
        exitCode: -1,
      });
    });
  });
}

/**
 * Extract a meaningful error message from Playwright output.
 */
function extractErrorMessage(stdout, stderr, jsonReport) {
  // Try JSON report first
  if (jsonReport && jsonReport.suites) {
    var errors = [];
    function walkSuites(suites) {
      for (var i = 0; i < suites.length; i++) {
        var suite = suites[i];
        if (suite.specs) {
          for (var j = 0; j < suite.specs.length; j++) {
            var spec = suite.specs[j];
            if (spec.tests) {
              for (var k = 0; k < spec.tests.length; k++) {
                var test = spec.tests[k];
                if (test.results) {
                  for (var l = 0; l < test.results.length; l++) {
                    var r = test.results[l];
                    if (r.status === 'failed' || r.status === 'timedOut') {
                      var msg = r.error && r.error.message ? r.error.message : '';
                      if (msg) errors.push(spec.title + ': ' + msg.split('\n')[0]);
                    }
                  }
                }
              }
            }
          }
        }
        if (suite.suites) walkSuites(suite.suites);
      }
    }
    walkSuites(jsonReport.suites);
    if (errors.length > 0) return errors.join('; ').substring(0, 500);
  }

  // Fallback: extract from stdout
  var lines = stdout.split('\n');
  var errorLines = [];
  var capture = false;
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (/Error:|AssertionError:|TimeoutError:|expect\(/.test(line)) {
      capture = true;
    }
    if (capture) {
      errorLines.push(line.trim());
      if (errorLines.length >= 5) break;
    }
  }
  if (errorLines.length > 0) return errorLines.join('\n').substring(0, 500);

  if (stderr.trim()) return stderr.trim().split('\n')[0].substring(0, 500);

  return 'Test failed (see execution log for details)';
}

/**
 * Execute a run: run all scripts sequentially, updating DB rows as each completes.
 */
async function executeRun(runId, scriptPaths, options) {
  options = options || {};
  var passed = 0, failed = 0, errors = 0;

  for (var i = 0; i < scriptPaths.length; i++) {
    var scriptPath = scriptPaths[i];

    await db.query(
      "UPDATE test_run_scripts SET status = 'running', started_at = now() WHERE run_id = $1 AND script_path = $2",
      [runId, scriptPath]
    );

    try {
      var result = await executeScript(scriptPath, options);

      await db.query(
        `UPDATE test_run_scripts SET status = $1, duration_ms = $2, error_message = $3,
         execution_log = $4, trace_path = $5, video_path = $6, completed_at = now()
         WHERE run_id = $7 AND script_path = $8`,
        [result.status, result.durationMs, result.errorMessage, result.executionLog,
         result.tracePath, result.videoPath, runId, scriptPath]
      );

      if (result.status === 'passed') passed++;
      else if (result.status === 'error') errors++;
      else failed++;

    } catch (e) {
      await db.query(
        `UPDATE test_run_scripts SET status = 'error', error_message = $1,
         execution_log = $2, completed_at = now()
         WHERE run_id = $3 AND script_path = $4`,
        ['Execution engine error: ' + e.message, 'Internal error: ' + e.stack, runId, scriptPath]
      );
      errors++;
    }
  }

  var runStatus = (failed + errors) === 0 ? 'completed' : 'failed';
  await db.query(
    `UPDATE test_runs SET status = $1, completed_at = now(),
     summary = $2 WHERE id = $3`,
    [runStatus, JSON.stringify({ passed: passed, failed: failed, errors: errors, total: scriptPaths.length }), runId]
  );

  console.log('[Executor] Run ' + runId.substring(0, 8) + ' complete: ' + passed + ' passed, ' + failed + ' failed, ' + errors + ' errors');
}

module.exports = {
  executeScript: executeScript,
  executeRun: executeRun,
};
