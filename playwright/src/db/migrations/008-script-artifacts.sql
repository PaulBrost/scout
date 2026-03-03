-- SCOUT Migration 008: Add trace/video artifact paths to test_run_scripts
-- Stores paths to Playwright trace archives and video recordings

ALTER TABLE test_run_scripts ADD COLUMN IF NOT EXISTS trace_path TEXT;
ALTER TABLE test_run_scripts ADD COLUMN IF NOT EXISTS video_path TEXT;
