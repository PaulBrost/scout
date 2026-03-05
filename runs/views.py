import json
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
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
    sort = request.GET.get('sort', 'started')
    direction = 'ASC' if request.GET.get('dir', 'desc') == 'asc' else 'DESC'
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '').strip()

    valid_sorts = {
        'started': 'r.queued_at',
        'status': 'r.status',
        'trigger': 'r.trigger_type',
        'suite': 's.name',
    }
    order_col = valid_sorts.get(sort, 'r.queued_at')

    where = []
    params = []

    # RBAC scoping via environment
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'runs/list.html', {
                'runs': [], 'total': 0, 'page': 1, 'page_size': page_size,
                'page_size_options': [10, 25, 50, 100],
                'sort': sort, 'direction': 'asc' if direction == 'ASC' else 'desc',
                'search': search, 'status_filter': status_filter,
                'total_pages': 1, 'start_item': 0, 'end_item': 0, 'page_range': [],
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('(r.environment_id = ANY(%s::uuid[]) OR r.environment_id IS NULL)')

    if status_filter:
        params.append(status_filter)
        where.append('r.status = %s')
    if search:
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(r.notes) LIKE %s OR LOWER(s.name) LIKE %s)')
        params.append(f'%{search.lower()}%')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id {where_clause}',
            params
        )
        total = cursor.fetchone()[0]

        offset = (page - 1) * page_size
        row_params = params + [page_size, offset]
        cursor.execute(f"""
            SELECT r.id, r.queued_at, r.started_at, r.completed_at, r.status, r.trigger_type, r.summary, r.notes,
                   s.id AS suite_id, s.name AS suite_name,
                   (SELECT COUNT(*) FROM test_run_scripts rs WHERE rs.run_id = r.id) AS script_count
            FROM test_runs r
            LEFT JOIN test_suites s ON r.suite_id = s.id
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, row_params)
        cols = [c[0] for c in cursor.description]
        runs = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Parse summary JSON
    for run in runs:
        if isinstance(run.get('summary'), str):
            try:
                run['summary'] = json.loads(run['summary'])
            except Exception:
                run['summary'] = {}

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = (page - 1) * page_size + 1 if total > 0 else 0
    end_item = min(page * page_size, total)

    return render(request, 'runs/list.html', {
        'runs': runs,
        'total': total,
        'page': page,
        'page_size': page_size,
        'page_size_options': [10, 25, 50, 100],
        'sort': sort,
        'direction': 'asc' if direction == 'ASC' else 'desc',
        'search': search,
        'status_filter': status_filter,
        'total_pages': total_pages,
        'start_item': start_item,
        'end_item': end_item,
        'page_range': build_page_range(page, total_pages),
    })


@login_required(login_url='/login/')
def detail(request, run_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT r.*, s.name AS suite_name, s.id AS suite_id
               FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id
               WHERE r.id = %s""",
            [run_id]
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        from django.http import Http404
        raise Http404
    run = dict(zip(cols, row))

    # Parse summary
    if isinstance(run.get('summary'), str):
        try:
            run['summary'] = json.loads(run['summary'])
        except Exception:
            run['summary'] = {}

    # Script results
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT * FROM test_run_scripts WHERE run_id = %s ORDER BY completed_at DESC NULLS LAST, script_path',
            [run_id]
        )
        cols = [c[0] for c in cursor.description]
        script_results = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return render(request, 'runs/detail.html', {
        'run': run,
        'script_results': script_results,
    })


@login_required(login_url='/login/')
def script_detail(request, run_id, script_id):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT * FROM test_run_scripts WHERE run_id = %s AND id = %s',
            [run_id, script_id]
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse(dict(zip(cols, row)), json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_run_status(request, run_id):
    """Lightweight JSON endpoint for polling run status + script results."""
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT status, summary, queued_at, started_at, completed_at FROM test_runs WHERE id = %s',
            [run_id]
        )
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'error': 'Not found'}, status=404)

    run_status = row[0]
    summary = row[1]
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except Exception:
            summary = {}

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT id, script_path, status, duration_ms, error_message,
                      execution_log IS NOT NULL AS has_log,
                      started_at, completed_at
               FROM test_run_scripts WHERE run_id = %s
               ORDER BY completed_at DESC NULLS LAST, script_path""",
            [run_id]
        )
        cols = [c[0] for c in cursor.description]
        scripts = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return JsonResponse({
        'status': run_status,
        'summary': summary,
        'queued_at': row[2],
        'started_at': row[3],
        'completed_at': row[4],
        'scripts': scripts,
    }, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_list(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('pageSize', 25))))
    sort = request.GET.get('sort', 'started')
    direction = 'ASC' if request.GET.get('dir', 'desc') == 'asc' else 'DESC'
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '').strip()

    valid_sorts = {'started': 'r.queued_at', 'status': 'r.status', 'trigger': 'r.trigger_type', 'suite': 's.name'}
    order_col = valid_sorts.get(sort, 'r.queued_at')

    where = []
    params = []

    # RBAC scoping via environment
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return JsonResponse({'rows': [], 'total': 0, 'page': page, 'pageSize': page_size})
        params.append(tuple(str(e) for e in env_ids))
        where.append('(r.environment_id = ANY(%s::uuid[]) OR r.environment_id IS NULL)')

    if status_filter:
        params.append(status_filter)
        where.append('r.status = %s')
    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(r.notes) LIKE %s OR LOWER(s.name) LIKE %s)')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id {where_clause}',
            params
        )
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT r.id, r.queued_at, r.started_at, r.completed_at, r.status, r.trigger_type, r.summary,
                   s.name AS suite_name,
                   (SELECT COUNT(*) FROM test_run_scripts rs WHERE rs.run_id = r.id) AS script_count
            FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size}, default=str)


@login_required(login_url='/login/')
def api_latest(request):
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM test_runs ORDER BY queued_at DESC NULLS LAST LIMIT 1')
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'run': None})
    run = dict(zip(cols, row))
    if isinstance(run.get('summary'), str):
        try:
            run['summary'] = json.loads(run['summary'])
        except Exception:
            pass
    return JsonResponse({'run': run}, default=str)
