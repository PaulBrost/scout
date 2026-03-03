-- Migration 004: Add execution_log to test_run_scripts
-- Stores step-by-step Playwright execution logs (actions, assertions, timing)

ALTER TABLE test_run_scripts ADD COLUMN IF NOT EXISTS execution_log TEXT;
