import json
import re
import time
import uuid as _uuid
from pathlib import Path
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import connection
from core.mixins import get_user_env_ids


def fix_helper_paths(code, rel_path):
    """Auto-correct require paths for src/helpers based on the script's location.
    Scripts in tests/ need ../src/helpers/, scripts in tests/items/ need ../../src/helpers/, etc.
    """
    depth = rel_path.count('/')  # 0 = tests root, 1 = one subdir, etc.
    correct_prefix = '../' * (depth + 1)  # tests/ root → ../, tests/items/ → ../../
    # Fix common wrong paths: too many or too few ../ segments
    code = re.sub(
        r"""require\(\s*['"](\.\./)*src/helpers/""",
        f"require('{correct_prefix}src/helpers/",
        code,
    )
    return code


@login_required(login_url='/login/')
def builder_view(request):
    file_content = None
    file_path = None
    filename = None
    script_meta = None
    run_history = []
    assessment = None
    items = []
    assessments = []
    environments = []

    tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)

    if request.GET.get('file'):
        file_path = request.GET['file']
        full_path = (tests_dir / file_path).resolve()
        if str(full_path).startswith(str(tests_dir)) and full_path.exists():
            file_content = full_path.read_text(encoding='utf-8')
            filename = full_path.name

        # Load script metadata
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT ts.*, i.title AS item_title, i.numeric_id AS item_numeric_id,
                              a.name AS assessment_name, a.numeric_id AS assessment_numeric_id,
                              e.name AS environment_name
                       FROM test_scripts ts
                       LEFT JOIN items i ON ts.item_id = i.item_id
                       LEFT JOIN assessments a ON ts.assessment_id = a.id
                       LEFT JOIN environments e ON ts.environment_id = e.id
                       WHERE ts.script_path = %s""",
                    [file_path]
                )
                cols = [c[0] for c in cursor.description]
                row = cursor.fetchone()
                if row:
                    script_meta = dict(zip(cols, row))
                    # Ensure ai_config is a dict
                    ai_cfg = script_meta.get('ai_config')
                    if isinstance(ai_cfg, str):
                        try:
                            script_meta['ai_config'] = json.loads(ai_cfg)
                        except Exception:
                            script_meta['ai_config'] = {}
                    elif not isinstance(ai_cfg, dict):
                        script_meta['ai_config'] = {}
        except Exception:
            pass

        # Load run history
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT trs.id, trs.run_id, trs.status, trs.duration_ms, trs.error_message,
                              trs.completed_at, trs.trace_path, trs.video_path,
                              r.trigger_type, s.name AS suite_name
                       FROM test_run_scripts trs
                       JOIN test_runs r ON r.id = trs.run_id
                       LEFT JOIN test_suites s ON r.suite_id = s.id
                       WHERE trs.script_path = %s
                       ORDER BY trs.completed_at DESC NULLS LAST LIMIT 50""",
                    [file_path]
                )
                cols = [c[0] for c in cursor.description]
                run_history = [dict(zip(cols, r)) for r in cursor.fetchall()]
        except Exception:
            pass

    # Load assessment info
    assessment_id = request.GET.get('assessment') or (script_meta and script_meta.get('assessment_id'))
    if assessment_id:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT a.id, a.name, a.subject, a.grade, e.name AS env_name
                       FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id
                       WHERE a.id = %s""",
                    [assessment_id]
                )
                cols = [c[0] for c in cursor.description]
                row = cursor.fetchone()
                if row:
                    assessment = dict(zip(cols, row))
        except Exception:
            pass

    # Load items and assessments for dropdowns
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT numeric_id, item_id, title FROM items ORDER BY numeric_id')
            cols = [c[0] for c in cursor.description]
            items = [dict(zip(cols, r)) for r in cursor.fetchall()]
            cursor.execute('SELECT id, name FROM assessments ORDER BY name')
            cols = [c[0] for c in cursor.description]
            assessments = [dict(zip(cols, r)) for r in cursor.fetchall()]
    except Exception:
        pass

    # Load environments for the user (RBAC-scoped)
    env_ids = get_user_env_ids(request.user)
    try:
        with connection.cursor() as cursor:
            if env_ids is None:
                cursor.execute('SELECT id, name FROM environments ORDER BY name')
            else:
                cursor.execute(
                    'SELECT id, name FROM environments WHERE id = ANY(%s::uuid[]) ORDER BY name',
                    [tuple(str(e) for e in env_ids)]
                )
            environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]
    except Exception:
        pass

    # Load chat conversation ID and test summary from script metadata
    chat_conversation_id = None
    test_summary = None
    if script_meta:
        chat_conversation_id = script_meta.get('chat_conversation_id')
        test_summary = script_meta.get('test_summary')

    # Load baselines for this script
    baselines = []
    if file_path:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, browser, viewport, file_path, source_run_id, created_at
                    FROM test_script_baselines
                    WHERE script_path = %s
                    ORDER BY name
                """, [file_path])
                cols = [c[0] for c in cursor.description]
                baselines = [dict(zip(cols, r)) for r in cursor.fetchall()]
        except Exception:
            pass

    return render(request, 'builder/builder.html', {
        'file_content': file_content,
        'file_path': file_path,
        'filename': filename,
        'script_meta': script_meta,
        'run_history': run_history,
        'assessment': assessment,
        'items': items,
        'assessments': assessments,
        'environments': environments,
        'test_type': request.GET.get('type'),
        'baseline_version': request.GET.get('baseline'),
        'chat_conversation_id': str(chat_conversation_id) if chat_conversation_id else None,
        'test_summary': test_summary,
        'baselines': baselines,
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_chat(request):
    try:
        data = json.loads(request.body)
        message = data.get('message')
        if not message:
            return JsonResponse({'error': 'Message is required'}, status=400)
        from builder.chat_manager import chat
        result = chat(
            message,
            data.get('conversationId'),
            data.get('currentCode', ''),
            data.get('filename', ''),
            script_context=data.get('context'),
            current_summary=data.get('currentSummary', ''),
        )
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': str(e), 'conversationId': data.get('conversationId')})


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_delete(request):
    """Delete a script file and its DB metadata (or archive if archiving enabled)."""
    try:
        data = json.loads(request.body)
        file_path = data.get('path', '').strip()
        if not file_path:
            return JsonResponse({'error': 'No path provided'}, status=400)

        tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
        full_path = (tests_dir / file_path).resolve()

        # Security: ensure path stays within tests dir
        if not str(full_path).startswith(str(tests_dir.resolve())):
            return JsonResponse({'error': 'Invalid path'}, status=400)

        with connection.cursor() as cursor:
            # Check if archiving is enabled
            cursor.execute("SELECT value FROM ai_settings WHERE key = 'archiving_enabled'")
            row = cursor.fetchone()
            archiving_enabled = False
            if row:
                val = row[0]
                if isinstance(val, str):
                    try:
                        archiving_enabled = json.loads(val)
                    except Exception:
                        pass
                elif isinstance(val, bool):
                    archiving_enabled = val

            if archiving_enabled:
                _archive_script(cursor, file_path, full_path, request.user)
            else:
                _hard_delete_script(cursor, file_path, full_path)

        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _get_archiving_config(cursor):
    """Read archiving_enabled and retention_days from settings."""
    cursor.execute(
        "SELECT key, value FROM ai_settings WHERE key IN ('archiving_enabled', 'archiving_retention_days')"
    )
    cfg = {r[0]: r[1] for r in cursor.fetchall()}
    enabled = False
    val = cfg.get('archiving_enabled')
    if isinstance(val, str):
        try:
            enabled = json.loads(val)
        except Exception:
            pass
    elif isinstance(val, bool):
        enabled = val
    days = 30
    d = cfg.get('archiving_retention_days')
    if isinstance(d, str):
        try:
            days = int(json.loads(d))
        except Exception:
            pass
    elif isinstance(d, (int, float)):
        days = int(d)
    return enabled, days


def _cancel_runs_for_script(cursor, script_path):
    """Cancel any running or queued test runs that include this script."""
    cursor.execute("""
        SELECT DISTINCT trs.run_id FROM test_run_scripts trs
        JOIN test_runs r ON r.id = trs.run_id
        WHERE trs.script_path = %s AND r.status IN ('running', 'scheduled', 'queued')
    """, [script_path])
    run_ids = [row[0] for row in cursor.fetchall()]
    for run_id in run_ids:
        cursor.execute(
            "UPDATE test_runs SET status = 'cancelled', completed_at = COALESCE(completed_at, now()) WHERE id = %s",
            [run_id]
        )
        cursor.execute(
            "UPDATE test_run_scripts SET status = 'cancelled', completed_at = COALESCE(completed_at, now()) WHERE run_id = %s AND status IN ('pending', 'running', 'queued')",
            [run_id]
        )


def _archive_script(cursor, script_path, full_path, user):
    """Move a script into the archive table."""
    _cancel_runs_for_script(cursor, script_path)
    _, retention_days = _get_archiving_config(cursor)

    # Read script metadata
    cursor.execute("""
        SELECT id, description, environment_id, item_id, assessment_id, test_type,
               ai_config, tags, category, test_summary, browser, viewport, created_at
        FROM test_scripts WHERE script_path = %s
    """, [script_path])
    meta = cursor.fetchone()

    file_content = None
    if full_path.exists():
        file_content = full_path.read_text(encoding='utf-8')

    original_id = meta[0] if meta else 0
    description = meta[1] if meta else None
    environment_id = meta[2] if meta else None
    item_id = meta[3] if meta else None
    assessment_id = meta[4] if meta else None
    test_type = meta[5] if meta else 'functional'
    ai_config = meta[6] if meta else '{}'
    tags = meta[7] if meta else '[]'
    category = meta[8] if meta else None
    test_summary = meta[9] if meta else None
    browser = meta[10] if meta else 'chromium'
    viewport = meta[11] if meta else '1920x1080'
    original_created_at = meta[12] if meta else None

    if isinstance(ai_config, dict):
        ai_config = json.dumps(ai_config)
    if isinstance(tags, list):
        tags = json.dumps(tags)

    cursor.execute("""
        INSERT INTO test_script_archives
            (script_path, description, environment_id, item_id, assessment_id, test_type,
             ai_config, tags, category, test_summary, browser, viewport,
             file_content, original_id, archived_by_id, archived_at, expires_at, original_created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s,
                %s, %s, %s, now(), now() + interval '%s days', %s)
    """, [script_path, description,
          str(environment_id) if environment_id else None,
          item_id,
          str(assessment_id) if assessment_id else None,
          test_type, ai_config, tags, category, test_summary,
          browser, viewport, file_content, original_id,
          user.id if user and user.is_authenticated else None,
          retention_days, original_created_at])

    # Remove from active tables
    cursor.execute('DELETE FROM test_suite_scripts WHERE script_path = %s', [script_path])
    cursor.execute('DELETE FROM test_scripts WHERE script_path = %s', [script_path])

    # Delete file from disk
    if full_path.exists():
        full_path.unlink()


def _hard_delete_script(cursor, script_path, full_path):
    """Permanently delete a script and cascade-delete all associated run data."""
    _cancel_runs_for_script(cursor, script_path)
    from admin_config.views import _cascade_delete_run_data

    # Delete suite references
    cursor.execute('DELETE FROM test_suite_scripts WHERE script_path = %s', [script_path])

    # Delete baselines
    cursor.execute('DELETE FROM test_script_baselines WHERE script_path = %s', [script_path])

    # Delete run data
    _cascade_delete_run_data(cursor, script_path)

    # Delete script record
    cursor.execute('DELETE FROM test_scripts WHERE script_path = %s', [script_path])

    # Delete file
    if full_path.exists():
        full_path.unlink()


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_save(request):
    try:
        data = json.loads(request.body)
        code = data.get('code')
        environment_id = data.get('environment_id')
        if not code:
            return JsonResponse({'error': 'No code to save'}, status=400)
        tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
        tests_dir.mkdir(parents=True, exist_ok=True)
        filename = f'{_uuid.uuid4()}.spec.js'
        code = fix_helper_paths(code, filename)
        filepath = tests_dir / filename
        filepath.write_text(code, encoding='utf-8')
        # Register in DB with environment
        rel_path = filename
        with connection.cursor() as cursor:
            if environment_id:
                cursor.execute(
                    """INSERT INTO test_scripts (script_path, environment_id, test_type, tags, ai_config, browser, viewport, created_at, updated_at)
                       VALUES (%s, %s::uuid, 'functional', '[]'::jsonb, '{}'::jsonb, 'chromium', '1920x1080', now(), now())
                       ON CONFLICT (script_path) DO UPDATE SET updated_at = now()""",
                    [rel_path, environment_id]
                )
            else:
                cursor.execute(
                    """INSERT INTO test_scripts (script_path, test_type, tags, ai_config, browser, viewport, created_at, updated_at)
                       VALUES (%s, 'functional', '[]'::jsonb, '{}'::jsonb, 'chromium', '1920x1080', now(), now())
                       ON CONFLICT (script_path) DO UPDATE SET updated_at = now()""",
                    [rel_path]
                )
        return JsonResponse({'path': rel_path})
    except Exception as e:
        return JsonResponse({'error': str(e)})


@login_required(login_url='/login/')
def api_chat_history(request):
    """Return chat messages for a conversation (GET ?conversationId=...)."""
    conv_id = request.GET.get('conversationId')
    if not conv_id:
        return JsonResponse({'messages': []})
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT messages FROM ai_conversations WHERE id = %s', [conv_id])
            row = cursor.fetchone()
        if not row:
            return JsonResponse({'messages': []})
        messages = row[0] if isinstance(row[0], list) else json.loads(row[0])
        return JsonResponse({'messages': messages})
    except Exception as e:
        return JsonResponse({'error': str(e), 'messages': []})


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_link_conversation(request):
    """Link a conversation to a test script."""
    try:
        data = json.loads(request.body)
        file_path = data.get('filePath', '').strip()
        conv_id = data.get('conversationId', '').strip()
        if not file_path or not conv_id:
            return JsonResponse({'error': 'Missing filePath or conversationId'}, status=400)
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE test_scripts SET chat_conversation_id = %s, updated_at = now() WHERE script_path = %s',
                [conv_id, file_path]
            )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_update_summary(request):
    """Update the test summary for a script."""
    try:
        data = json.loads(request.body)
        file_path = data.get('filePath', '').strip()
        summary = data.get('summary', '').strip()
        if not file_path:
            return JsonResponse({'error': 'Missing filePath'}, status=400)
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE test_scripts SET test_summary = %s, updated_at = now() WHERE script_path = %s',
                [summary or None, file_path]
            )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_clear_chat(request):
    """Clear the chat conversation link for a script."""
    try:
        data = json.loads(request.body)
        file_path = data.get('filePath', '').strip()
        if not file_path:
            return JsonResponse({'error': 'Missing filePath'}, status=400)
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE test_scripts SET chat_conversation_id = NULL, updated_at = now() WHERE script_path = %s',
                [file_path]
            )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_duplicate(request):
    """Duplicate a test script: copy file + metadata under a new name."""
    try:
        data = json.loads(request.body)
        source_path = data.get('sourcePath', '').strip()
        new_name = data.get('newName', '').strip()
        if not source_path:
            return JsonResponse({'error': 'Missing sourcePath'}, status=400)
        if not new_name:
            return JsonResponse({'error': 'Missing newName'}, status=400)

        # Optional overrides for item/assessment
        override_item = data.get('itemId')         # '' = keep source, '__none__' = clear
        override_assessment = data.get('assessmentId')  # '' = keep source, '__none__' = clear

        tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
        source_full = (tests_dir / source_path).resolve()

        # Security: ensure source is within tests dir
        if not str(source_full).startswith(str(tests_dir.resolve())):
            return JsonResponse({'error': 'Invalid source path'}, status=400)
        if not source_full.exists():
            return JsonResponse({'error': 'Source file not found'}, status=404)

        # Copy the file with a UUID filename
        dest_filename = f'{_uuid.uuid4()}.spec.js'
        dest_full = tests_dir / dest_filename
        code = source_full.read_text(encoding='utf-8')
        dest_full.write_text(code, encoding='utf-8')
        new_rel_path = dest_filename

        # Copy metadata from source script
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT item_id, assessment_id, category, test_type, description,
                          environment_id, browser, viewport, ai_config, test_summary
                   FROM test_scripts WHERE script_path = %s""",
                [source_path]
            )
            row = cursor.fetchone()

        if row:
            item_id, assessment_id, category, test_type, description, environment_id, browser, viewport, ai_config, test_summary = row
            # Ensure ai_config is a JSON string
            if isinstance(ai_config, dict):
                ai_config = json.dumps(ai_config)
            elif not isinstance(ai_config, str):
                ai_config = '{}'
            # Use the user-provided name as the description
            new_desc = new_name

            # Apply item/assessment overrides
            if override_item == '__none__':
                item_id = None
            elif override_item:
                item_id = override_item

            if override_assessment == '__none__':
                assessment_id = None
            elif override_assessment:
                assessment_id = override_assessment

            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO test_scripts
                       (script_path, item_id, assessment_id, category, test_type, description,
                        environment_id, browser, viewport, ai_config, test_summary, tags, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, COALESCE(%s, 'functional'), %s,
                               %s::uuid, %s, %s, COALESCE(%s::jsonb, '{}'::jsonb), %s, '[]'::jsonb, now(), now())""",
                    [new_rel_path, item_id, str(assessment_id) if assessment_id else None,
                     category, test_type, new_desc,
                     environment_id, browser or 'chromium', viewport or '1920x1080', ai_config, test_summary]
                )
        else:
            # No source metadata — create minimal record with any overrides
            new_item = None if (not override_item or override_item == '__none__') else override_item
            new_assess = None if (not override_assessment or override_assessment == '__none__') else override_assessment
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO test_scripts
                       (script_path, item_id, assessment_id, description, test_type, tags, ai_config, browser, viewport, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, 'functional', '[]'::jsonb, '{}'::jsonb, 'chromium', '1920x1080', now(), now())""",
                    [new_rel_path, new_item, new_assess, new_name]
                )

        return JsonResponse({'ok': True, 'path': new_rel_path})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_generate_baseline(request):
    """Run a test script and promote its screenshots to baselines."""
    try:
        data = json.loads(request.body)
        script_path = data.get('scriptPath', '').strip()
        if not script_path:
            return JsonResponse({'error': 'scriptPath required'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT environment_id, browser, viewport FROM test_scripts WHERE script_path = %s',
                [script_path]
            )
            ts_row = cursor.fetchone()
            environment_id = ts_row[0] if ts_row else None
            script_browser = (ts_row[1] if ts_row else None) or 'chromium'
            script_viewport = (ts_row[2] if ts_row else None) or '1920x1080'

            if data.get('browser'):
                script_browser = data['browser']
            if data.get('viewport'):
                script_viewport = data['viewport']

            cursor.execute(
                """INSERT INTO test_runs (id, status, trigger_type, environment_id, config, notes, queued_at)
                   VALUES (gen_random_uuid(), 'running', 'baseline', %s, '{}', %s, now()) RETURNING id""",
                [str(environment_id) if environment_id else None,
                 f'Baseline generation: {script_path}']
            )
            run_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO test_run_scripts (id, run_id, script_path, browser, viewport, status)
                   VALUES (gen_random_uuid(), %s, %s, %s, %s, 'queued')""",
                [str(run_id), script_path, script_browser, script_viewport]
            )

        from core.utils import spawn_background_task
        def _run_baseline(rid=str(run_id), sp=script_path):
            try:
                from tasks.run_tasks import execute_baseline_generation
                execute_baseline_generation(rid, sp)
            except Exception as e:
                print(f'[Baseline] generation error: {e}')
                from django.db import connection as conn
                with conn.cursor() as cur:
                    cur.execute("UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
                    cur.execute("UPDATE test_run_scripts SET status='error', error_message=%s, completed_at=now() WHERE run_id=%s AND status IN ('queued','running')", [str(e), rid])
        spawn_background_task(_run_baseline)

        return JsonResponse({'runId': str(run_id), 'status': 'running'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_delete_baseline(request):
    """Delete a specific baseline screenshot."""
    try:
        data = json.loads(request.body)
        baseline_id = data.get('id', '').strip()
        if not baseline_id:
            return JsonResponse({'error': 'id required'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM test_script_baselines WHERE id = %s', [baseline_id])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_clear_baselines(request):
    """Delete all baselines for a script."""
    try:
        data = json.loads(request.body)
        script_path = data.get('scriptPath', '').strip()
        if not script_path:
            return JsonResponse({'error': 'scriptPath required'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM test_script_baselines WHERE script_path = %s', [script_path])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
