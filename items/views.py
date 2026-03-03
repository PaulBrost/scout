import json
from pathlib import Path
from django.shortcuts import render
from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
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
        'environment': 'e.name',
    }
    order_col = valid_sorts.get(sort, 'i.numeric_id')

    where = []
    params = []

    # RBAC scoping - now directly on items.environment_id
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'items/list.html', {
                'items': [], 'total': 0, 'page': 1, 'page_size': page_size,
                'page_size_options': [10, 25, 50, 100], 'sort': sort, 'direction': direction.lower(),
                'search': search, 'total_pages': 1, 'start_item': 0, 'end_item': 0, 'page_range': [],
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('i.environment_id = ANY(%s::uuid[])')

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
            f"""SELECT COUNT(*) FROM items i
                LEFT JOIN assessments a ON i.assessment_id = a.id
                LEFT JOIN environments e ON i.environment_id = e.id
                {where_clause}""",
            params
        )
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT i.numeric_id, i.item_id, i.title, i.category, i.tier, i.languages,
                   a.id AS assessment_id, a.numeric_id AS assessment_numeric_id,
                   a.name AS assessment_name,
                   e.name AS environment_name, i.environment_id
            FROM items i
            LEFT JOIN assessments a ON i.assessment_id = a.id
            LEFT JOIN environments e ON i.environment_id = e.id
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
            """SELECT i.*, a.name AS assessment_name, a.id AS assessment_id,
                      a.numeric_id AS assessment_numeric_id,
                      e.name AS environment_name
               FROM items i
               LEFT JOIN assessments a ON i.assessment_id = a.id
               LEFT JOIN environments e ON i.environment_id = e.id
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

    # RBAC scoping
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return JsonResponse({'rows': [], 'total': 0, 'page': page, 'pageSize': page_size})
        params.append(tuple(str(e) for e in env_ids))
        where.append('i.environment_id = ANY(%s::uuid[])')

    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(i.item_id) LIKE %s OR LOWER(i.title) LIKE %s)')
    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM items i {where_clause}', params)
        total = cursor.fetchone()[0]
        cursor.execute(f"""
            SELECT i.numeric_id, i.item_id, i.title, i.category, i.tier,
                   a.name AS assessment_name, a.numeric_id AS assessment_numeric_id,
                   e.name AS environment_name
            FROM items i
            LEFT JOIN assessments a ON i.assessment_id = a.id
            LEFT JOIN environments e ON i.environment_id = e.id
            {where_clause}
            ORDER BY i.numeric_id
            LIMIT %s OFFSET %s
        """, params + [page_size, (page - 1) * page_size])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size})


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_update_item(request):
    """Update item details."""
    try:
        data = json.loads(request.body)
        numeric_id = data.get('numeric_id')
        if not numeric_id:
            return JsonResponse({'error': 'numeric_id required'}, status=400)

        fields = []
        params = []
        for col in ('title', 'category', 'tier'):
            if col in data:
                fields.append(f'{col} = %s')
                params.append(data[col] if data[col] != '' else None)
        if 'languages' in data:
            fields.append('languages = %s')
            params.append(json.dumps(data['languages']) if isinstance(data['languages'], list) else data['languages'])

        if not fields:
            return JsonResponse({'error': 'No fields to update'}, status=400)

        fields.append('updated_at = now()')
        params.append(numeric_id)

        with connection.cursor() as cursor:
            cursor.execute(
                f'UPDATE items SET {", ".join(fields)} WHERE numeric_id = %s',
                params
            )
            if cursor.rowcount == 0:
                return JsonResponse({'error': 'Item not found'}, status=404)
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_delete_item(request):
    """Delete a single item by numeric_id."""
    try:
        data = json.loads(request.body)
        numeric_id = data.get('numeric_id')
        if not numeric_id:
            return JsonResponse({'error': 'numeric_id required'}, status=400)
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM items WHERE numeric_id = %s', [numeric_id])
            if cursor.rowcount == 0:
                return JsonResponse({'error': 'Item not found'}, status=404)
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_delete_items_bulk(request):
    """Delete multiple items by numeric_id list."""
    try:
        data = json.loads(request.body)
        ids = data.get('ids', [])
        if not ids:
            return JsonResponse({'error': 'No IDs provided'}, status=400)
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM items WHERE numeric_id = ANY(%s::int[])', [ids])
            deleted = cursor.rowcount
        return JsonResponse({'ok': True, 'deleted': deleted})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_create_script(request):
    """Create a new test script file and DB entry, pre-associated with an item."""
    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        item_id = data.get('item_id')
        environment_id = data.get('environment_id')

        if not name:
            return JsonResponse({'error': 'Script name is required'}, status=400)
        if not environment_id:
            return JsonResponse({'error': 'Environment is required'}, status=400)

        safe_name = name.replace(' ', '-').lower()
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '-_')
        if not safe_name:
            safe_name = 'new-script'
        if not safe_name.endswith('.spec.js'):
            safe_name += '.spec.js'

        script_path = safe_name
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM test_scripts WHERE script_path = %s', [script_path])
            if cursor.fetchone():
                return JsonResponse({'error': f'Script "{script_path}" already exists'}, status=409)

        tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
        full_path = tests_dir / script_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        starter = (
            "const { test, expect } = require('@playwright/test');\n\n"
            f"test.describe('{name}', () => {{\n"
            "  test('should pass', async ({{ page }}) => {{\n"
            "    // TODO: implement test\n"
            "  }});\n"
            "}});\n"
        )
        full_path.write_text(starter, encoding='utf-8')

        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_scripts (script_path, environment_id, item_id, description, updated_at)
                   VALUES (%s, %s::uuid, %s, %s, now())""",
                [script_path, environment_id, item_id, f'Test script for {name}']
            )

        return JsonResponse({'ok': True, 'path': script_path})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
