import json
from django.shortcuts import render
from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
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
    sort = request.GET.get('sort', 'numeric_id')
    direction = 'DESC' if request.GET.get('dir', 'asc') == 'desc' else 'ASC'
    search = request.GET.get('search', '').strip()
    assessment_filter = request.GET.get('assessment', '')

    valid_sorts = {
        'numeric_id': 'i.numeric_id',
        'item_id': 'i.item_id',
        'title': 'i.title',
        'category': 'i.category',
        'tier': 'i.tier',
        'assessment': 'a.name',
    }
    order_col = valid_sorts.get(sort, 'i.numeric_id')

    where = []
    params = []

    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'items/list.html', {
                'items': [], 'total': 0, 'page': 1, 'page_size': page_size,
                'page_size_options': [10, 25, 50, 100], 'sort': sort, 'direction': direction.lower(),
                'search': search, 'total_pages': 1, 'start_item': 0, 'end_item': 0, 'page_range': [],
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('a.environment_id = ANY(%s::uuid[])')

    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(i.item_id) LIKE %s OR LOWER(i.title) LIKE %s)')
    if assessment_filter:
        params.append(assessment_filter)
        where.append('i.assessment_id = %s')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM items i LEFT JOIN assessments a ON i.assessment_id = a.id {where_clause}',
            params
        )
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT i.numeric_id, i.item_id, i.title, i.category, i.tier, i.languages,
                   a.id AS assessment_id, a.name AS assessment_name
            FROM items i LEFT JOIN assessments a ON i.assessment_id = a.id
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        items = [dict(zip(cols, r)) for r in cursor.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = (page - 1) * page_size + 1 if total > 0 else 0
    end_item = min(page * page_size, total)

    return render(request, 'items/list.html', {
        'items': items, 'total': total, 'page': page, 'page_size': page_size,
        'page_size_options': [10, 25, 50, 100], 'sort': sort, 'direction': direction.lower(),
        'search': search, 'assessment_filter': assessment_filter,
        'total_pages': total_pages, 'start_item': start_item, 'end_item': end_item,
        'page_range': build_page_range(page, total_pages),
    })


@login_required(login_url='/login/')
def detail(request, numeric_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT i.*, a.name AS assessment_name, a.id AS assessment_id
               FROM items i LEFT JOIN assessments a ON i.assessment_id = a.id
               WHERE i.numeric_id = %s""",
            [numeric_id]
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        raise Http404
    item = dict(zip(cols, row))

    # Test scripts for this item
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT * FROM test_scripts WHERE item_id = %s ORDER BY updated_at DESC',
            [item['item_id']]
        )
        cols = [c[0] for c in cursor.description]
        scripts = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return render(request, 'items/detail.html', {'item': item, 'scripts': scripts})


@login_required(login_url='/login/')
def api_list(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('pageSize', 25))))
    search = request.GET.get('search', '').strip()

    where = []
    params = []
    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(i.item_id) LIKE %s OR LOWER(i.title) LIKE %s)')
    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM items i {where_clause}', params)
        total = cursor.fetchone()[0]
        cursor.execute(f"""
            SELECT i.numeric_id, i.item_id, i.title, i.category, i.tier, a.name AS assessment_name
            FROM items i LEFT JOIN assessments a ON i.assessment_id = a.id
            {where_clause}
            ORDER BY i.numeric_id
            LIMIT %s OFFSET %s
        """, params + [page_size, (page - 1) * page_size])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size})
