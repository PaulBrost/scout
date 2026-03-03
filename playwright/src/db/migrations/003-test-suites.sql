-- SCOUT Migration 003: Test Suites & Run Scripts
-- Adds test_suites, test_suite_scripts, test_run_scripts tables
-- and suite_id FK on test_runs.

-- Test suites — named collections of test scripts
CREATE TABLE IF NOT EXISTS test_suites (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT,
    created_by      TEXT,
    schedule        JSONB,
    browser_profiles TEXT[] NOT NULL DEFAULT '{chrome-desktop}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Test suite scripts — many-to-many link between suites and scripts
CREATE TABLE IF NOT EXISTS test_suite_scripts (
    suite_id        UUID NOT NULL REFERENCES test_suites(id) ON DELETE CASCADE,
    script_path     TEXT NOT NULL,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (suite_id, script_path)
);

CREATE INDEX IF NOT EXISTS idx_suite_scripts_suite ON test_suite_scripts(suite_id);

-- Add suite_id to test_runs (nullable — ad-hoc runs have no suite)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'test_runs' AND column_name = 'suite_id'
    ) THEN
        ALTER TABLE test_runs ADD COLUMN suite_id UUID REFERENCES test_suites(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_test_runs_suite ON test_runs(suite_id);

-- Test run scripts — per-script results within a run
CREATE TABLE IF NOT EXISTS test_run_scripts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    script_path     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'passed', 'failed', 'error')),
    duration_ms     INTEGER,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_run_scripts_run ON test_run_scripts(run_id);
CREATE INDEX IF NOT EXISTS idx_run_scripts_status ON test_run_scripts(status);
