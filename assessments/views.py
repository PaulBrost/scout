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
    sort = request.GET.get('sort', 'name')
    direction = 'DESC' if request.GET.get('dir', 'asc') == 'desc' else 'ASC'
    search = request.GET.get('search', '').strip()

    valid_sorts = {'name': 'a.name', 'subject': 'a.subject', 'grade': 'a.grade', 'environment': 'e.name'}
    order_col = valid_sorts.get(sort, 'a.name')

    where = []
    params = []

    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'assessments/list.html', {
                'assessments': [], 'total': 0, 'page': 1, 'page_size': page_size,
                'page_size_options': [10, 25, 50, 100], 'sort': sort, 'direction': direction.lower(),
                'search': search, 'total_pages': 1, 'start_item': 0, 'end_item': 0, 'page_range': [],
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('a.environment_id = ANY(%s::uuid[])')

    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(a.name) LIKE %s OR LOWER(a.id) LIKE %s)')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id {where_clause}',
            params
        )
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT a.id, a.name, a.subject, a.grade, a.year, a.item_count,
                   e.name AS environment_name,
                   (SELECT COUNT(*) FROM items i WHERE i.assessment_id = a.id) AS actual_item_count
            FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        assessments = [dict(zip(cols, r)) for r in cursor.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = (page - 1) * page_size + 1 if total > 0 else 0
    end_item = min(page * page_size, total)

    return render(request, 'assessments/list.html', {
        'assessments': assessments, 'total': total, 'page': page, 'page_size': page_size,
        'page_size_options': [10, 25, 50, 100], 'sort': sort, 'direction': direction.lower(),
        'search': search, 'total_pages': total_pages, 'start_item': start_item,
        'end_item': end_item, 'page_range': build_page_range(page, total_pages),
    })


@login_required(login_url='/login/')
def detail(request, assessment_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT a.*, e.name AS environment_name
               FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id
               WHERE a.id = %s""",
            [assessment_id]
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        raise Http404
    assessment = dict(zip(cols, row))

    # Items in this assessment
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT numeric_id, item_id, title, category, tier FROM items WHERE assessment_id = %s ORDER BY numeric_id',
            [assessment_id]
        )
        cols = [c[0] for c in cursor.description]
        items = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return render(request, 'assessments/detail.html', {'assessment': assessment, 'items': items})


@login_required(login_url='/login/')
def api_list(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('pageSize', 25))))
    search = request.GET.get('search', '').strip()

    where = []
    params = []
    if search:
        params.append(f'%{search.lower()}%')
        where.append('LOWER(a.name) LIKE %s')
    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM assessments a {where_clause}', params)
        total = cursor.fetchone()[0]
        cursor.execute(f"""
            SELECT a.id, a.name, a.subject, a.grade, e.name AS environment_name
            FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id
            {where_clause}
            ORDER BY a.name LIMIT %s OFFSET %s
        """, params + [page_size, (page - 1) * page_size])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size})
