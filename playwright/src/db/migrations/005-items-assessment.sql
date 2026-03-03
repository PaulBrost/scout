-- Migration 005: Add assessment_id to items
-- Links items to their parent assessment

ALTER TABLE items ADD COLUMN IF NOT EXISTS assessment_id TEXT REFERENCES assessments(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_items_assessment ON items(assessment_id);
