-- SCOUT Database Schema
-- PostgreSQL DDL for the NAEP Automated Testing System

-- Test runs — each execution of the test suite
CREATE TABLE IF NOT EXISTS test_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    trigger_type    TEXT NOT NULL DEFAULT 'manual'
                    CHECK (trigger_type IN ('manual', 'scheduled', 'ci', 'dashboard')),
    config          JSONB NOT NULL DEFAULT '{}',
    summary         JSONB,
    notes           TEXT
);

-- Items — registry of assessment items under test
CREATE TABLE IF NOT EXISTS items (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    category        TEXT,
    tier            TEXT NOT NULL DEFAULT 'full'
                    CHECK (tier IN ('smoke', 'core', 'full')),
    languages       TEXT[] NOT NULL DEFAULT '{English}',
    active_version  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Test results — one row per item × browser × device per run
CREATE TABLE IF NOT EXISTS test_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    item_id         TEXT NOT NULL REFERENCES items(id),
    browser         TEXT NOT NULL,
    device_profile  TEXT NOT NULL DEFAULT 'desktop',
    status          TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'skipped', 'error')),
    diff_pixel_ratio REAL,
    screenshot_path TEXT,
    diff_image_path TEXT,
    duration_ms     INTEGER,
    error_message   TEXT,
    ai_status       TEXT NOT NULL DEFAULT 'none'
                    CHECK (ai_status IN ('none', 'pending_ai', 'analyzing', 'completed', 'skipped')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_test_results_run ON test_results(run_id);
CREATE INDEX IF NOT EXISTS idx_test_results_item ON test_results(item_id);
CREATE INDEX IF NOT EXISTS idx_test_results_status ON test_results(status);
CREATE INDEX IF NOT EXISTS idx_test_results_ai_status ON test_results(ai_status);

-- AI analyses — results from text and vision AI checks
CREATE TABLE IF NOT EXISTS ai_analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    item_id         TEXT NOT NULL REFERENCES items(id),
    analysis_type   TEXT NOT NULL CHECK (analysis_type IN ('text', 'vision', 'comparison', 'query')),
    model           TEXT NOT NULL,
    language        TEXT,
    input_summary   TEXT,
    output          TEXT NOT NULL,
    issues_found    BOOLEAN NOT NULL DEFAULT false,
    issue_count     INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_analyses_run ON ai_analyses(run_id);
CREATE INDEX IF NOT EXISTS idx_ai_analyses_issues ON ai_analyses(issues_found) WHERE issues_found = true;

-- Reviews — human decisions on AI-flagged items and visual failures
CREATE TABLE IF NOT EXISTS reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id       UUID REFERENCES test_results(id),
    analysis_id     UUID REFERENCES ai_analyses(id),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'dismissed', 'bug_filed')),
    reviewer        TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at     TIMESTAMPTZ,
    CHECK (result_id IS NOT NULL OR analysis_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);

-- Baselines — approved screenshot versions
CREATE TABLE IF NOT EXISTS baselines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id         TEXT NOT NULL REFERENCES items(id),
    browser         TEXT NOT NULL,
    device_profile  TEXT NOT NULL,
    version         TEXT NOT NULL,
    screenshot_path TEXT NOT NULL,
    approved_by     TEXT,
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (item_id, browser, device_profile, version)
);

-- Read-only role for AI query feature (requires superuser — run manually if needed)
-- DO $$
-- BEGIN
--   IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scout_readonly') THEN
--     CREATE ROLE scout_readonly;
--   END IF;
-- END
-- $$;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO scout_readonly;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO scout_readonly;

-- Environments — target deployment sites to test against
CREATE TABLE IF NOT EXISTS environments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    base_url        TEXT NOT NULL,
    auth_type       TEXT NOT NULL DEFAULT 'password_only'
                    CHECK (auth_type IN ('password_only', 'username_password', 'none')),
    credentials     JSONB NOT NULL DEFAULT '{}',
    launcher_config JSONB NOT NULL DEFAULT '{}',
    notes           TEXT,
    is_default      BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Assessments — test forms within an environment
CREATE TABLE IF NOT EXISTS assessments (
    id              TEXT PRIMARY KEY,
    environment_id  UUID NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    subject         TEXT,
    grade           TEXT,
    year            TEXT,
    item_count      INTEGER,
    form_value      TEXT,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_assessments_env ON assessments(environment_id);
