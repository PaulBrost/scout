-- SCOUT Migration 009: Test scripts registry
-- Links script files to items and/or assessments

CREATE TABLE IF NOT EXISTS test_scripts (
  id SERIAL PRIMARY KEY,
  script_path TEXT NOT NULL UNIQUE,
  description TEXT,
  item_id TEXT REFERENCES items(id) ON DELETE SET NULL,
  assessment_id TEXT REFERENCES assessments(id) ON DELETE SET NULL,
  category TEXT,                -- visual, content, feature, workflow, scoring
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Auto-register existing scripts from test_run_scripts
INSERT INTO test_scripts (script_path)
SELECT DISTINCT script_path FROM test_run_scripts
ON CONFLICT (script_path) DO NOTHING;

CREATE INDEX IF NOT EXISTS test_scripts_item_idx ON test_scripts (item_id);
CREATE INDEX IF NOT EXISTS test_scripts_assessment_idx ON test_scripts (assessment_id);
