import json
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection
from django.utils import timezone


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
    search = request.GET.get('search', '').strip()

    valid_sorts = {
        'created': 'rv.created_at',
        'status': 'rv.status',
        'type': 'aa.analysis_type',
    }
    order_col = valid_sorts.get(sort, 'rv.created_at')

    where = []
    params = []
    if status_filter:
        params.append(status_filter)
        where.append('rv.status = %s')
    else:
        where.append("rv.status = 'pending'")
    if search:
        params.append(f'%{search.lower()}%')
        where.append('LOWER(aa.analysis_type) LIKE %s')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM reviews rv JOIN ai_analyses aa ON rv.analysis_id = aa.id {where_clause}',
            params
        )
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT rv.id, rv.status, rv.notes, rv.reviewed_at, rv.created_at,
                   aa.analysis_type, aa.issues_found, aa.issues, aa.model_used,
                   aa.run_id, aa.item_id
            FROM reviews rv
            JOIN ai_analyses aa ON rv.analysis_id = aa.id
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
        action = data.get('action')  # approve, dismiss, bug_filed
        notes = data.get('notes', '')
        bug_url = data.get('bugUrl', '')

        if not review_id or action not in ('approve', 'dismiss', 'bug_filed'):
            return JsonResponse({'error': 'Invalid request'}, status=400)

        status_map = {'approve': 'approved', 'dismiss': 'dismissed', 'bug_filed': 'bug_filed'}
        new_status = status_map[action]

        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE reviews SET status=%s, notes=%s, bug_url=%s, reviewer_id=%s, reviewed_at=now()
                   WHERE id=%s""",
                [new_status, notes or None, bug_url or None, request.user.id, review_id]
            )
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
            f'SELECT COUNT(*) FROM reviews rv {where_clause}',
            params
        )
        total = cursor.fetchone()[0]
        cursor.execute(f"""
            SELECT rv.id, rv.status, rv.created_at, aa.analysis_type, aa.issues_found
            FROM reviews rv JOIN ai_analyses aa ON rv.analysis_id = aa.id
            {where_clause}
            ORDER BY rv.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, (page - 1) * page_size])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size}, default=str)
