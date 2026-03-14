import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection
from core.mixins import get_user_env_ids


def build_page_range(page, total_pages):
    if total_pages <= 7:
        return list(range(1, total_pages + 1))
    pages = set([1, total_pages])
    for i in range(max(1, page - 2), min(total_pages + 1, page + 3)):
        pages.add(i)
    result = []
    prev = None
    for p in sorted(pages):
        if prev and p - prev > 1:
            result.append('...')
        result.append(p)
        prev = p
    return result


@login_required(login_url='/login/')
def index(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('page_size', 25))))
    sort = request.GET.get('sort', 'name')
    direction = 'DESC' if request.GET.get('dir', 'asc') == 'desc' else 'ASC'
    search = request.GET.get('search', '').strip()

    valid_sorts = {
        'name': 's.name',
        'scripts': 'script_count',
        'schedule': 's.schedule',
        'updated': 's.updated_at',
    }
    order_col = valid_sorts.get(sort, 's.name')

    where = []
    params = []

    # Environment scoping
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'suites/list.html', {
                'suites': [], 'total': 0, 'page': 1, 'page_size': page_size,
                'page_size_options': [10, 25, 50, 100],
                'sort': sort, 'direction': direction.lower(), 'search': search,
                'total_pages': 1, 'start_item': 0, 'end_item': 0, 'page_range': [],
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('s.environment_id = ANY(%s::uuid[])')

    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(s.name) LIKE %s OR LOWER(s.description) LIKE %s)')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM test_suites s {where_clause}',
            params
        )
        total = cursor.fetchone()[0]

        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT s.*,
                   (SELECT COUNT(*) FROM test_suite_scripts ss WHERE ss.suite_id = s.id) AS script_count,
                   tr.started_at AS last_run_at, tr.status AS last_run_status,
                   e.name AS environment_name
            FROM test_suites s
            LEFT JOIN environments e ON s.environment_id = e.id
            LEFT JOIN LATERAL (
                SELECT started_at, status FROM test_runs WHERE suite_id = s.id
                ORDER BY started_at DESC LIMIT 1
            ) tr ON true
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        suites = [dict(zip(cols, row)) for row in cursor.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = (page - 1) * page_size + 1 if total > 0 else 0
    end_item = min(page * page_size, total)

    return render(request, 'suites/list.html', {
        'suites': suites,
        'total': total,
        'page': page,
        'page_size': page_size,
        'page_size_options': [10, 25, 50, 100],
        'sort': sort,
        'direction': direction.lower(),
        'search': search,
        'total_pages': total_pages,
        'start_item': start_item,
        'end_item': end_item,
        'page_range': build_page_range(page, total_pages),
    })


def _get_scripts_for_environment(env_id, assessment_id=None, item_id=None):
    """Query DB for test scripts belonging to an environment, optionally filtered by assessment/item."""
    if not env_id:
        return []
    where = ['ts.environment_id = %s::uuid']
    params = [str(env_id)]
    if item_id:
        where.append('ts.item_id = %s')
        params.append(item_id)
    elif assessment_id:
        where.append('ts.assessment_id = %s')
        params.append(assessment_id)
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT ts.script_path, ts.description, ts.category, ts.test_type,
                   ts.assessment_id, ts.item_id
            FROM test_scripts ts
            WHERE {' AND '.join(where)}
            ORDER BY ts.script_path
        """, params)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


@login_required(login_url='/login/')
def suite_new(request):
    from core.models import Environment
    env_ids = get_user_env_ids(request.user)
    if env_ids is None:
        environments = list(Environment.objects.values('id', 'name').order_by('name'))
    else:
        environments = list(Environment.objects.filter(id__in=env_ids).values('id', 'name').order_by('name'))
    return render(request, 'suites/detail.html', {
        'suite': None,
        'suite_scripts_json': '[]',
        'environments': environments,
    })


@login_required(login_url='/login/')
def suite_detail(request, suite_id):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT s.*, e.name AS environment_name FROM test_suites s LEFT JOIN environments e ON s.environment_id = e.id WHERE s.id = %s',
            [suite_id]
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        raise Http404

    suite = dict(zip(cols, row))

    # Load suite script entries with browser/viewport and description from test_scripts
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ss.id, ss.script_path, ss.browser, ss.viewport,
                   ts.description, ts.test_type
            FROM test_suite_scripts ss
            LEFT JOIN test_scripts ts ON ss.script_path = ts.script_path
            WHERE ss.suite_id = %s
            ORDER BY ss.added_at
        """, [suite_id])
        cols = [c[0] for c in cursor.description]
        suite_scripts = [dict(zip(cols, row)) for row in cursor.fetchall()]

    from core.models import Environment
    env_ids = get_user_env_ids(request.user)
    if env_ids is None:
        environments = list(Environment.objects.values('id', 'name').order_by('name'))
    else:
        environments = list(Environment.objects.filter(id__in=env_ids).values('id', 'name').order_by('name'))

    return render(request, 'suites/detail.html', {
        'suite': suite,
        'suite_scripts_json': json.dumps(suite_scripts, default=str),
        'environments': environments,
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def suite_create(request):
    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)
        description = data.get('description') or None
        scripts = data.get('scripts') or []
        environment_id = data.get('environment_id') or None

        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_suites (id, name, description, created_by, browser_profiles, environment_id, created_at, updated_at)
                   VALUES (gen_random_uuid(), %s, %s, %s, '[]'::jsonb, %s, now(), now()) RETURNING id""",
                [name, description, request.user.username, environment_id]
            )
            suite_id = cursor.fetchone()[0]
            for entry in scripts:
                sp = entry.get('script_path') if isinstance(entry, dict) else entry
                browser = entry.get('browser', 'chromium') if isinstance(entry, dict) else 'chromium'
                viewport = entry.get('viewport', '1920x1080') if isinstance(entry, dict) else '1920x1080'
                cursor.execute(
                    """INSERT INTO test_suite_scripts (suite_id, script_path, browser, viewport, added_at)
                       VALUES (%s, %s, %s, %s, now())
                       ON CONFLICT (suite_id, script_path, browser, viewport) DO NOTHING""",
                    [str(suite_id), sp, browser, viewport]
                )
        return JsonResponse({'id': str(suite_id), 'redirect': f'/suites/{suite_id}/'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT", "POST"])
@login_required(login_url='/login/')
def suite_update(request, suite_id):
    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)
        description = data.get('description') or None
        scripts = data.get('scripts') or []
        environment_id = data.get('environment_id') or None

        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE test_suites SET name=%s, description=%s,
                   environment_id=%s, updated_at=now()
                   WHERE id=%s""",
                [name, description, environment_id, suite_id]
            )
            cursor.execute('DELETE FROM test_suite_scripts WHERE suite_id = %s', [suite_id])
            for entry in scripts:
                sp = entry.get('script_path') if isinstance(entry, dict) else entry
                browser = entry.get('browser', 'chromium') if isinstance(entry, dict) else 'chromium'
                viewport = entry.get('viewport', '1920x1080') if isinstance(entry, dict) else '1920x1080'
                cursor.execute(
                    """INSERT INTO test_suite_scripts (suite_id, script_path, browser, viewport, added_at)
                       VALUES (%s, %s, %s, %s, now())""",
                    [suite_id, sp, browser, viewport]
                )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
@login_required(login_url='/login/')
def suite_delete(request, suite_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM test_suites WHERE id = %s', [suite_id])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def suite_run(request, suite_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM test_suites WHERE id = %s', [suite_id])
            cols = [c[0] for c in cursor.description]
            row = cursor.fetchone()
        if not row:
            return JsonResponse({'error': 'Suite not found'}, status=404)
        suite = dict(zip(cols, row))

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT script_path, browser, viewport FROM test_suite_scripts WHERE suite_id = %s ORDER BY added_at',
                [suite_id]
            )
            suite_entries = [{'script_path': r[0], 'browser': r[1] or 'chromium', 'viewport': r[2] or '1920x1080'} for r in cursor.fetchall()]

        if not suite_entries:
            return JsonResponse({'error': 'Suite has no scripts'}, status=400)

        # Create run
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_runs (id, status, trigger_type, suite_id, environment_id, config, notes, queued_at)
                   VALUES (gen_random_uuid(), 'running', 'dashboard', %s, %s, '{}'::jsonb, %s, now()) RETURNING id""",
                [suite_id, suite.get('environment_id'), f"Suite: {suite['name']}"]
            )
            run_id = cursor.fetchone()[0]
            for entry in suite_entries:
                cursor.execute(
                    """INSERT INTO test_run_scripts (id, run_id, script_path, browser, viewport, status)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, 'queued')""",
                    [str(run_id), entry['script_path'], entry['browser'], entry['viewport']]
                )

        # Run task in background thread
        from core.utils import spawn_background_task
        def _run_suite(rid=str(run_id)):
            try:
                from tasks.run_tasks import execute_suite_run
                execute_suite_run(rid)
            except Exception as e:
                print(f'[suite_run] error: {e}')
                from django.db import connection as conn
                with conn.cursor() as cur:
                    cur.execute("UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
        spawn_background_task(_run_suite)

        return JsonResponse({'runId': str(run_id), 'status': 'running', 'scripts': len(suite_entries)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def run_script(request):
    try:
        data = json.loads(request.body)
        script_path = data.get('scriptPath')
        if not script_path:
            return JsonResponse({'error': 'scriptPath required'}, status=400)

        with connection.cursor() as cursor:
            # Look up environment_id, browser, viewport from test_scripts
            cursor.execute('SELECT environment_id, browser, viewport FROM test_scripts WHERE script_path = %s', [script_path])
            ts_row = cursor.fetchone()
            environment_id = ts_row[0] if ts_row else None
            script_browser = (ts_row[1] if ts_row else None) or 'chromium'
            script_viewport = (ts_row[2] if ts_row else None) or '1920x1080'
            if not environment_id and data.get('environment_id'):
                environment_id = data['environment_id']
            # Allow POST body to override browser/viewport for this run
            if data.get('browser'):
                script_browser = data['browser']
            if data.get('viewport'):
                script_viewport = data['viewport']

            scheduled_at = data.get('scheduled_at')
            config = {}
            if scheduled_at:
                config['scheduled_at'] = scheduled_at

            run_status = 'scheduled' if scheduled_at else 'running'

            cursor.execute(
                """INSERT INTO test_runs (id, status, trigger_type, environment_id, config, notes, queued_at)
                   VALUES (gen_random_uuid(), %s, 'manual', %s, %s, %s, now()) RETURNING id""",
                [run_status, str(environment_id) if environment_id else None,
                 json.dumps(config), f'Ad-hoc: {script_path}']
            )
            run_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO test_run_scripts (id, run_id, script_path, browser, viewport, status)
                   VALUES (gen_random_uuid(), %s, %s, %s, %s, 'queued')""",
                [str(run_id), script_path, script_browser, script_viewport]
            )

        # Only queue for immediate execution if not scheduled
        if not scheduled_at:
            from core.utils import spawn_background_task
            def _run_task(rid=str(run_id), sp=script_path):
                try:
                    from tasks.run_tasks import execute_single_script
                    execute_single_script(rid, sp)
                except Exception as e:
                    print(f'[run_script] run error: {e}')
                    from django.db import connection as conn
                    with conn.cursor() as cur:
                        cur.execute("UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
                        cur.execute("UPDATE test_run_scripts SET status='error', error_message=%s, completed_at=now() WHERE run_id=%s AND status IN ('queued','running')", [str(e), rid])
            spawn_background_task(_run_task)

        return JsonResponse({'runId': str(run_id), 'status': run_status})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def api_list(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('pageSize', 25))))
    sort = request.GET.get('sort', 'name')
    direction = 'DESC' if request.GET.get('dir', 'asc') == 'desc' else 'ASC'
    search = request.GET.get('search', '').strip()

    valid_sorts = {'name': 's.name', 'scripts': 'script_count', 'updated': 's.updated_at'}
    order_col = valid_sorts.get(sort, 's.name')

    where = []
    params = []
    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(s.name) LIKE %s OR LOWER(s.description) LIKE %s)')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM test_suites s {where_clause}', params)
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT s.*,
                   (SELECT COUNT(*) FROM test_suite_scripts ss WHERE ss.suite_id = s.id) AS script_count,
                   tr.started_at AS last_run_at, tr.status AS last_run_status
            FROM test_suites s
            LEFT JOIN LATERAL (
                SELECT started_at, status FROM test_runs WHERE suite_id = s.id ORDER BY started_at DESC LIMIT 1
            ) tr ON true
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_scripts_by_environment(request):
    """Return test scripts for a given environment (with RBAC), optionally filtered by assessment/item."""
    env_id = request.GET.get('environment_id', '').strip()
    if not env_id:
        return JsonResponse({'scripts': []})

    # RBAC check
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None and env_id not in [str(e) for e in env_ids]:
        return JsonResponse({'scripts': []})

    assessment_id = request.GET.get('assessment_id', '').strip() or None
    item_id = request.GET.get('item_id', '').strip() or None
    scripts = _get_scripts_for_environment(env_id, assessment_id=assessment_id, item_id=item_id)
    return JsonResponse({'scripts': scripts}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_assessments_by_environment(request):
    """Return assessments for a given environment."""
    env_id = request.GET.get('environment_id', '').strip()
    if not env_id:
        return JsonResponse({'assessments': []})

    env_ids = get_user_env_ids(request.user)
    if env_ids is not None and env_id not in [str(e) for e in env_ids]:
        return JsonResponse({'assessments': []})

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, name, item_count
            FROM assessments
            WHERE environment_id = %s::uuid
            ORDER BY name
        """, [str(env_id)])
        cols = [c[0] for c in cursor.description]
        assessments = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return JsonResponse({'assessments': assessments}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_items_by_assessment(request):
    """Return items for a given assessment."""
    assessment_id = request.GET.get('assessment_id', '').strip()
    if not assessment_id:
        return JsonResponse({'items': []})

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT item_id, title
            FROM items
            WHERE assessment_id = %s
            ORDER BY position, item_id
        """, [assessment_id])
        cols = [c[0] for c in cursor.description]
        items = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return JsonResponse({'items': items}, json_dumps_params={'default': str})
