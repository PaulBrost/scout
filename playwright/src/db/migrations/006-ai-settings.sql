-- SCOUT Migration 006: AI Settings & Tool Registry
-- Stores configurable system prompts, tool definitions, and AI preferences

-- AI settings key-value store
CREATE TABLE IF NOT EXISTS ai_settings (
  key         TEXT PRIMARY KEY,
  value       JSONB NOT NULL DEFAULT '{}',
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- AI tool registry
CREATE TABLE IF NOT EXISTS ai_tools (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT NOT NULL,
  category    TEXT NOT NULL DEFAULT 'general',
  enabled     BOOLEAN NOT NULL DEFAULT true,
  parameters  JSONB NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Seed default system prompt
INSERT INTO ai_settings (key, value) VALUES
  ('system_prompt', '"You are SCOUT AI, an expert assistant for the SCOUT automated testing system. You help users understand, create, and modify Playwright test scripts for the NAEP assessment platform.\n\nYou have access to tools that let you interact with the codebase and test infrastructure. Use them when appropriate:\n- Use `update_code` ONLY when the user explicitly asks you to modify, create, or fix code. Never call it for explanations or questions.\n- Use `explain_code` when asked to explain what code does.\n- Use `read_file` to look at helper files or other test scripts for reference.\n- Use `list_helpers` to see available helper functions.\n- Use `analyze_script` to validate code syntax.\n- Use `search_tests` to find examples in existing test scripts.\n- Use `get_items` to look up assessment items.\n\nWhen explaining code, be concise and focus on what matters. When modifying code, make minimal targeted changes unless asked for a rewrite.\n\nIMPORTANT: If the user asks a question, explains something, or asks for information — respond with text. Do NOT generate or replace code unless explicitly asked to modify, create, or fix it."'::jsonb),
  ('max_conversation_turns', '50'::jsonb),
  ('tool_calling_enabled', 'true'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- Seed default tools
INSERT INTO ai_tools (id, name, description, category, enabled, parameters) VALUES
  ('explain_code', 'Explain Code', 'Analyzes and explains what the current script does, including test structure, assertions, and helper usage. Returns a text explanation without modifying the editor.', 'analysis', true, '{}'),
  ('update_code', 'Update Code', 'Replaces the editor content with new or modified code. Use ONLY when the user explicitly asks to modify, create, generate, or fix code.', 'editing', true, '{"required": ["code", "summary"]}'),
  ('read_file', 'Read File', 'Reads the contents of a file from the project (helpers, test scripts, config files). Useful for understanding available utilities before writing code.', 'filesystem', true, '{"required": ["path"]}'),
  ('list_helpers', 'List Helpers', 'Lists all available helper functions from src/helpers/ with their signatures and documentation. Use this to know what utilities are available.', 'analysis', true, '{}'),
  ('analyze_script', 'Analyze Script', 'Validates JavaScript/Playwright script syntax and reports any errors. Does not execute the code.', 'analysis', true, '{"required": ["code"]}'),
  ('search_tests', 'Search Tests', 'Searches existing test scripts for patterns, function usage, or examples. Returns matching file paths and snippets.', 'filesystem', true, '{"required": ["query"]}'),
  ('get_items', 'Get Items', 'Fetches assessment items from the database. Useful for knowing what items exist and their properties when generating test scripts.', 'data', true, '{"optional": ["assessmentId", "search", "limit"]}')
ON CONFLICT (id) DO NOTHING;
