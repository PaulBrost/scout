import json
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection
from django.utils import timezone
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
    sort = request.GET.get('sort', 'created')
    direction = 'ASC' if request.GET.get('dir', 'desc') == 'asc' else 'DESC'
    status_filter = request.GET.get('status', '')
    source_filter = request.GET.get('source', '')
    search = request.GET.get('search', '').strip()

    valid_sorts = {
        'created': 'rv.created_at',
        'status': 'rv.status',
        'type': 'rv.source_type',
    }
    order_col = valid_sorts.get(sort, 'rv.created_at')

    where = []
    params = []

    if status_filter:
        params.append(status_filter)
        where.append('rv.status = %s')
    else:
        where.append("rv.status = 'pending'")

    if source_filter:
        params.append(source_filter)
        where.append('rv.source_type = %s')

    if search:
        params.append(f'%{search.lower()}%')
        where.append("""(LOWER(COALESCE(aa.analysis_type, '')) LIKE %s
                        OR LOWER(COALESCE(rs.name, '')) LIKE %s
                        OR LOWER(COALESCE(rv.notes, '')) LIKE %s)""")
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')

    # RBAC scoping
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'reviews/list.html', {
                'reviews': [], 'total': 0, 'page': 1, 'page_size': page_size,
                'page_size_options': [10, 25, 50, 100], 'sort': sort,
                'direction': 'asc' if direction == 'ASC' else 'desc',
                'search': search, 'status_filter': status_filter,
                'source_filter': source_filter,
                'total_pages': 1, 'start_item': 0, 'end_item': 0,
                'page_range': [],
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('(tr.environment_id = ANY(%s::uuid[]) OR tr.environment_id IS NULL)')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    # Unified query: LEFT JOIN both ai_analyses and run_screenshots
    base_query = """
        FROM reviews rv
        LEFT JOIN ai_analyses aa ON rv.analysis_id = aa.id
        LEFT JOIN run_screenshots rs ON rv.screenshot_id = rs.id
        LEFT JOIN test_runs tr ON COALESCE(aa.run_id, rs.run_id) = tr.id
    """

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) {base_query} {where_clause}',
            params
        )
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT rv.id, rv.status, rv.notes, rv.reviewed_at, rv.created_at,
                   rv.source_type,
                   aa.analysis_type, aa.issues_found, aa.issues, aa.model_used,
                   aa.run_id AS ai_run_id, aa.item_id,
                   rs.id AS screenshot_id, rs.name AS screenshot_name,
                   rs.file_path AS screenshot_path, rs.flagged,
                   rs.flag_notes, rs.run_id AS ss_run_id,
                   COALESCE(aa.run_id, rs.run_id) AS run_id,
                   trs.script_path,
                   e.name AS environment_name
            {base_query}
            LEFT JOIN test_run_scripts trs ON rs.run_script_id = trs.id
            LEFT JOIN environments e ON tr.environment_id = e.id
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        reviews = [dict(zip(cols, r)) for r in cursor.fetchall()]

    for rv in reviews:
        if isinstance(rv.get('issues'), str):
            try:
                rv['issues'] = json.loads(rv['issues'])
            except Exception:
                rv['issues'] = []

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = (page - 1) * page_size + 1 if total > 0 else 0
    end_item = min(page * page_size, total)

    return render(request, 'reviews/list.html', {
        'reviews': reviews, 'total': total, 'page': page, 'page_size': page_size,
        'page_size_options': [10, 25, 50, 100], 'sort': sort,
        'direction': 'asc' if direction == 'ASC' else 'desc',
        'search': search, 'status_filter': status_filter,
        'source_filter': source_filter,
        'total_pages': total_pages, 'start_item': start_item, 'end_item': end_item,
        'page_range': build_page_range(page, total_pages),
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def review_action(request):
    try:
        data = json.loads(request.body)
        review_id = data.get('reviewId')
        action = data.get('action')  # issue, suppress
        notes = data.get('notes', '')

        if not review_id or action not in ('issue', 'suppress'):
            return JsonResponse({'error': 'Invalid request'}, status=400)

        status_map = {'issue': 'issue', 'suppress': 'suppressed'}
        new_status = status_map[action]

        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE reviews SET status=%s, notes=%s, reviewer_id=%s, reviewed_at=now()
                   WHERE id=%s""",
                [new_status, notes or None, request.user.id, review_id]
            )

            # If suppressing, create a ReviewSuppression record so future runs
            # auto-suppress the same screenshot+script+environment combo
            if action == 'suppress':
                # Get the screenshot details to build the suppression key
                cursor.execute("""
                    SELECT rs.name, trs.script_path, tr.environment_id
                    FROM reviews rv
                    LEFT JOIN run_screenshots rs ON rv.screenshot_id = rs.id
                    LEFT JOIN test_run_scripts trs ON rs.run_script_id = trs.id
                    LEFT JOIN test_runs tr ON rs.run_id = tr.id
                    WHERE rv.id = %s
                """, [review_id])
                row = cursor.fetchone()
                if row and row[0] and row[1] and row[2]:
                    screenshot_name, script_path, environment_id = row
                    cursor.execute("""
                        INSERT INTO review_suppressions
                            (id, screenshot_name, script_path, environment_id, suppressed_by_id, notes, created_at)
                        VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, now())
                        ON CONFLICT (screenshot_name, script_path, environment_id) DO NOTHING
                    """, [screenshot_name, script_path, str(environment_id),
                          request.user.id, notes or None])

        return JsonResponse({'ok': True, 'status': new_status})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def api_list(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('pageSize', 25))))
    status_filter = request.GET.get('status', 'pending')

    where = []
    params = []
    if status_filter:
        params.append(status_filter)
        where.append('rv.status = %s')
    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT COUNT(*) FROM reviews rv
                LEFT JOIN ai_analyses aa ON rv.analysis_id = aa.id
                LEFT JOIN run_screenshots rs ON rv.screenshot_id = rs.id
                {where_clause}""",
            params
        )
        total = cursor.fetchone()[0]
        cursor.execute(f"""
            SELECT rv.id, rv.status, rv.source_type, rv.created_at,
                   aa.analysis_type, aa.issues_found,
                   rs.name AS screenshot_name, rs.flagged
            FROM reviews rv
            LEFT JOIN ai_analyses aa ON rv.analysis_id = aa.id
            LEFT JOIN run_screenshots rs ON rv.screenshot_id = rs.id
            {where_clause}
            ORDER BY rv.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, (page - 1) * page_size])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def suppressions(request):
    """List all active suppressions with management UI."""
    env_ids = get_user_env_ids(request.user)

    where = []
    params = []
    if env_ids is not None:
        if not env_ids:
            return render(request, 'reviews/suppressions.html', {'suppressions': [], 'total': 0})
        params.append(tuple(str(e) for e in env_ids))
        where.append('s.environment_id = ANY(%s::uuid[])')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT s.id, s.screenshot_name, s.script_path, s.notes, s.created_at,
                   e.name AS environment_name, u.username AS suppressed_by_name
            FROM review_suppressions s
            JOIN environments e ON s.environment_id = e.id
            LEFT JOIN auth_user u ON s.suppressed_by_id = u.id
            {where_clause}
            ORDER BY s.created_at DESC
        """, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return render(request, 'reviews/suppressions.html', {
        'suppressions': rows,
        'total': len(rows),
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def delete_suppression(request, suppression_id):
    """Remove a suppression rule."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM review_suppressions WHERE id = %s', [str(suppression_id)])
            if cursor.rowcount == 0:
                return JsonResponse({'error': 'Not found'}, status=404)
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
