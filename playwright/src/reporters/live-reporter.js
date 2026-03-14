// SCOUT — Live Progress Reporter
// Writes test progress to stderr (unbuffered) so the runner can stream it in real time.
// Stdout from Node.js is fully buffered when piped; stderr is not.

class LiveReporter {
  onBegin(config, suite) {
    const total = suite.allTests().length;
    process.stderr.write(`[SCOUT] Starting ${total} test(s)\n`);
  }

  onTestBegin(test) {
    process.stderr.write(`[SCOUT] Running: ${test.title}\n`);
  }

  onStdOut(chunk, test) {
    // Forward test console.log output to stderr so it appears in live log
    const text = typeof chunk === 'string' ? chunk : chunk.toString('utf-8');
    process.stderr.write(text);
  }

  onStdErr(chunk, test) {
    const text = typeof chunk === 'string' ? chunk : chunk.toString('utf-8');
    process.stderr.write(text);
  }

  onTestEnd(test, result) {
    const status = result.status;
    const duration = (result.duration / 1000).toFixed(1);
    process.stderr.write(`[SCOUT] ${status}: ${test.title} (${duration}s)\n`);
  }

  onEnd(result) {
    process.stderr.write(`[SCOUT] Finished — ${result.status}\n`);
  }
}

module.exports = LiveReporter;
