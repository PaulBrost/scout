// SCOUT — AI Chat Conversation Manager
// Manages multi-turn conversation state and tool-calling chat flow.

const db = require('../../db');
const toolExecutor = require('./tool-executor');
const prompts = require('../../ai/prompts');

// In-memory conversation store (keyed by conversationId)
const conversations = new Map();
const MAX_TURNS = 50;
const CONVERSATION_TTL = 60 * 60 * 1000; // 1 hour

/**
 * Get or create a conversation.
 */
function getConversation(conversationId) {
  if (!conversationId || !conversations.has(conversationId)) {
    const id = conversationId || crypto.randomUUID();
    conversations.set(id, {
      id,
      messages: [],
      createdAt: Date.now(),
    });
    return conversations.get(id);
  }
  return conversations.get(conversationId);
}

/**
 * Periodically clean up old conversations.
 */
setInterval(() => {
  const now = Date.now();
  for (const [id, conv] of conversations) {
    if (now - conv.createdAt > CONVERSATION_TTL) {
      conversations.delete(id);
    }
  }
}, 5 * 60 * 1000);

/**
 * Build the system prompt with tool descriptions and current code context.
 */
async function buildSystemPrompt(currentCode, filename) {
  // Load custom system prompt from DB
  let basePrompt;
  try {
    const result = await db.query("SELECT value FROM ai_settings WHERE key = 'system_prompt'");
    basePrompt = result.rows[0]?.value || getDefaultSystemPrompt();
  } catch {
    basePrompt = getDefaultSystemPrompt();
  }

  // Build tool descriptions from enabled tools
  const toolDescriptions = await toolExecutor.buildToolDescriptions();

  // Build helper context
  const helperContext = await buildHelperContext();

  let prompt = basePrompt + '\n\n';
  prompt += `## Available Tools\n${toolDescriptions}\n\n`;
  prompt += `## Tool Calling Format\nWhen you need to use a tool, include a JSON block in your response:\n`;
  prompt += '```tool\n{"tool": "tool_id", "args": {"param": "value"}}\n```\n';
  prompt += `You can use multiple tools in one response. Always provide a text explanation alongside tool calls.\n`;
  prompt += `CRITICAL: Only use \`update_code\` when the user explicitly asks to modify, create, generate, or fix code. For questions and explanations, just respond with text.\n\n`;

  if (helperContext) {
    prompt += `## Available Helpers\n${helperContext}\n\n`;
  }

  if (currentCode && currentCode.trim() && currentCode !== '// Generated test code will appear here...') {
    prompt += `## Current Script${filename ? ' (' + filename + ')' : ''}\nThe user is currently working with this code:\n\`\`\`javascript\n${currentCode}\n\`\`\`\n`;
  }

  return prompt;
}

function getDefaultSystemPrompt() {
  return `You are SCOUT AI, an expert assistant for the SCOUT automated testing system. You help users understand, create, and modify Playwright test scripts for the NAEP assessment platform.

When explaining code, be concise and focus on what matters. When modifying code, make minimal targeted changes unless asked for a rewrite.

IMPORTANT: If the user asks a question or asks for an explanation — respond with text only. Do NOT generate or replace code unless explicitly asked to modify, create, or fix it.`;
}

/**
 * Build helper function context for the AI.
 */
async function buildHelperContext() {
  try {
    const result = await toolExecutor.executeTool('list_helpers', {}, {});
    if (result.success) return result.result;
  } catch { /* ignore */ }
  return '';
}

/**
 * Process a chat message: send to AI, handle tool calls, return response.
 * @param {string} message - User's message
 * @param {string} conversationId - Conversation ID (null for new)
 * @param {string} currentCode - Current editor content
 * @param {string} filename - Current file being edited
 * @returns {Promise<{conversationId, response, codeUpdate?, toolsUsed[]}>}
 */
async function chat(message, conversationId, currentCode, filename) {
  const conv = getConversation(conversationId);

  // Build system prompt with current context
  const systemPrompt = await buildSystemPrompt(currentCode, filename);

  // Add user message to history
  conv.messages.push({ role: 'user', content: message });

  // Trim conversation to max turns
  if (conv.messages.length > MAX_TURNS * 2) {
    conv.messages = conv.messages.slice(-MAX_TURNS * 2);
  }

  // Build messages array for the AI
  const aiMessages = [
    { role: 'system', content: systemPrompt },
    ...conv.messages,
  ];

  // Call the AI
  const ai = require('../../ai');
  const rawResponse = await ai._chatCompletion(aiMessages, {
    max_tokens: 3000,
  });

  // Parse tool calls from the response
  const { text, toolCalls } = parseToolCalls(rawResponse);

  // Execute tool calls
  const toolResults = [];
  let codeUpdate = null;

  for (const tc of toolCalls) {
    const result = await toolExecutor.executeTool(tc.tool, tc.args, { currentCode, filename });
    toolResults.push({
      tool: tc.tool,
      args: tc.args,
      success: result.success,
      result: typeof result.result === 'object' ? result.result : result.result,
    });

    // Check if this is a code update
    if (tc.tool === 'update_code' && result.success && result.result?.code) {
      codeUpdate = {
        code: result.result.code,
        summary: result.result.summary || 'Code updated',
      };
    }
  }

  // Build the response text
  let responseText = text;

  // Add assistant message to history
  conv.messages.push({ role: 'assistant', content: rawResponse });

  return {
    conversationId: conv.id,
    response: responseText,
    codeUpdate,
    toolsUsed: toolResults.map(t => ({
      tool: t.tool,
      success: t.success,
      summary: typeof t.result === 'string' ? t.result.substring(0, 200) : t.result?.summary || '',
    })),
  };
}

/**
 * Parse tool calls from AI response text.
 * Handles multiple formats: ```tool blocks, inline JSON, and various formatting quirks.
 */
function parseToolCalls(response) {
  const toolCalls = [];
  let text = response;

  // Strategy 1: Match ```tool ... ``` blocks (flexible whitespace)
  const toolBlockRegex = /```tool\s*\n?([\s\S]*?)```/g;
  let match;

  while ((match = toolBlockRegex.exec(response)) !== null) {
    const jsonStr = match[1].trim();
    const parsed = tryParseToolJson(jsonStr);
    if (parsed) {
      toolCalls.push(parsed);
      text = text.replace(match[0], '').trim();
    }
  }

  // Strategy 2: Look for {"tool": "...", "args": ...} patterns with balanced braces
  if (toolCalls.length === 0) {
    const startPattern = /\{"tool"\s*:\s*"/g;
    while ((match = startPattern.exec(response)) !== null) {
      const jsonStr = extractBalancedJson(response, match.index);
      if (jsonStr) {
        const parsed = tryParseToolJson(jsonStr);
        if (parsed) {
          toolCalls.push(parsed);
          text = text.replace(jsonStr, '').trim();
        }
      }
    }
  }

  // Clean up leftover empty code fences
  text = text.replace(/```\s*```/g, '').trim();

  return { text, toolCalls };
}

/**
 * Try to parse a JSON string as a tool call.
 */
function tryParseToolJson(str) {
  try {
    const parsed = JSON.parse(str);
    if (parsed && parsed.tool) {
      return { tool: parsed.tool, args: parsed.args || {} };
    }
  } catch { /* not valid JSON */ }
  return null;
}

/**
 * Extract a balanced JSON object starting at the given position.
 */
function extractBalancedJson(str, startIdx) {
  if (str[startIdx] !== '{') return null;
  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let i = startIdx; i < str.length; i++) {
    const ch = str[i];
    if (escaped) { escaped = false; continue; }
    if (ch === '\\' && inString) { escaped = true; continue; }
    if (ch === '"') { inString = !inString; continue; }
    if (inString) continue;
    if (ch === '{') depth++;
    if (ch === '}') {
      depth--;
      if (depth === 0) {
        return str.substring(startIdx, i + 1);
      }
    }
  }
  return null;
}

module.exports = { chat, getConversation, conversations };
