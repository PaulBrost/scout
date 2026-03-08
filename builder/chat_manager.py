"""SCOUT — AI Chat Conversation Manager.

Supports an agentic loop: when the AI calls research tools (read_file,
list_helpers, search_tests, get_items), results are fed back automatically
and the AI continues without requiring user prompts.  The loop stops when
the AI produces a text-only response, calls update_code, or hits MAX_LOOP.
"""
import uuid
import re
import json
from django.db import connection


MAX_TURNS = 50
MAX_LOOP = 8  # max auto-continue iterations per user message


def get_default_system_prompt():
    return """You are SCOUT AI, an expert assistant for the SCOUT automated testing system. You help users understand, create, and modify Playwright test scripts for PIAAC and NAEP assessment platforms.

When explaining code, be concise and focus on what matters. When modifying code, make minimal targeted changes unless asked for a rewrite.

## Autonomy Rules — CRITICAL
- When the user asks you to create, generate, or write a test: IMMEDIATELY call your tools to gather context, then produce the finished code. Do NOT describe what you plan to do. Do NOT ask for confirmation. The user's request IS the confirmation.
- NEVER ask the user for helper function names, item IDs, or file contents. You have tools to find all of this yourself:
  * `list_helpers` — lists all available helper functions with signatures
  * `read_file` — reads any helper file (e.g., src/helpers/piaac.js, src/helpers/auth.js)
  * `get_items` — looks up item details from the database
  * `search_tests` — finds example test patterns in existing scripts
- Your FIRST response to a code generation request should contain tool calls, NOT questions or plans.
- Call multiple tools in one response to gather all context at once.
- After gathering context, call `update_code` with the complete finished script.
- Only ask clarifying questions when the request is genuinely ambiguous (e.g., the user says "write a test" without specifying which item or what kind of test).

## When NOT to modify code
If the user asks a question or asks for an explanation — respond with text only. Do NOT generate or replace code unless explicitly asked to modify, create, generate, or fix it."""


def build_tool_descriptions():
    """Build tool descriptions from enabled tools in DB."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT id, name, description, parameters FROM ai_tools WHERE enabled = true ORDER BY id')
        cols = [c[0] for c in cursor.description]
        tools = [dict(zip(cols, row)) for row in cursor.fetchall()]

    lines = []
    for t in tools:
        params = t.get('parameters') or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except (json.JSONDecodeError, TypeError):
                params = {}
        param_str = ''
        if params.get('required'):
            param_str = f" Parameters: {', '.join(params['required'])}"
        if params.get('optional'):
            param_str += f" Optional: {', '.join(params['optional'])}"
        lines.append(f"- **{t['id']}**: {t['description']}{param_str}")
    return '\n'.join(lines)


def build_system_prompt(current_code, filename):
    """Build system prompt with tool descriptions and current code context."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT value FROM ai_settings WHERE key = 'system_prompt'")
            row = cursor.fetchone()
            base_prompt = row[0] if row else get_default_system_prompt()
            if isinstance(base_prompt, str):
                # value is stored as JSONB string (with quotes)
                try:
                    base_prompt = json.loads(base_prompt)
                except Exception:
                    pass
    except Exception:
        base_prompt = get_default_system_prompt()

    tool_desc = build_tool_descriptions()

    prompt = base_prompt + '\n\n'
    prompt += f'## Available Tools\n{tool_desc}\n\n'
    prompt += '## Tool Calling Format\nWhen you need to use a tool, include ONE tool per code block:\n'
    prompt += '```tool\n{"tool": "tool_id", "args": {"param": "value"}}\n```\n'
    prompt += 'For multiple tools, use SEPARATE ```tool blocks for each.\n'
    prompt += 'CRITICAL: Only use `update_code` when the user explicitly asks to modify, create, generate, or fix code.\n\n'
    prompt += '## Code Conventions\n'
    prompt += '- Use CommonJS `require()` syntax, NOT ES module `import` syntax.\n'
    prompt += '- Scripts in `tests/` import helpers with `../src/helpers/` paths. Scripts in `tests/items/` use `../../src/helpers/`.\n'
    prompt += '- Always pass env config to login: `const envConfig = loadEnvConfig(); await login(page, { env: envConfig });`\n'
    prompt += '- Use Playwright built-in `toHaveScreenshot()` or `page.screenshot()` for captures.\n\n'

    if current_code and current_code.strip() and current_code != '// Generated test code will appear here...':
        fname_part = f' ({filename})' if filename else ''
        prompt += f'## Current Script{fname_part}\nThe user is currently working with this code:\n```javascript\n{current_code}\n```\n'

    return prompt


def parse_tool_calls(response):
    """Parse tool calls from AI response text."""
    tool_calls = []
    text = response

    # Strategy 1: ```tool ... ``` blocks (may contain multiple tool calls)
    tool_block_re = re.compile(r'```tool\s*\n?([\s\S]*?)```')
    for match in tool_block_re.finditer(response):
        block_content = match.group(1).strip()
        # Try as single JSON object first
        parsed = _try_parse_tool_json(block_content)
        if parsed:
            tool_calls.append(parsed)
        else:
            # Multiple tool calls in one block — find each { and extract
            for obj_match in re.finditer(r'\{', block_content):
                json_str = _extract_balanced_json(block_content, obj_match.start())
                if json_str:
                    p = _try_parse_tool_json(json_str)
                    if p:
                        tool_calls.append(p)
        text = text.replace(match.group(0), '').strip()

    # Strategy 2: inline {"tool": ... } patterns (only if no block matches)
    if not tool_calls:
        start_re = re.compile(r'\{"tool"\s*:\s*"')
        for match in start_re.finditer(response):
            json_str = _extract_balanced_json(response, match.start())
            if json_str:
                parsed = _try_parse_tool_json(json_str)
                if parsed:
                    tool_calls.append(parsed)
                    text = text.replace(json_str, '').strip()

    text = re.sub(r'```\s*```', '', text).strip()
    # Clean up stray braces, "tool" markers, and empty lines
    text = re.sub(r'^\s*[{}]\s*$', '', text, flags=re.MULTILINE).strip()
    text = re.sub(r'^\s*tool\s*$', '', text, flags=re.MULTILINE).strip()
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text, tool_calls


def _try_parse_tool_json(s):
    try:
        parsed = json.loads(s)
        if parsed and parsed.get('tool'):
            return {'tool': parsed['tool'], 'args': parsed.get('args', {})}
    except Exception:
        pass
    return None


def _extract_balanced_json(s, start):
    if s[start] != '{':
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if escaped:
            escaped = False
            continue
        if ch == '\\' and in_string:
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def execute_tool(tool_id, args, context):
    """Execute an AI tool. Returns {success, result}."""
    from django.conf import settings
    from pathlib import Path
    import os

    # Verify tool is enabled
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM ai_tools WHERE id = %s', [tool_id])
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        return {'success': False, 'result': f'Unknown tool: {tool_id}'}
    tool = dict(zip(cols, row))
    if not tool['enabled']:
        return {'success': False, 'result': f'Tool "{tool_id}" is disabled'}

    tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
    project_root = Path(settings.PLAYWRIGHT_PROJECT_ROOT)

    if tool_id == 'explain_code':
        code = args.get('code') or context.get('current_code', '')
        if not code.strip():
            return {'success': True, 'result': 'No code is currently loaded.'}
        return {'success': True, 'result': f'Code provided ({len(code.splitlines())} lines). AI will explain it.'}

    elif tool_id == 'update_code':
        if not args.get('code'):
            return {'success': False, 'result': 'No code provided'}
        return {'success': True, 'result': {'code': args['code'], 'summary': args.get('summary', 'Code updated')}}

    elif tool_id == 'read_file':
        if not args.get('path'):
            return {'success': False, 'result': 'No file path provided'}
        normalized = args['path'].replace('\\', '/').lstrip('./')
        full_path = (project_root / normalized).resolve()
        safe_dirs = ['src/helpers', 'tests', 'src/config']
        if not str(full_path).startswith(str(project_root)):
            return {'success': False, 'result': 'Access denied: path outside project'}
        allowed = any(str(full_path).startswith(str(project_root / d)) for d in safe_dirs)
        if not allowed:
            return {'success': False, 'result': f'Access denied: only files in {safe_dirs} are readable'}
        try:
            content = full_path.read_text(encoding='utf-8')
            truncated = content[:4000] + '\n... (truncated)' if len(content) > 4000 else content
            return {'success': True, 'result': f'File: {normalized}\n```javascript\n{truncated}\n```'}
        except Exception as e:
            return {'success': False, 'result': f'Cannot read file: {e}'}

    elif tool_id == 'list_helpers':
        helpers_dir = project_root / 'src' / 'helpers'
        try:
            helpers = []
            if helpers_dir.exists():
                for f in helpers_dir.glob('*.js'):
                    content = f.read_text()
                    export_match = re.search(r'module\.exports\s*=\s*\{([^}]+)\}', content)
                    if export_match:
                        names = [n.strip() for n in export_match.group(1).split(',') if n.strip()]
                        for name in names:
                            sig_match = re.search(rf'(?:async\s+)?function\s+{re.escape(name)}\s*\(([^)]*)\)', content)
                            sig = f'{name}({sig_match.group(1) if sig_match else ""})'
                            helpers.append(f'- `{sig}` (from {f.name})')
            result = 'Available helpers:\n' + '\n'.join(helpers) if helpers else 'No helpers found.'
            return {'success': True, 'result': result}
        except Exception as e:
            return {'success': False, 'result': f'Error scanning helpers: {e}'}

    elif tool_id == 'analyze_script':
        code = args.get('code') or context.get('current_code', '')
        if not code.strip():
            return {'success': True, 'result': 'No code to analyze.'}
        # Basic Python-side syntax check isn't possible for JS, just report OK
        return {'success': True, 'result': 'Script syntax check: passed (server-side JS parsing not available; run dry-run for full check).'}

    elif tool_id == 'search_tests':
        query = args.get('query', '').strip()
        if not query:
            return {'success': False, 'result': 'No search query provided'}
        results = []
        for f in tests_dir.rglob('*.spec.js'):
            try:
                content = f.read_text(encoding='utf-8', errors='replace')
                lines = content.splitlines()
                matches = [{'line': i + 1, 'text': l.strip()} for i, l in enumerate(lines) if query.lower() in l.lower()]
                if matches:
                    results.append({'file': str(f.relative_to(project_root)), 'matches': matches[:3]})
            except Exception:
                pass
        if not results:
            return {'success': True, 'result': f'No matches found for "{query}"'}
        output = '\n\n'.join(
            f"**{r['file']}**\n" + '\n'.join(f"  L{m['line']}: {m['text']}" for m in r['matches'])
            for r in results[:5]
        )
        return {'success': True, 'result': f'Found {len(results)} file(s) matching "{query}":\n\n{output}'}

    elif tool_id == 'get_items':
        try:
            conditions = []
            params = []
            if args.get('assessmentId'):
                conditions.append('i.assessment_id = %s')
                params.append(args['assessmentId'])
            if args.get('search'):
                conditions.append('(i.item_id ILIKE %s OR i.title ILIKE %s)')
                params.extend([f"%{args['search']}%", f"%{args['search']}%"])
            where = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
            limit = min(int(args.get('limit', 20)), 50)
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT i.numeric_id, i.item_id, i.title, i.category, i.tier, a.name AS assessment_name '
                    f'FROM items i LEFT JOIN assessments a ON i.assessment_id = a.id '
                    f'{where} ORDER BY i.numeric_id LIMIT %s',
                    params + [limit]
                )
                cols = [c[0] for c in cursor.description]
                items = [dict(zip(cols, r)) for r in cursor.fetchall()]
            if not items:
                return {'success': True, 'result': 'No items found.'}
            output = '\n'.join(
                f"- **{i['item_id']}** — {i['title'] or 'Untitled'} ({i['category']}, tier: {i['tier']})"
                + (f" [{i['assessment_name']}]" if i.get('assessment_name') else '')
                for i in items
            )
            return {'success': True, 'result': f'Found {len(items)} item(s):\n{output}'}
        except Exception as e:
            return {'success': False, 'result': f'Database error: {e}'}

    elif tool_id == 'get_run_screenshots':
        run_id = args.get('run_id', '').strip()
        if not run_id:
            return {'success': False, 'result': 'No run_id provided'}
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT rs.name, rs.file_path, rs.project_name, rs.flagged, rs.flag_notes,
                              trs.script_path
                       FROM run_screenshots rs
                       LEFT JOIN test_run_scripts trs ON rs.run_script_id = trs.id
                       WHERE rs.run_id = %s::uuid
                       ORDER BY rs.name""",
                    [run_id]
                )
                cols = [c[0] for c in cursor.description]
                rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
            if not rows:
                return {'success': True, 'result': f'No screenshots found for run {run_id}.'}
            output = '\n'.join(
                f"- **{r['name']}** — `{r['file_path']}` ({r['project_name']})"
                + (' [FLAGGED]' if r['flagged'] else '')
                + (f" Note: {r['flag_notes']}" if r.get('flag_notes') else '')
                + (f" (from {r['script_path']})" if r.get('script_path') else '')
                for r in rows
            )
            return {'success': True, 'result': f'Found {len(rows)} screenshot(s) for run {run_id[:8]}:\n{output}'}
        except Exception as e:
            return {'success': False, 'result': f'Database error: {e}'}

    return {'success': False, 'result': f'No executor for tool: {tool_id}'}


# Phrases that indicate the AI is planning/asking instead of acting
_PLANNING_PATTERNS = re.compile(
    r'\b(I will|I\'ll|Let me|Proceeding to|I\'m going to|I can now|'
    r'I\'ll now|going to|plan to|here\'s what|steps?:|'
    r'I need to know|I need to fetch|please confirm|please provide|'
    r'can you (provide|confirm|share)|do you want me to|shall I|'
    r'before I (can|proceed|create|generate)|first I need)\b',
    re.IGNORECASE
)


def _looks_like_planning(text):
    """Return True if response text looks like a plan/request rather than a final answer."""
    if not text or len(text) > 2000:
        return False
    return bool(_PLANNING_PATTERNS.search(text))


def chat(message, conversation_id, current_code, filename):
    """Process a chat message with an agentic tool loop.

    When the AI calls research tools (read_file, list_helpers, etc.) the
    results are fed back automatically and the AI continues until it either
    produces a text-only reply, calls update_code, or hits MAX_LOOP.

    If the AI responds with just a planning message (no tools), it is
    automatically nudged to continue and actually execute the work.
    """
    from ai.provider import get_provider

    # Tools that trigger auto-continue (research / context-gathering)
    RESEARCH_TOOLS = {'read_file', 'list_helpers', 'search_tests', 'get_items',
                      'explain_code', 'analyze_script', 'get_run_screenshots'}

    # Load or create conversation
    if conversation_id:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id, messages FROM ai_conversations WHERE id = %s', [conversation_id])
            row = cursor.fetchone()
        if row:
            conv_id = str(row[0])
            messages = row[1] if isinstance(row[1], list) else json.loads(row[1])
        else:
            conv_id = str(uuid.uuid4())
            messages = []
    else:
        conv_id = str(uuid.uuid4())
        messages = []

    # Build system prompt
    system_prompt = build_system_prompt(current_code, filename)

    # Add user message
    messages.append({'role': 'user', 'content': message})

    # Trim to max turns
    if len(messages) > MAX_TURNS * 2:
        messages = messages[-MAX_TURNS * 2:]

    provider = get_provider()
    all_tool_results = []
    code_update = None
    final_text = ''
    intermediate_messages = []  # assistant texts from mid-loop iterations
    steps = []  # track what happened at each loop iteration

    for iteration in range(MAX_LOOP):
        # Call AI
        ai_messages = [{'role': 'system', 'content': system_prompt}] + messages
        raw_response = provider.chat_completion(ai_messages, {'max_tokens': 8000})

        # Parse tool calls
        text, tool_calls = parse_tool_calls(raw_response)

        # Add assistant message to conversation
        messages.append({'role': 'assistant', 'content': raw_response})

        if not tool_calls:
            # Empty response — the AI returned nothing (possibly content filter or token issue)
            if (not text or not text.strip()) and iteration < MAX_LOOP - 1:
                steps.append({
                    'iteration': iteration + 1,
                    'tools': [],
                    'note': 'auto-continue (empty response)',
                })
                messages.pop()  # remove the empty assistant message
                messages.append({'role': 'user', 'content':
                    'Your previous response was empty. You MUST respond now. '
                    'If you have gathered enough context from the tools, call update_code '
                    'with the complete finished script. If you need to explain something, '
                    'write your explanation as plain text.'})
                continue

            # No tools called — check if the AI is just announcing a plan
            if _looks_like_planning(text) and iteration < MAX_LOOP - 1:
                # Save this as an intermediate message and nudge the AI to continue
                intermediate_messages.append(text)
                steps.append({
                    'iteration': iteration + 1,
                    'tools': [],
                    'note': 'auto-continue (planning response)',
                })
                messages.append({'role': 'user', 'content':
                    'Do not ask me for information — you have tools to find it yourself. '
                    'Call list_helpers to see available helper functions. '
                    'Call read_file to read src/helpers/piaac.js and src/helpers/auth.js. '
                    'Call get_items to look up item details. '
                    'Then call update_code with the complete finished script. '
                    'Do all of this NOW in your next response — do not ask for confirmation.'})
                continue

            # Genuine final text response — we're done
            final_text = text
            break

        # If we have both text and tool calls, save the text as intermediate
        if text.strip() and len(text.strip()) > 3:
            intermediate_messages.append(text)

        # Execute tools
        needs_continue = False
        tool_result_parts = []

        for tc in tool_calls:
            result = execute_tool(tc['tool'], tc['args'],
                                  {'current_code': current_code, 'filename': filename})
            all_tool_results.append({
                'tool': tc['tool'],
                'args': tc['args'],
                'success': result['success'],
                'result': result['result'],
            })

            if tc['tool'] == 'update_code' and result['success'] and isinstance(result.get('result'), dict):
                code_update = {
                    'code': result['result']['code'],
                    'summary': result['result'].get('summary', 'Code updated'),
                }
                # update_code delivered code — update current_code for any further iterations
                current_code = result['result']['code']
            elif tc['tool'] in RESEARCH_TOOLS:
                needs_continue = True

            # Format tool result for the AI to consume
            result_text = result['result'] if isinstance(result['result'], str) else json.dumps(result['result'])
            tool_result_parts.append(
                f"[Tool: {tc['tool']}] {'OK' if result['success'] else 'ERROR'}: {result_text}"
            )

        steps.append({
            'iteration': iteration + 1,
            'tools': [tc['tool'] for tc in tool_calls],
        })

        # If only update_code was called (no research tools), we're done
        if not needs_continue:
            final_text = text
            break

        # Feed tool results back — escalate urgency on later iterations
        tool_feedback = "Tool results:\n\n" + "\n\n".join(tool_result_parts)
        if iteration >= 3:
            tool_feedback += (
                "\n\nYou have gathered enough context. STOP reading more files. "
                "Call update_code NOW with the complete finished script. "
                "Do NOT call any more research tools."
            )
        elif iteration >= 1:
            tool_feedback += (
                "\n\nYou should have enough context now. "
                "Generate the complete script and call update_code. "
                "Only read more files if absolutely necessary."
            )
        else:
            tool_feedback += (
                "\n\nContinue with the task. If you have enough context, "
                "generate the code now using update_code."
            )
        messages.append({'role': 'user', 'content': tool_feedback})

    # If code was updated but no final text, generate a completion message
    if code_update and not final_text:
        final_text = f"Done — {code_update['summary']}. The script is ready in the editor. You can review it, then Save or Save & Run."

    # If the loop exhausted without producing any output, provide a fallback
    if not final_text and not code_update:
        tool_names = [t['tool'] for t in all_tool_results]
        if tool_names:
            final_text = (
                f"I gathered context using {', '.join(tool_names)} but wasn't able to "
                f"generate a complete response. This can happen when the task is complex "
                f"or the AI service returned an incomplete response. "
                f"Please try again — you can simplify the request or break it into steps."
            )
        else:
            final_text = (
                "I wasn't able to generate a response. The AI service may be temporarily "
                "unavailable. Please try again."
            )

    # Save conversation to DB
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO ai_conversations (id, messages, created_at, last_active_at)
               VALUES (%s, %s, now(), now())
               ON CONFLICT (id) DO UPDATE SET messages = EXCLUDED.messages, last_active_at = now()""",
            [conv_id, json.dumps(messages)]
        )

    return {
        'conversationId': conv_id,
        'response': final_text,
        'intermediateMessages': intermediate_messages,
        'codeUpdate': code_update,
        'steps': steps,
        'toolsUsed': [
            {
                'tool': t['tool'],
                'success': t['success'],
                'summary': (t['result'][:200] if isinstance(t['result'], str)
                            else t['result'].get('summary', ''))
                           if t.get('result') else '',
            }
            for t in all_tool_results
        ],
    }
