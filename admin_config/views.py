import json
import shutil
from pathlib import Path
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import connection


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/')
        if not request.user.is_staff:
            return HttpResponseForbidden('Admin access required.')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _upsert_setting(cursor, key, value):
    cursor.execute(
        """INSERT INTO ai_settings (key, value, updated_at) VALUES (%s, %s, now())
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
        [key, json.dumps(value)]
    )


@admin_required
def ai_settings(request):
    with connection.cursor() as cursor:
        cursor.execute('SELECT key, value FROM ai_settings ORDER BY key')
        cols = [c[0] for c in cursor.description]
        settings_rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        settings_dict = {r['key']: r['value'] for r in settings_rows}

        cursor.execute('SELECT * FROM ai_tools ORDER BY category, name')
        cols = [c[0] for c in cursor.description]
        tools = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Extract per-feature provider settings
    def _load_json(val):
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        return val

    text_provider_type = _load_json(settings_dict.get('text_provider_type', '"default"'))
    text_provider_config = _load_json(settings_dict.get('text_provider_config', '{}'))
    vision_provider_type = _load_json(settings_dict.get('vision_provider_type', '"default"'))
    vision_provider_config = _load_json(settings_dict.get('vision_provider_config', '{}'))

    return render(request, 'admin_config/ai_settings.html', {
        'settings': settings_dict,
        'tools': tools,
        'provider': settings.AI_PROVIDER,
        'success': request.GET.get('success'),
        'tab': request.GET.get('tab', 'prompt'),
        'text_provider_type': text_provider_type or 'default',
        'text_provider_config': json.dumps(text_provider_config if isinstance(text_provider_config, dict) else {}),
        'vision_provider_type': vision_provider_type or 'default',
        'vision_provider_config': json.dumps(vision_provider_config if isinstance(vision_provider_config, dict) else {}),
    })


@admin_required
def update_prompt(request):
    if request.method != 'POST':
        return redirect('/admin-config/ai/')
    prompt = request.POST.get('prompt', '')
    with connection.cursor() as cursor:
        _upsert_setting(cursor, 'system_prompt', prompt)
    return redirect('/admin-config/ai/?tab=prompt&success=prompt')


@csrf_exempt
@require_http_methods(["POST"])
@admin_required
def toggle_tool(request, tool_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute('UPDATE ai_tools SET enabled = NOT enabled WHERE id = %s', [tool_id])
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)})


@admin_required
def update_settings(request):
    if request.method != 'POST':
        return redirect('/admin-config/ai/')
    max_turns = request.POST.get('max_conversation_turns')
    tool_calling = request.POST.get('tool_calling_enabled')
    with connection.cursor() as cursor:
        if max_turns is not None:
            _upsert_setting(cursor, 'max_conversation_turns',
                            int(max_turns) if max_turns.isdigit() else 50)
        _upsert_setting(cursor, 'tool_calling_enabled', tool_calling == 'true')
    return redirect('/admin-config/ai/?tab=prompt&success=settings')


@admin_required
def update_text_analysis(request):
    if request.method != 'POST':
        return redirect('/admin-config/ai/?tab=text')
    with connection.cursor() as cursor:
        _upsert_setting(cursor, 'text_analysis_enabled',
                        request.POST.get('text_analysis_enabled') == 'true')
        _upsert_setting(cursor, 'text_analysis_prompt',
                        request.POST.get('text_analysis_prompt', ''))
        lang = request.POST.get('text_analysis_language', 'English').strip()
        _upsert_setting(cursor, 'text_analysis_language', lang if lang else 'English')
    return redirect('/admin-config/ai/?tab=text&success=text')


@admin_required
def update_vision_analysis(request):
    if request.method != 'POST':
        return redirect('/admin-config/ai/?tab=vision')
    with connection.cursor() as cursor:
        _upsert_setting(cursor, 'vision_analysis_enabled',
                        request.POST.get('vision_analysis_enabled') == 'true')
        _upsert_setting(cursor, 'vision_analysis_prompt',
                        request.POST.get('vision_analysis_prompt', ''))
        _upsert_setting(cursor, 'baseline_comparison_enabled',
                        request.POST.get('baseline_comparison_enabled') == 'true')
        threshold = request.POST.get('baseline_diff_threshold', '0.01')
        try:
            threshold = float(threshold)
        except (ValueError, TypeError):
            threshold = 0.01
        _upsert_setting(cursor, 'baseline_diff_threshold', threshold)
    return redirect('/admin-config/ai/?tab=vision&success=vision')


@csrf_exempt
@require_http_methods(["POST"])
@admin_required
def save_feature_provider(request):
    """AJAX — save per-feature provider type + config."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    feature = body.get('feature')
    if feature not in ('text', 'vision'):
        return JsonResponse({'ok': False, 'error': 'Invalid feature'}, status=400)

    provider_type = body.get('providerType', 'default')
    provider_config = body.get('providerConfig', {})

    with connection.cursor() as cursor:
        _upsert_setting(cursor, f'{feature}_provider_type', provider_type)
        _upsert_setting(cursor, f'{feature}_provider_config', provider_config)

    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(["POST"])
@admin_required
def test_provider(request):
    """AJAX — test an AI provider connection. Returns {ok, message, durationMs}."""
    import time

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    feature = body.get('feature')  # 'text', 'vision', 'chat', or None
    provider_type = body.get('providerType')
    provider_config = body.get('providerConfig')

    start = time.time()
    try:
        if provider_type and provider_type != 'default':
            from ai.provider import _instantiate_provider
            provider = _instantiate_provider(provider_type, provider_config or {})
        else:
            from ai.provider import get_provider_for_feature
            provider = get_provider_for_feature(feature)

        if feature == 'text':
            result = provider.analyze_text('The quick brown fox jumps over the lazy dog.')
            duration_ms = int((time.time() - start) * 1000)
            issue_count = len(result.get('issues', []))
            model = result.get('model', 'unknown')
            return JsonResponse({
                'ok': True,
                'message': f'Text analysis succeeded via {model} — {issue_count} issue(s) found',
                'durationMs': duration_ms,
            })
        else:
            result = provider.health_check()
            duration_ms = int((time.time() - start) * 1000)
            if result.get('healthy'):
                return JsonResponse({
                    'ok': True,
                    'message': f'Provider "{result.get("provider", "unknown")}" is healthy',
                    'durationMs': duration_ms,
                })
            else:
                detail = result.get('details', {}).get('error', 'Unknown error')
                return JsonResponse({
                    'ok': False,
                    'error': f'Health check failed: {detail}',
                    'durationMs': duration_ms,
                })
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return JsonResponse({
            'ok': False,
            'error': str(e),
            'durationMs': duration_ms,
        })


# ═══════════════════════════════════════════════════════════════════
#  General Settings
# ═══════════════════════════════════════════════════════════════════

def _load_json_val(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


@admin_required
def general_settings(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT key, value FROM ai_settings WHERE key IN ('archiving_enabled', 'archiving_retention_days')")
        rows = {r[0]: r[1] for r in cursor.fetchall()}

    return render(request, 'admin_config/general_settings.html', {
        'archiving_enabled': _load_json_val(rows.get('archiving_enabled', False)),
        'retention_days': _load_json_val(rows.get('archiving_retention_days', 30)),
        'success': request.GET.get('success'),
    })


@admin_required
def update_general_settings(request):
    if request.method != 'POST':
        return redirect('/admin-config/general/')
    archiving_enabled = request.POST.get('archiving_enabled') == 'true'
    retention_days = request.POST.get('archiving_retention_days', '30')
    try:
        retention_days = max(1, int(retention_days))
    except (ValueError, TypeError):
        retention_days = 30
    with connection.cursor() as cursor:
        _upsert_setting(cursor, 'archiving_enabled', archiving_enabled)
        _upsert_setting(cursor, 'archiving_retention_days', retention_days)
    return redirect('/admin-config/general/?success=1')


# ═══════════════════════════════════════════════════════════════════
#  Test Archives
# ═══════════════════════════════════════════════════════════════════

@admin_required
def test_archives(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT value FROM ai_settings WHERE key = 'archiving_enabled'")
        row = cursor.fetchone()
        archiving_enabled = _load_json_val(row[0]) if row else False

        cursor.execute("""
            SELECT a.id, a.script_path, a.description, a.test_type, a.browser, a.viewport,
                   a.archived_at, a.expires_at, a.original_id,
                   e.name AS environment_name, u.username AS archived_by_name
            FROM test_script_archives a
            LEFT JOIN environments e ON a.environment_id = e.id
            LEFT JOIN auth_user u ON a.archived_by_id = u.id
            ORDER BY a.archived_at DESC
        """)
        cols = [c[0] for c in cursor.description]
        archives = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return render(request, 'admin_config/test_archives.html', {
        'archives': archives,
        'archiving_enabled': archiving_enabled,
        'success': request.GET.get('success'),
    })


@csrf_exempt
@require_http_methods(["POST"])
@admin_required
def restore_archive(request):
    """Restore an archived test back to the active test_scripts table."""
    try:
        data = json.loads(request.body)
        archive_id = data.get('id')
        if not archive_id:
            return JsonResponse({'error': 'id required'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT script_path, description, environment_id, item_id, assessment_id,
                       test_type, ai_config, tags, category, test_summary, browser, viewport,
                       file_content, original_created_at
                FROM test_script_archives WHERE id = %s
            """, [archive_id])
            row = cursor.fetchone()
            if not row:
                return JsonResponse({'error': 'Archive not found'}, status=404)

            (script_path, description, environment_id, item_id, assessment_id,
             test_type, ai_config, tags, category, test_summary, browser, viewport,
             file_content, original_created_at) = row

            # Ensure ai_config / tags are JSON strings
            if isinstance(ai_config, dict):
                ai_config = json.dumps(ai_config)
            elif not isinstance(ai_config, str):
                ai_config = '{}'
            if isinstance(tags, list):
                tags = json.dumps(tags)
            elif not isinstance(tags, str):
                tags = '[]'

            # Re-insert into test_scripts
            cursor.execute("""
                INSERT INTO test_scripts
                    (script_path, description, environment_id, item_id, assessment_id,
                     test_type, ai_config, tags, category, test_summary, browser, viewport,
                     created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, COALESCE(%s, 'functional'),
                        COALESCE(%s::jsonb, '{}'::jsonb), COALESCE(%s::jsonb, '[]'::jsonb),
                        %s, %s, %s, %s, COALESCE(%s, now()), now())
                ON CONFLICT (script_path) DO UPDATE SET
                    description = EXCLUDED.description,
                    environment_id = EXCLUDED.environment_id,
                    updated_at = now()
            """, [script_path, description, str(environment_id) if environment_id else None,
                  item_id, str(assessment_id) if assessment_id else None,
                  test_type, ai_config, tags, category, test_summary,
                  browser or 'chromium', viewport or '1920x1080', original_created_at])

            # Restore file to disk
            if file_content:
                tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
                full_path = tests_dir / script_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(file_content, encoding='utf-8')

            # Remove archive record
            cursor.execute("DELETE FROM test_script_archives WHERE id = %s", [archive_id])

        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@admin_required
def delete_archive(request):
    """Permanently delete an archived test and its associated run history."""
    try:
        data = json.loads(request.body)
        archive_id = data.get('id')
        if not archive_id:
            return JsonResponse({'error': 'id required'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("SELECT script_path FROM test_script_archives WHERE id = %s", [archive_id])
            row = cursor.fetchone()
            if not row:
                return JsonResponse({'error': 'Archive not found'}, status=404)
            script_path = row[0]

            # Delete associated run data
            _cascade_delete_run_data(cursor, script_path)

            # Delete baselines
            cursor.execute("DELETE FROM test_script_baselines WHERE script_path = %s", [script_path])

            # Delete archive record
            cursor.execute("DELETE FROM test_script_archives WHERE id = %s", [archive_id])

        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@admin_required
def run_cleanup(request):
    """Manually run cleanup of expired archives."""
    try:
        deleted = _cleanup_expired_archives()
        return JsonResponse({'ok': True, 'deleted': deleted})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _cascade_delete_run_data(cursor, script_path):
    """Delete all run-related data for a given script_path."""
    # Find all run_ids that have scripts matching this path
    cursor.execute("""
        SELECT DISTINCT run_id FROM test_run_scripts WHERE script_path = %s
    """, [script_path])
    run_ids = [r[0] for r in cursor.fetchall()]

    if run_ids:
        run_id_list = [str(rid) for rid in run_ids]
        # Nullify baseline FK references before deleting runs
        cursor.execute("UPDATE test_script_baselines SET source_run_id = NULL WHERE source_run_id = ANY(%s::uuid[])", [run_id_list])
        # Delete run_screenshots for these runs
        cursor.execute("DELETE FROM run_screenshots WHERE run_id = ANY(%s::uuid[])", [run_id_list])
        # Delete test_results + ai_analyses + reviews cascade via run
        cursor.execute("""
            DELETE FROM reviews WHERE analysis_id IN (
                SELECT id FROM ai_analyses WHERE run_id = ANY(%s::uuid[])
            )
        """, [run_id_list])
        cursor.execute("DELETE FROM ai_analyses WHERE run_id = ANY(%s::uuid[])", [run_id_list])
        cursor.execute("DELETE FROM test_results WHERE run_id = ANY(%s::uuid[])", [run_id_list])

    # Delete test_run_scripts for this script
    cursor.execute("DELETE FROM test_run_scripts WHERE script_path = %s", [script_path])

    if run_ids:
        # Delete runs that no longer have any scripts
        run_id_list = [str(rid) for rid in run_ids]
        cursor.execute("""
            DELETE FROM test_runs WHERE id = ANY(%s::uuid[])
            AND NOT EXISTS (SELECT 1 FROM test_run_scripts WHERE run_id = test_runs.id)
        """, [run_id_list])


def _cleanup_expired_archives():
    """Delete all archives past their expires_at date. Returns count deleted."""
    deleted = 0
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, script_path FROM test_script_archives WHERE expires_at < now()
        """)
        expired = cursor.fetchall()

        for archive_id, script_path in expired:
            _cascade_delete_run_data(cursor, script_path)
            cursor.execute("DELETE FROM test_script_baselines WHERE script_path = %s", [script_path])
            cursor.execute("DELETE FROM test_script_archives WHERE id = %s", [archive_id])
            deleted += 1

    return deleted


# ═══════════════════════════════════════════════════════════════════
#  API Client Management
# ═══════════════════════════════════════════════════════════════════

@admin_required
def api_clients(request):
    """List all API clients."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.id, c.name, c.description, c.key_prefix, c.is_active,
                   c.rate_limit, c.last_used_at, c.created_at, c.expires_at,
                   e.name AS environment_name
            FROM api_clients c
            LEFT JOIN environments e ON c.environment_id = e.id
            ORDER BY c.name
        """)
        cols = [c[0] for c in cursor.description]
        clients = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return render(request, 'admin_config/api_clients.html', {
        'clients': clients,
        'success': request.GET.get('success'),
    })


@admin_required
def api_client_create(request):
    """GET: show create form. POST: create client and redirect with key in session."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT id, name FROM environments ORDER BY name')
        environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]

    if request.method == 'GET':
        return render(request, 'admin_config/api_client_edit.html', {
            'client': None,
            'environments': environments,
        })

    # POST
    name = (request.POST.get('name') or '').strip()
    if not name:
        return render(request, 'admin_config/api_client_edit.html', {
            'client': None,
            'environments': environments,
            'form_error': 'Name is required.',
        })

    environment_id = request.POST.get('environment_id')
    if not environment_id:
        return render(request, 'admin_config/api_client_edit.html', {
            'client': None,
            'environments': environments,
            'form_error': 'Environment is required.',
        })

    description = request.POST.get('description', '').strip() or None
    rate_limit = 60
    try:
        rate_limit = max(1, min(1000, int(request.POST.get('rate_limit', 60))))
    except (ValueError, TypeError):
        pass
    expires_at = request.POST.get('expires_at') or None

    from api.auth import generate_api_key, hash_api_key
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12]

    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO api_clients
                   (id, name, description, key_prefix, key_hash, environment_id,
                    is_active, rate_limit, created_by_id, expires_at, created_at)
               VALUES (gen_random_uuid(), %s, %s, %s, %s, %s::uuid,
                       true, %s, %s, %s, now())
               RETURNING id""",
            [name, description, key_prefix, key_hash, environment_id,
             rate_limit, request.user.id, expires_at or None],
        )
        client_id = cursor.fetchone()[0]

    # Store raw key in session (shown once on the edit page)
    request.session['new_api_key'] = raw_key
    request.session['new_api_key_client_id'] = str(client_id)

    return redirect(f'/admin-config/api/{client_id}/edit/?created=1')


@admin_required
def api_client_edit(request, client_id):
    """Display edit form for an API client."""
    # Check for one-time key display (create or regenerate)
    new_key = None
    session_key_client = request.session.get('new_api_key_client_id')
    if session_key_client == str(client_id):
        if request.GET.get('created') or request.GET.get('regenerated'):
            new_key = request.session.pop('new_api_key', None)
            request.session.pop('new_api_key_client_id', None)

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.id, c.name, c.description, c.key_prefix, c.is_active,
                   c.rate_limit, c.environment_id, c.created_at, c.last_used_at,
                   c.expires_at, u.username AS created_by_name
            FROM api_clients c
            LEFT JOIN auth_user u ON c.created_by_id = u.id
            WHERE c.id = %s
        """, [str(client_id)])
        cols = [col[0] for col in cursor.description]
        row = cursor.fetchone()

    if not row:
        return redirect('/admin-config/api/')

    client = dict(zip(cols, row))
    # Format expires_at for datetime-local input
    client['expires_at_input'] = ''
    if client['expires_at']:
        client['expires_at_input'] = client['expires_at'].strftime('%Y-%m-%dT%H:%M')
    # Convert environment_id to string for template comparison
    client['environment_id'] = str(client['environment_id']) if client['environment_id'] else ''

    with connection.cursor() as cursor:
        cursor.execute('SELECT id, name FROM environments ORDER BY name')
        environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]

    # Recent API activity
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT method, path, status_code, ip_address, created_at
            FROM api_client_logs
            WHERE client_id = %s
            ORDER BY created_at DESC
            LIMIT 15
        """, [str(client_id)])
        cols = [c[0] for c in cursor.description]
        recent_logs = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return render(request, 'admin_config/api_client_edit.html', {
        'client': client,
        'new_key': new_key,
        'environments': environments,
        'recent_logs': recent_logs,
        'success': request.GET.get('success'),
        'created': request.GET.get('created'),
    })


@admin_required
def api_client_update(request, client_id):
    """POST: update client settings."""
    if request.method != 'POST':
        return redirect(f'/admin-config/api/{client_id}/edit/')

    name = (request.POST.get('name') or '').strip()
    description = request.POST.get('description', '').strip() or None
    environment_id = request.POST.get('environment_id')
    is_active = request.POST.get('is_active') == 'true'
    rate_limit = 60
    try:
        rate_limit = max(1, min(1000, int(request.POST.get('rate_limit', 60))))
    except (ValueError, TypeError):
        pass
    expires_at = request.POST.get('expires_at') or None

    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE api_clients
               SET name = %s, description = %s, environment_id = %s::uuid,
                   is_active = %s, rate_limit = %s, expires_at = %s
               WHERE id = %s""",
            [name, description, environment_id, is_active, rate_limit,
             expires_at or None, str(client_id)],
        )

    return redirect(f'/admin-config/api/{client_id}/edit/?success=updated')


@admin_required
def api_client_regenerate(request, client_id):
    """POST: generate a new key for this client (invalidates the old one)."""
    if request.method != 'POST':
        return redirect(f'/admin-config/api/{client_id}/edit/')

    from api.auth import generate_api_key, hash_api_key
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12]

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE api_clients SET key_prefix = %s, key_hash = %s WHERE id = %s",
            [key_prefix, key_hash, str(client_id)],
        )

    request.session['new_api_key'] = raw_key
    request.session['new_api_key_client_id'] = str(client_id)

    return redirect(f'/admin-config/api/{client_id}/edit/?regenerated=1')


@admin_required
def api_client_delete(request, client_id):
    """POST: permanently delete a client and its logs."""
    if request.method != 'POST':
        return redirect('/admin-config/api/')

    with connection.cursor() as cursor:
        cursor.execute('DELETE FROM api_client_logs WHERE client_id = %s', [str(client_id)])
        cursor.execute('DELETE FROM api_clients WHERE id = %s', [str(client_id)])

    return redirect('/admin-config/api/?success=deleted')
