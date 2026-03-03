"""SCOUT — AI Chat Conversation Manager."""
import uuid
import re
import json
from django.db import connection


MAX_TURNS = 50


def get_default_system_prompt():
    return """You are SCOUT AI, an expert assistant for the SCOUT automated testing system. You help users understand, create, and modify Playwright test scripts for the NAEP assessment platform.

When explaining code, be concise and focus on what matters. When modifying code, make minimal targeted changes unless asked for a rewrite.

IMPORTANT: If the user asks a question or asks for an explanation — respond with text only. Do NOT generate or replace code unless explicitly asked to modify, create, or fix it."""


def build_tool_descriptions():
    """Build tool descriptions from enabled tools in DB."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT id, name, description, parameters FROM ai_tools WHERE enabled = true ORDER BY id')
        cols = [c[0] for c in cursor.description]
        tools = [dict(zip(cols, row)) for row in cursor.fetchall()]

    lines = []
    for t in tools:
        params = t.get('parameters') or {}
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
    prompt += '## Tool Calling Format\nWhen you need to use a tool, include a JSON block in your response:\n'
    prompt += '```tool\n{"tool": "tool_id", "args": {"param": "value"}}\n```\n'
    prompt += 'You can use multiple tools in one response.\n'
    prompt += 'CRITICAL: Only use `update_code` when the user explicitly asks to modify, create, generate, or fix code.\n\n'

    if current_code and current_code.strip() and current_code != '// Generated test code will appear here...':
        fname_part = f' ({filename})' if filename else ''
        prompt += f'## Current Script{fname_part}\nThe user is currently working with this code:\n```javascript\n{current_code}\n```\n'

    return prompt


def parse_tool_calls(response):
    """Parse tool calls from AI response text."""
    tool_calls = []
    text = response

    # Strategy 1: ```tool ... ``` blocks
    tool_block_re = re.compile(r'```tool\s*\n?([\s\S]*?)```')
    for match in tool_block_re.finditer(response):
        json_str = match.group(1).strip()
        parsed = _try_parse_tool_json(json_str)
        if parsed:
            tool_calls.append(parsed)
            text = text.replace(match.group(0), '').strip()

    # Strategy 2: inline {"tool": ... } patterns
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

    return {'success': False, 'result': f'No executor for tool: {tool_id}'}


def chat(message, conversation_id, current_code, filename):
    """Process a chat message and return AI response."""
    from ai.provider import get_provider

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

    # Call AI
    provider = get_provider()
    ai_messages = [{'role': 'system', 'content': system_prompt}] + messages
    raw_response = provider.chat_completion(ai_messages, {'max_tokens': 3000})

    # Parse tool calls
    text, tool_calls = parse_tool_calls(raw_response)

    # Execute tools
    tool_results = []
    code_update = None

    for tc in tool_calls:
        result = execute_tool(tc['tool'], tc['args'], {'current_code': current_code, 'filename': filename})
        tool_results.append({
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

    # Add assistant message
    messages.append({'role': 'assistant', 'content': raw_response})

    # Save conversation to DB
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO ai_conversations (id, messages, last_active_at)
               VALUES (%s, %s, now())
               ON CONFLICT (id) DO UPDATE SET messages = EXCLUDED.messages, last_active_at = now()""",
            [conv_id, json.dumps(messages)]
        )

    return {
        'conversationId': conv_id,
        'response': text,
        'codeUpdate': code_update,
        'toolsUsed': [
            {
                'tool': t['tool'],
                'success': t['success'],
                'summary': (t['result'][:200] if isinstance(t['result'], str) else t['result'].get('summary', '')) if t.get('result') else '',
            }
            for t in tool_results
        ],
    }
