-- SCOUT Migration: Add environments and assessments tables
-- Run with: psql $DATABASE_URL -f src/db/migrations/001-environments.sql

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
