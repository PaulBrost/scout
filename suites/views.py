import json
import os
from pathlib import Path
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
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


# Script file cache
_script_cache = None
_script_cache_time = 0
CACHE_TTL = 30


def get_test_scripts():
    """Scan PLAYWRIGHT_TESTS_DIR for .spec.js files."""
    import time
    global _script_cache, _script_cache_time
    now = time.time()
    if _script_cache is not None and now - _script_cache_time < CACHE_TTL:
        return _script_cache

    tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
    scripts = []

    def scan(directory, prefix=''):
        if not directory.exists():
            return
        for entry in sorted(directory.iterdir()):
            if entry.is_dir():
                scan(entry, f"{prefix}{entry.name}/" if prefix else f"{entry.name}/")
            elif entry.name.endswith('.spec.js'):
                rel_path = f"{prefix}{entry.name}"
                try:
                    content = entry.read_text(encoding='utf-8', errors='replace')
                except Exception:
                    content = ''
                test_count = content.count('test(')
                script_type = 'feature'
                type_label = 'Feature'
                if 'visual-regression' in rel_path or '@visual' in content:
                    script_type = 'visual'
                    type_label = 'Visual Regression'
                elif 'content-validation' in rel_path or '@content' in content:
                    script_type = 'content'
                    type_label = 'Content Validation'
                import re
                desc_match = re.search(r"test\.describe\s*\(\s*['\"`]([^'\"`]+)", content)
                name = desc_match.group(1) if desc_match else entry.name.replace('.spec.js', '')
                scripts.append({
                    'name': name,
                    'type': script_type,
                    'typeLabel': type_label,
                    'testCount': test_count,
                    'relativePath': rel_path,
                })

    scan(tests_dir)
    _script_cache = scripts
    _script_cache_time = now
    return scripts


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


@login_required(login_url='/login/')
def suite_new(request):
    from core.models import Environment
    environments = list(Environment.objects.values('id', 'name').order_by('name'))
    return render(request, 'suites/detail.html', {
        'suite': None,
        'suite_scripts': [],
        'available_scripts': get_test_scripts(),
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
    environments = list(Environment.objects.values('id', 'name').order_by('name'))

    return render(request, 'suites/detail.html', {
        'suite': suite,
        'suite_scripts': suite_scripts,
        'available_scripts': get_test_scripts(),
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
                """INSERT INTO test_runs (status, trigger_type, suite_id, config, notes)
                   VALUES ('running', 'dashboard', %s, %s, %s) RETURNING id""",
                [suite_id, json.dumps({'browser_profiles': suite.get('browser_profiles', [])}),
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
            cursor.execute(
                """INSERT INTO test_runs (status, trigger_type, config, notes)
                   VALUES ('running', 'manual', '{}', %s) RETURNING id""",
                [f'Ad-hoc: {script_path}']
            )
            run_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO test_run_scripts (run_id, script_path, status) VALUES (%s, %s, 'queued')",
                [str(run_id), script_path]
            )

        from django_q.tasks import async_task
        async_task('tasks.run_tasks.execute_single_script', str(run_id), script_path)

        return JsonResponse({'runId': str(run_id), 'status': 'running'})
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
