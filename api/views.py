"""SCOUT REST API v1 — token-authenticated endpoints for scripts, suites, and runs."""
import json
import re
from pathlib import Path
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import connection
from .auth import api_auth_required


# ── Helpers ──────────────────────────────────────────────────────────

def _err(code, message, status=400):
    return JsonResponse({'error': {'code': code, 'message': message}}, status=status)


def _ok(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={'default': str})


# ═════════════════════════════════════════════════════════════════════
#  Health (no auth)
# ═════════════════════════════════════════════════════════════════════

def health(request):
    """GET /api/v1/health/"""
    return _ok({'status': 'ok'})


# ═════════════════════════════════════════════════════════════════════
#  Scripts
# ═════════════════════════════════════════════════════════════════════

@csrf_exempt
@api_auth_required
def scripts(request):
    """POST → create script, GET → list scripts."""
    if request.method == 'POST':
        return _create_script(request)
    if request.method == 'GET':
        return _list_scripts(request)
    return _err('method_not_allowed', 'Use GET or POST.', 405)


def _create_script(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _err('invalid_json', 'Request body must be valid JSON.')

    script_path = (data.get('script_path') or '').strip()
    content = data.get('content')
    if not script_path or content is None:
        return _err('validation_error', 'script_path and content are required.')

    env_id = str(request.api_client['environment_id'])

    # Path-traversal check
    tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
    full_path = (tests_dir / script_path).resolve()
    if not str(full_path).startswith(str(tests_dir.resolve())):
        return _err('validation_error', 'Invalid script_path: directory traversal not allowed.', 403)

    # Auto-correct helper import paths (same logic as test_cases/views.py)
    depth = script_path.count('/')
    correct_prefix = '../' * (depth + 1)
    content = re.sub(
        r"""require\(\s*['"](\.\./)*src/helpers/""",
        f"require('{correct_prefix}src/helpers/",
        content,
    )

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding='utf-8')

    # Optional metadata
    description = data.get('description') or None
    test_type = data.get('test_type', 'functional')
    browser = data.get('browser', 'chromium')
    viewport = data.get('viewport', '1920x1080')
    item_id = data.get('item_id') or None
    assessment_id = data.get('assessment_id') or None
    category = data.get('category') or None

    tags = data.get('tags', '')
    if isinstance(tags, str):
        tags_list = [t.strip() for t in tags.split(',') if t.strip()]
    elif isinstance(tags, list):
        tags_list = tags
    else:
        tags_list = []

    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO test_scripts
                   (script_path, description, environment_id, item_id, assessment_id,
                    test_type, browser, viewport, tags, category, ai_config,
                    created_at, updated_at)
               VALUES (%s, %s, %s::uuid, %s, %s, %s, %s, %s,
                       %s::jsonb, %s, '{}'::jsonb, now(), now())
               ON CONFLICT (script_path) DO UPDATE SET
                   description = COALESCE(EXCLUDED.description, test_scripts.description),
                   environment_id = EXCLUDED.environment_id,
                   item_id = COALESCE(EXCLUDED.item_id, test_scripts.item_id),
                   assessment_id = COALESCE(EXCLUDED.assessment_id, test_scripts.assessment_id),
                   test_type = EXCLUDED.test_type,
                   browser = EXCLUDED.browser,
                   viewport = EXCLUDED.viewport,
                   tags = EXCLUDED.tags,
                   category = COALESCE(EXCLUDED.category, test_scripts.category),
                   updated_at = now()
               RETURNING id, created_at""",
            [script_path, description, env_id, item_id, assessment_id,
             test_type, browser, viewport, json.dumps(tags_list), category],
        )
        script_id, created_at = cursor.fetchone()

    return _ok({
        'id': script_id,
        'script_path': script_path,
        'environment_id': env_id,
        'created_at': created_at,
    }, status=201)


def _list_scripts(request):
    env_id = str(request.api_client['environment_id'])
    search = request.GET.get('search', '').strip()
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(100, max(1, int(request.GET.get('page_size', 25))))

    where = ['ts.environment_id = %s::uuid']
    params = [env_id]
    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(ts.script_path) LIKE %s OR LOWER(ts.description) LIKE %s)')

    wc = 'WHERE ' + ' AND '.join(where)
    offset = (page - 1) * page_size

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM test_scripts ts {wc}', params)
        total = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT ts.id, ts.script_path, ts.description, ts.test_type,
                   ts.browser, ts.viewport, ts.item_id, ts.assessment_id,
                   ts.category, ts.tags, ts.created_at, ts.updated_at
            FROM test_scripts ts
            {wc}
            ORDER BY ts.updated_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return _ok({'scripts': rows, 'total': total, 'page': page, 'page_size': page_size})


@csrf_exempt
@api_auth_required
def script_detail(request, script_id):
    """GET /api/v1/scripts/{id}/"""
    if request.method != 'GET':
        return _err('method_not_allowed', 'Only GET is supported.', 405)

    env_id = str(request.api_client['environment_id'])
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ts.id, ts.script_path, ts.description, ts.test_type,
                   ts.browser, ts.viewport, ts.item_id, ts.assessment_id,
                   ts.category, ts.tags, ts.environment_id,
                   ts.created_at, ts.updated_at
            FROM test_scripts ts
            WHERE ts.id = %s AND ts.environment_id = %s::uuid
        """, [script_id, env_id])
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()

    if not row:
        return _err('not_found', 'Script not found or not accessible.', 404)
    return _ok(dict(zip(cols, row)))


@csrf_exempt
@api_auth_required
def script_run(request, script_id):
    """POST /api/v1/scripts/{id}/run/ — execute a single script."""
    if request.method != 'POST':
        return _err('method_not_allowed', 'Only POST is supported.', 405)

    env_id = str(request.api_client['environment_id'])

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT script_path, browser, viewport FROM test_scripts WHERE id = %s AND environment_id = %s::uuid',
            [script_id, env_id],
        )
        row = cursor.fetchone()

    if not row:
        return _err('not_found', 'Script not found or not accessible.', 404)

    script_path, default_browser, default_viewport = row

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = {}

    browser = data.get('browser', default_browser) or 'chromium'
    viewport = data.get('viewport', default_viewport) or '1920x1080'

    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO test_runs (id, status, trigger_type, environment_id, config, notes, queued_at)
               VALUES (gen_random_uuid(), 'running', 'api', %s::uuid, '{}'::jsonb, %s, now())
               RETURNING id""",
            [env_id, f'API: {script_path}'],
        )
        run_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO test_run_scripts (id, run_id, script_path, browser, viewport, status)
               VALUES (gen_random_uuid(), %s, %s, %s, %s, 'queued')""",
            [str(run_id), script_path, browser, viewport],
        )

    from core.utils import spawn_background_task

    def _run(rid=str(run_id), sp=script_path):
        try:
            from tasks.run_tasks import execute_single_script
            execute_single_script(rid, sp)
        except Exception as e:
            from django.db import connection as conn
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
                cur.execute(
                    "UPDATE test_run_scripts SET status='error', error_message=%s, completed_at=now() "
                    "WHERE run_id=%s AND status IN ('queued','running')", [str(e), rid])

    spawn_background_task(_run)

    return _ok({
        'run_id': str(run_id),
        'status': 'running',
        'status_url': f'/api/v1/runs/{run_id}/status/',
    }, status=202)


# ═════════════════════════════════════════════════════════════════════
#  Suites
# ═════════════════════════════════════════════════════════════════════

@csrf_exempt
@api_auth_required
def suites(request):
    """POST → create suite, GET → list suites."""
    if request.method == 'POST':
        return _create_suite(request)
    if request.method == 'GET':
        return _list_suites(request)
    return _err('method_not_allowed', 'Use GET or POST.', 405)


def _create_suite(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _err('invalid_json', 'Request body must be valid JSON.')

    name = (data.get('name') or '').strip()
    if not name:
        return _err('validation_error', 'name is required.')

    env_id = str(request.api_client['environment_id'])
    description = data.get('description') or None
    scripts = data.get('scripts') or []

    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO test_suites
                   (id, name, description, created_by, browser_profiles,
                    environment_id, created_at, updated_at)
               VALUES (gen_random_uuid(), %s, %s, %s, '[]'::jsonb, %s::uuid, now(), now())
               RETURNING id""",
            [name, description, f'api:{request.api_client["name"]}', env_id],
        )
        suite_id = cursor.fetchone()[0]

        for entry in scripts:
            sp = entry.get('script_path') if isinstance(entry, dict) else entry
            br = entry.get('browser', 'chromium') if isinstance(entry, dict) else 'chromium'
            vp = entry.get('viewport', '1920x1080') if isinstance(entry, dict) else '1920x1080'
            cursor.execute(
                """INSERT INTO test_suite_scripts (suite_id, script_path, browser, viewport, added_at)
                   VALUES (%s, %s, %s, %s, now())
                   ON CONFLICT (suite_id, script_path, browser, viewport) DO NOTHING""",
                [str(suite_id), sp, br, vp],
            )

    return _ok({
        'id': str(suite_id),
        'name': name,
        'environment_id': env_id,
        'scripts': len(scripts),
    }, status=201)


def _list_suites(request):
    env_id = str(request.api_client['environment_id'])
    search = request.GET.get('search', '').strip()
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(100, max(1, int(request.GET.get('page_size', 25))))

    where = ['s.environment_id = %s::uuid']
    params = [env_id]
    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(s.name) LIKE %s OR LOWER(s.description) LIKE %s)')

    wc = 'WHERE ' + ' AND '.join(where)
    offset = (page - 1) * page_size

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM test_suites s {wc}', params)
        total = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT s.id, s.name, s.description, s.environment_id,
                   s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM test_suite_scripts ss WHERE ss.suite_id = s.id) AS script_count
            FROM test_suites s
            {wc}
            ORDER BY s.name
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return _ok({'suites': rows, 'total': total, 'page': page, 'page_size': page_size})


@csrf_exempt
@api_auth_required
def suite_detail_view(request, suite_id):
    """GET → details, PUT → update, DELETE → delete."""
    if request.method == 'GET':
        return _get_suite(request, suite_id)
    if request.method == 'PUT':
        return _update_suite(request, suite_id)
    if request.method == 'DELETE':
        return _delete_suite(request, suite_id)
    return _err('method_not_allowed', 'Use GET, PUT, or DELETE.', 405)


def _get_suite(request, suite_id):
    env_id = str(request.api_client['environment_id'])

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT s.id, s.name, s.description, s.environment_id,
                   s.created_by, s.created_at, s.updated_at
            FROM test_suites s
            WHERE s.id = %s AND s.environment_id = %s::uuid
        """, [str(suite_id), env_id])
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()

    if not row:
        return _err('not_found', 'Suite not found or not accessible.', 404)

    suite = dict(zip(cols, row))

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ss.script_path, ss.browser, ss.viewport
            FROM test_suite_scripts ss
            WHERE ss.suite_id = %s
            ORDER BY ss.added_at
        """, [str(suite_id)])
        cols = [c[0] for c in cursor.description]
        suite['scripts'] = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return _ok(suite)


def _update_suite(request, suite_id):
    env_id = str(request.api_client['environment_id'])

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return _err('invalid_json', 'Request body must be valid JSON.')

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT id FROM test_suites WHERE id = %s AND environment_id = %s::uuid',
            [str(suite_id), env_id],
        )
        if not cursor.fetchone():
            return _err('not_found', 'Suite not found or not accessible.', 404)

    name = (data.get('name') or '').strip()
    if not name:
        return _err('validation_error', 'name is required.')

    description = data.get('description') or None
    scripts = data.get('scripts') or []

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE test_suites SET name=%s, description=%s, updated_at=now() WHERE id=%s",
            [name, description, str(suite_id)],
        )
        cursor.execute('DELETE FROM test_suite_scripts WHERE suite_id = %s', [str(suite_id)])
        for entry in scripts:
            sp = entry.get('script_path') if isinstance(entry, dict) else entry
            br = entry.get('browser', 'chromium') if isinstance(entry, dict) else 'chromium'
            vp = entry.get('viewport', '1920x1080') if isinstance(entry, dict) else '1920x1080'
            cursor.execute(
                """INSERT INTO test_suite_scripts (suite_id, script_path, browser, viewport, added_at)
                   VALUES (%s, %s, %s, %s, now())""",
                [str(suite_id), sp, br, vp],
            )

    return _ok({'ok': True, 'id': str(suite_id)})


def _delete_suite(request, suite_id):
    env_id = str(request.api_client['environment_id'])

    with connection.cursor() as cursor:
        cursor.execute(
            'DELETE FROM test_suites WHERE id = %s AND environment_id = %s::uuid',
            [str(suite_id), env_id],
        )
        if cursor.rowcount == 0:
            return _err('not_found', 'Suite not found or not accessible.', 404)

    return _ok({'ok': True})


@csrf_exempt
@api_auth_required
def suite_run_view(request, suite_id):
    """POST /api/v1/suites/{id}/run/ — execute all scripts in a suite."""
    if request.method != 'POST':
        return _err('method_not_allowed', 'Only POST is supported.', 405)

    env_id = str(request.api_client['environment_id'])

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT id, name FROM test_suites WHERE id = %s AND environment_id = %s::uuid',
            [str(suite_id), env_id],
        )
        row = cursor.fetchone()

    if not row:
        return _err('not_found', 'Suite not found or not accessible.', 404)
    suite_name = row[1]

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT script_path, browser, viewport FROM test_suite_scripts WHERE suite_id = %s ORDER BY added_at',
            [str(suite_id)],
        )
        entries = [
            {'script_path': r[0], 'browser': r[1] or 'chromium', 'viewport': r[2] or '1920x1080'}
            for r in cursor.fetchall()
        ]

    if not entries:
        return _err('validation_error', 'Suite has no scripts.')

    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO test_runs
                   (id, status, trigger_type, suite_id, environment_id, config, notes, queued_at)
               VALUES (gen_random_uuid(), 'running', 'api', %s, %s::uuid, '{}'::jsonb, %s, now())
               RETURNING id""",
            [str(suite_id), env_id, f'API Suite: {suite_name}'],
        )
        run_id = cursor.fetchone()[0]
        for e in entries:
            cursor.execute(
                """INSERT INTO test_run_scripts (id, run_id, script_path, browser, viewport, status)
                   VALUES (gen_random_uuid(), %s, %s, %s, %s, 'queued')""",
                [str(run_id), e['script_path'], e['browser'], e['viewport']],
            )

    from core.utils import spawn_background_task

    def _run(rid=str(run_id)):
        try:
            from tasks.run_tasks import execute_suite_run
            execute_suite_run(rid)
        except Exception as e:
            from django.db import connection as conn
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])

    spawn_background_task(_run)

    return _ok({
        'run_id': str(run_id),
        'status': 'running',
        'scripts': len(entries),
        'status_url': f'/api/v1/runs/{run_id}/status/',
    }, status=202)


# ═════════════════════════════════════════════════════════════════════
#  Runs
# ═════════════════════════════════════════════════════════════════════

@csrf_exempt
@api_auth_required
def runs(request):
    """GET /api/v1/runs/ — paginated run list."""
    if request.method != 'GET':
        return _err('method_not_allowed', 'Only GET is supported.', 405)

    env_id = str(request.api_client['environment_id'])
    status_filter = request.GET.get('status', '').strip()
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(100, max(1, int(request.GET.get('page_size', 25))))

    where = ['r.environment_id = %s::uuid']
    params = [env_id]
    if status_filter:
        params.append(status_filter)
        where.append('r.status = %s')

    wc = 'WHERE ' + ' AND '.join(where)
    offset = (page - 1) * page_size

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM test_runs r {wc}', params)
        total = cursor.fetchone()[0]

        cursor.execute(f"""
            SELECT r.id, r.status, r.trigger_type, r.suite_id, r.environment_id,
                   r.summary, r.notes, r.queued_at, r.started_at, r.completed_at,
                   s.name AS suite_name
            FROM test_runs r
            LEFT JOIN test_suites s ON r.suite_id = s.id
            {wc}
            ORDER BY r.queued_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return _ok({'runs': rows, 'total': total, 'page': page, 'page_size': page_size})


@csrf_exempt
@api_auth_required
def run_detail(request, run_id):
    """GET /api/v1/runs/{id}/ — full run details with script results."""
    if request.method != 'GET':
        return _err('method_not_allowed', 'Only GET is supported.', 405)

    env_id = str(request.api_client['environment_id'])

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT r.id, r.status, r.trigger_type, r.suite_id, r.environment_id,
                   r.summary, r.notes, r.queued_at, r.started_at, r.completed_at,
                   s.name AS suite_name
            FROM test_runs r
            LEFT JOIN test_suites s ON r.suite_id = s.id
            WHERE r.id = %s AND r.environment_id = %s::uuid
        """, [str(run_id), env_id])
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()

    if not row:
        return _err('not_found', 'Run not found or not accessible.', 404)

    run = dict(zip(cols, row))

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT rs.id, rs.script_path, rs.browser, rs.viewport, rs.status,
                   rs.duration_ms, rs.error_message, rs.started_at, rs.completed_at
            FROM test_run_scripts rs
            WHERE rs.run_id = %s
            ORDER BY rs.script_path
        """, [str(run_id)])
        cols = [c[0] for c in cursor.description]
        run['scripts'] = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return _ok(run)


@csrf_exempt
@api_auth_required
def run_status(request, run_id):
    """GET /api/v1/runs/{id}/status/ — lightweight polling endpoint."""
    if request.method != 'GET':
        return _err('method_not_allowed', 'Only GET is supported.', 405)

    env_id = str(request.api_client['environment_id'])

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT r.id, r.status, r.summary, r.started_at, r.completed_at
            FROM test_runs r
            WHERE r.id = %s AND r.environment_id = %s::uuid
        """, [str(run_id), env_id])
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()

    if not row:
        return _err('not_found', 'Run not found or not accessible.', 404)

    run = dict(zip(cols, row))

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT status, COUNT(*) AS count
            FROM test_run_scripts WHERE run_id = %s
            GROUP BY status
        """, [str(run_id)])
        run['script_statuses'] = {r[0]: r[1] for r in cursor.fetchall()}

    return _ok(run)
