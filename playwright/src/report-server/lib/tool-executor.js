// SCOUT — AI Tool Executor
// Executes tools called by the AI during chat conversations.

const path = require('path');
const fs = require('fs');
const vm = require('vm');
const db = require('../../db');

const PROJECT_ROOT = path.resolve(__dirname, '../../../');
const TESTS_DIR = path.resolve(PROJECT_ROOT, 'tests');
const HELPERS_DIR = path.resolve(PROJECT_ROOT, 'src/helpers');

/**
 * Load enabled tools from the database.
 */
async function getEnabledTools() {
  const result = await db.query('SELECT * FROM ai_tools WHERE enabled = true ORDER BY id');
  return result.rows;
}

/**
 * Build tool descriptions for the system prompt.
 */
async function buildToolDescriptions() {
  const tools = await getEnabledTools();
  return tools.map(t => {
    let params = '';
    if (t.parameters.required) {
      params = ` Parameters: ${t.parameters.required.join(', ')}`;
    }
    if (t.parameters.optional) {
      params += ` Optional: ${t.parameters.optional.join(', ')}`;
    }
    return `- **${t.id}**: ${t.description}${params}`;
  }).join('\n');
}

/**
 * Execute a tool by ID with the given arguments.
 * @param {string} toolId - Tool identifier
 * @param {object} args - Tool arguments
 * @param {object} context - Current context (currentCode, filename, etc.)
 * @returns {Promise<{success: boolean, result: any}>}
 */
async function executeTool(toolId, args, context) {
  // Verify tool is enabled
  const toolResult = await db.query('SELECT * FROM ai_tools WHERE id = $1', [toolId]);
  const tool = toolResult.rows[0];
  if (!tool) return { success: false, result: `Unknown tool: ${toolId}` };
  if (!tool.enabled) return { success: false, result: `Tool "${toolId}" is currently disabled` };

  switch (toolId) {
    case 'explain_code':
      return executeExplainCode(args, context);
    case 'update_code':
      return executeUpdateCode(args, context);
    case 'read_file':
      return executeReadFile(args, context);
    case 'list_helpers':
      return executeListHelpers(args, context);
    case 'analyze_script':
      return executeAnalyzeScript(args, context);
    case 'search_tests':
      return executeSearchTests(args, context);
    case 'get_items':
      return executeGetItems(args, context);
    default:
      return { success: false, result: `No executor for tool: ${toolId}` };
  }
}

// --- Tool Implementations ---

async function executeExplainCode(args, context) {
  // This tool is mostly handled by the AI itself — we just provide the code
  const code = args.code || context.currentCode || '';
  if (!code.trim()) {
    return { success: true, result: 'No code is currently loaded in the editor.' };
  }
  return {
    success: true,
    result: `Code provided for analysis (${code.split('\n').length} lines). The AI will explain it.`,
  };
}

async function executeUpdateCode(args, context) {
  if (!args.code) {
    return { success: false, result: 'No code provided for update_code tool' };
  }
  return {
    success: true,
    result: {
      code: args.code,
      summary: args.summary || 'Code updated',
    },
  };
}

async function executeReadFile(args, context) {
  if (!args.path) {
    return { success: false, result: 'No file path provided' };
  }

  // Resolve relative to project root, restrict to safe directories
  const safeDirs = ['src/helpers', 'tests', 'playwright.config.js', 'src/config'];
  const normalized = args.path.replace(/\\/g, '/').replace(/^\.?\//, '');
  const fullPath = path.resolve(PROJECT_ROOT, normalized);

  // Security: must stay within project
  if (!fullPath.startsWith(PROJECT_ROOT)) {
    return { success: false, result: 'Access denied: path outside project directory' };
  }

  // Check it's in an allowed subdirectory
  const isAllowed = safeDirs.some(d => fullPath.startsWith(path.resolve(PROJECT_ROOT, d)));
  if (!isAllowed) {
    return { success: false, result: `Access denied: only files in ${safeDirs.join(', ')} are readable` };
  }

  try {
    const content = fs.readFileSync(fullPath, 'utf-8');
    const maxLen = 4000;
    const truncated = content.length > maxLen ? content.substring(0, maxLen) + '\n... (truncated)' : content;
    return { success: true, result: `File: ${normalized}\n\`\`\`javascript\n${truncated}\n\`\`\`` };
  } catch (err) {
    return { success: false, result: `Cannot read file: ${err.message}` };
  }
}

async function executeListHelpers(args, context) {
  try {
    const files = fs.readdirSync(HELPERS_DIR).filter(f => f.endsWith('.js'));
    const helpers = [];

    for (const file of files) {
      const content = fs.readFileSync(path.join(HELPERS_DIR, file), 'utf-8');
      const exportMatch = content.match(/module\.exports\s*=\s*\{([^}]+)\}/);
      if (!exportMatch) continue;

      const names = exportMatch[1].split(',').map(s => s.trim()).filter(Boolean);
      for (const name of names) {
        // Find function signature
        const sigRegex = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(([^)]*)\\)`, 'm');
        const sigMatch = content.match(sigRegex);
        // Find JSDoc
        const docRegex = new RegExp(`(/\\*\\*[\\s\\S]*?\\*/)\\s*(?:async\\s+)?function\\s+${name}`, 'm');
        const docMatch = content.match(docRegex);

        const sig = sigMatch ? `${name}(${sigMatch[1]})` : name;
        const doc = docMatch ? docMatch[1].replace(/\s*\*\s*/g, ' ').replace(/\/\*\*|\*\//g, '').trim() : '';
        helpers.push(`- \`${sig}\` ${doc ? '— ' + doc : ''} (from ${file})`);
      }
    }

    return {
      success: true,
      result: helpers.length > 0
        ? `Available helpers:\n${helpers.join('\n')}`
        : 'No helper functions found in src/helpers/',
    };
  } catch (err) {
    return { success: false, result: `Error scanning helpers: ${err.message}` };
  }
}

async function executeAnalyzeScript(args, context) {
  const code = args.code || context.currentCode || '';
  if (!code.trim()) {
    return { success: true, result: 'No code to analyze.' };
  }

  try {
    new vm.Script(code, { filename: 'analysis.spec.js' });
    return { success: true, result: 'Syntax valid — no errors found.' };
  } catch (err) {
    const loc = err.stack ? err.stack.split('\n').slice(0, 3).join('\n') : err.message;
    return { success: true, result: `Syntax error found:\n${loc}` };
  }
}

async function executeSearchTests(args, context) {
  const query = (args.query || '').trim();
  if (!query) {
    return { success: false, result: 'No search query provided' };
  }

  try {
    const results = [];
    const searchDir = (dir) => {
      if (!fs.existsSync(dir)) return;
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          searchDir(path.join(dir, entry.name));
        } else if (entry.name.endsWith('.spec.js') || entry.name.endsWith('.js')) {
          const fullPath = path.join(dir, entry.name);
          const content = fs.readFileSync(fullPath, 'utf-8');
          const lines = content.split('\n');
          const matches = [];
          for (let i = 0; i < lines.length; i++) {
            if (lines[i].toLowerCase().includes(query.toLowerCase())) {
              matches.push({ line: i + 1, text: lines[i].trim() });
            }
          }
          if (matches.length > 0) {
            const relPath = path.relative(PROJECT_ROOT, fullPath);
            results.push({ file: relPath, matches: matches.slice(0, 3) });
          }
        }
      }
    };

    searchDir(TESTS_DIR);
    searchDir(HELPERS_DIR);

    if (results.length === 0) {
      return { success: true, result: `No matches found for "${query}"` };
    }

    const output = results.slice(0, 5).map(r => {
      const matchLines = r.matches.map(m => `  L${m.line}: ${m.text}`).join('\n');
      return `**${r.file}**\n${matchLines}`;
    }).join('\n\n');

    return { success: true, result: `Found ${results.length} file(s) matching "${query}":\n\n${output}` };
  } catch (err) {
    return { success: false, result: `Search error: ${err.message}` };
  }
}

async function executeGetItems(args, context) {
  try {
    let query = 'SELECT i.id, i.name, i.category, i.tier, i.languages, a.name as assessment_name FROM items i LEFT JOIN assessments a ON i.assessment_id = a.id';
    const params = [];
    const conditions = [];

    if (args.assessmentId) {
      conditions.push(`i.assessment_id = $${params.length + 1}`);
      params.push(args.assessmentId);
    }
    if (args.search) {
      conditions.push(`(i.name ILIKE $${params.length + 1} OR i.id ILIKE $${params.length + 1})`);
      params.push(`%${args.search}%`);
    }

    if (conditions.length > 0) {
      query += ' WHERE ' + conditions.join(' AND ');
    }

    const limit = Math.min(parseInt(args.limit || '20', 10), 50);
    query += ` ORDER BY i.name LIMIT ${limit}`;

    const result = await db.query(query, params);

    if (result.rows.length === 0) {
      return { success: true, result: 'No items found.' };
    }

    const output = result.rows.map(i =>
      `- **${i.id}** — ${i.name} (${i.category}, tier: ${i.tier})${i.assessment_name ? ' [' + i.assessment_name + ']' : ''}`
    ).join('\n');

    return { success: true, result: `Found ${result.rows.length} item(s):\n${output}` };
  } catch (err) {
    return { success: false, result: `Database error: ${err.message}` };
  }
}

module.exports = {
  getEnabledTools,
  buildToolDescriptions,
  executeTool,
};
