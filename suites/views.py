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


def _get_scripts_for_environment(env_id):
    """Query DB for test scripts belonging to an environment."""
    if not env_id:
        return []
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ts.script_path, ts.description, ts.category, ts.test_type
            FROM test_scripts ts
            WHERE ts.environment_id = %s::uuid
            ORDER BY ts.script_path
        """, [str(env_id)])
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
        'suite_scripts': [],
        'available_scripts': [],
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

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT script_path FROM test_suite_scripts WHERE suite_id = %s ORDER BY added_at',
            [suite_id]
        )
        suite_scripts = [row[0] for row in cursor.fetchall()]

    from core.models import Environment
    env_ids = get_user_env_ids(request.user)
    if env_ids is None:
        environments = list(Environment.objects.values('id', 'name').order_by('name'))
    else:
        environments = list(Environment.objects.filter(id__in=env_ids).values('id', 'name').order_by('name'))

    # Load scripts for the suite's environment from DB
    available_scripts = _get_scripts_for_environment(suite.get('environment_id'))

    return render(request, 'suites/detail.html', {
        'suite': suite,
        'suite_scripts': suite_scripts,
        'available_scripts': available_scripts,
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
        browser_profiles = data.get('browser_profiles') or ['chrome-desktop']
        schedule = data.get('schedule') if data.get('schedule', {}).get('enabled') else None
        environment_id = data.get('environment_id') or None

        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_suites (name, description, created_by, schedule, browser_profiles, environment_id)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                [name, description, request.user.username,
                 json.dumps(schedule) if schedule else None,
                 browser_profiles, environment_id]
            )
            suite_id = cursor.fetchone()[0]
            for sp in scripts:
                cursor.execute(
                    'INSERT INTO test_suite_scripts (suite_id, script_path) VALUES (%s, %s) ON CONFLICT DO NOTHING',
                    [str(suite_id), sp]
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
        browser_profiles = data.get('browser_profiles') or ['chrome-desktop']
        schedule = data.get('schedule') if data.get('schedule', {}).get('enabled') else None
        environment_id = data.get('environment_id') or None

        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE test_suites SET name=%s, description=%s, schedule=%s,
                   browser_profiles=%s, environment_id=%s, updated_at=now()
                   WHERE id=%s""",
                [name, description, json.dumps(schedule) if schedule else None,
                 browser_profiles, environment_id, suite_id]
            )
            cursor.execute('DELETE FROM test_suite_scripts WHERE suite_id = %s', [suite_id])
            for sp in scripts:
                cursor.execute(
                    'INSERT INTO test_suite_scripts (suite_id, script_path) VALUES (%s, %s)',
                    [suite_id, sp]
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
                'SELECT script_path FROM test_suite_scripts WHERE suite_id = %s',
                [suite_id]
            )
            script_paths = [row[0] for row in cursor.fetchall()]

        if not script_paths:
            return JsonResponse({'error': 'Suite has no scripts'}, status=400)

        # Create run
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_runs (status, trigger_type, suite_id, environment_id, config, notes)
                   VALUES ('running', 'dashboard', %s, %s, %s, %s) RETURNING id""",
                [suite_id, suite.get('environment_id'),
                 json.dumps({'browser_profiles': suite.get('browser_profiles', [])}),
                 f"Suite: {suite['name']}"]
            )
            run_id = cursor.fetchone()[0]
            for sp in script_paths:
                cursor.execute(
                    "INSERT INTO test_run_scripts (run_id, script_path, status) VALUES (%s, %s, 'queued')",
                    [str(run_id), sp]
                )

        # Queue task
        from django_q.tasks import async_task
        async_task('tasks.run_tasks.execute_suite_run', str(run_id))

        return JsonResponse({'runId': str(run_id), 'status': 'running', 'scripts': len(script_paths)})
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
            # Look up environment_id from test_scripts, with POST body fallback
            cursor.execute('SELECT environment_id FROM test_scripts WHERE script_path = %s', [script_path])
            env_row = cursor.fetchone()
            environment_id = env_row[0] if env_row else None
            if not environment_id and data.get('environment_id'):
                environment_id = data['environment_id']

            # Build config with optional headed and scheduled_at flags
            config = {}
            if data.get('headed'):
                config['headed'] = True
            scheduled_at = data.get('scheduled_at')
            if scheduled_at:
                config['scheduled_at'] = scheduled_at

            run_status = 'scheduled' if scheduled_at else 'running'

            cursor.execute(
                """INSERT INTO test_runs (id, status, trigger_type, environment_id, config, notes, started_at)
                   VALUES (gen_random_uuid(), %s, 'manual', %s, %s, %s, now()) RETURNING id""",
                [run_status, str(environment_id) if environment_id else None,
                 json.dumps(config), f'Ad-hoc: {script_path}']
            )
            run_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO test_run_scripts (id, run_id, script_path, status) VALUES (gen_random_uuid(), %s, %s, 'queued')",
                [str(run_id), script_path]
            )

        # Only queue for immediate execution if not scheduled
        if not scheduled_at:
            if data.get('headed'):
                # Headed mode: run synchronously via thread so the browser opens
                # on this machine (qcluster worker has no display)
                import threading
                def _run_headed():
                    try:
                        from tasks.run_tasks import execute_single_script
                        execute_single_script(str(run_id), script_path)
                    except Exception as e:
                        print(f'[run_script] headed run error: {e}')
                threading.Thread(target=_run_headed, daemon=True).start()
            else:
                from django_q.tasks import async_task
                async_task('tasks.run_tasks.execute_single_script', str(run_id), script_path)

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
    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size}, default=str)


@login_required(login_url='/login/')
def api_scripts_by_environment(request):
    """Return test scripts for a given environment (with RBAC)."""
    env_id = request.GET.get('environment_id', '').strip()
    if not env_id:
        return JsonResponse({'scripts': []})

    # RBAC check
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None and env_id not in [str(e) for e in env_ids]:
        return JsonResponse({'scripts': []})

    scripts = _get_scripts_for_environment(env_id)
    return JsonResponse({'scripts': scripts}, default=str)
