-- SCOUT Migration 007: Add numeric item IDs for URL routing
-- Adds a serial numeric_id column to items for use in links/URLs
-- The text 'id' column remains as the primary key for DB integrity

-- Add auto-increment numeric ID
ALTER TABLE items ADD COLUMN IF NOT EXISTS numeric_id SERIAL;

-- Create unique index on numeric_id for fast lookups
CREATE UNIQUE INDEX IF NOT EXISTS items_numeric_id_idx ON items (numeric_id);
