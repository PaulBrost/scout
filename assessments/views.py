import json
import re
from pathlib import Path
from django.shortcuts import render
from django.http import JsonResponse, Http404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import connection
from core.mixins import get_user_env_ids, get_env_filter


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
    env_filter = get_env_filter(request)

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
                'search': search, 'env_filter': env_filter, 'environments': [],
                'total_pages': 1, 'start_item': 0, 'end_item': 0, 'page_range': [],
            })
        params.append(list(str(e) for e in env_ids))
        where.append('a.environment_id = ANY(%s::uuid[])')

    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(a.name) LIKE %s OR LOWER(a.id) LIKE %s)')
    if env_filter:
        params.append(env_filter)
        where.append('a.environment_id = %s::uuid')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id {where_clause}',
            params
        )
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT a.id, a.numeric_id, a.name, a.subject, a.grade, a.year, a.item_count,
                   e.name AS environment_name,
                   (SELECT COUNT(*) FROM items i WHERE i.assessment_id = a.id) AS actual_item_count
            FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        assessments = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Load environments for filter dropdown
    env_query = 'SELECT id, name FROM environments ORDER BY name'
    env_params = []
    if env_ids is not None:
        env_query = 'SELECT id, name FROM environments WHERE id = ANY(%s::uuid[]) ORDER BY name'
        env_params = [list(str(e) for e in env_ids)]
    with connection.cursor() as cursor:
        cursor.execute(env_query, env_params)
        environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = (page - 1) * page_size + 1 if total > 0 else 0
    end_item = min(page * page_size, total)

    return render(request, 'assessments/list.html', {
        'assessments': assessments, 'total': total, 'page': page, 'page_size': page_size,
        'page_size_options': [10, 25, 50, 100], 'sort': sort, 'direction': direction.lower(),
        'search': search, 'env_filter': env_filter, 'environments': environments,
        'total_pages': total_pages, 'start_item': start_item,
        'end_item': end_item, 'page_range': build_page_range(page, total_pages),
    })


@login_required(login_url='/login/')
def detail(request, numeric_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT a.*, e.name AS environment_name
               FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id
               WHERE a.numeric_id = %s""",
            [numeric_id]
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
            [assessment['id']]
        )
        cols = [c[0] for c in cursor.description]
        items = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Test scripts associated with this assessment (user-scoped)
    script_where = 'ts.assessment_id = %s'
    script_params = [assessment['id']]
    if not request.user.is_staff:
        script_where += ' AND (ts.created_by_id = %s OR ts.created_by_id IS NULL)'
        script_params.append(request.user.id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT ts.id, ts.script_path, ts.description, ts.category, ts.item_id,
                      ts.updated_at, i.title AS item_title
               FROM test_scripts ts
               LEFT JOIN items i ON ts.item_id = i.item_id
               WHERE {script_where}
               ORDER BY ts.script_path""",
            script_params
        )
        cols = [c[0] for c in cursor.description]
        scripts = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Load environments for modals
    env_ids = get_user_env_ids(request.user)
    env_query = 'SELECT id, name FROM environments ORDER BY name'
    env_params = []
    if env_ids is not None:
        env_query = 'SELECT id, name FROM environments WHERE id = ANY(%s::uuid[]) ORDER BY name'
        env_params = [list(str(e) for e in env_ids)]
    with connection.cursor() as cursor:
        cursor.execute(env_query, env_params)
        environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]

    return render(request, 'assessments/detail.html', {
        'assessment': assessment,
        'items': items,
        'scripts': scripts,
        'environments': environments,
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_delete_item(request):
    """Delete an item (removes it entirely)."""
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
def api_create_script(request):
    """Create a new test script file and DB entry, pre-associated with an assessment/environment."""
    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        assessment_id = data.get('assessment_id')
        environment_id = data.get('environment_id')

        if not name:
            return JsonResponse({'error': 'Script name is required'}, status=400)
        if not environment_id:
            return JsonResponse({'error': 'Environment is required'}, status=400)

        import uuid as _uuid
        script_path = f'{_uuid.uuid4()}.spec.js'

        # Create the file on disk with a starter template
        tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
        full_path = tests_dir / script_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        starter = (
            "const { test, expect } = require('@playwright/test');\n\n"
            f"test.describe('{name}', () => {{\n"
            "  test('should pass', async ({ page }) => {\n"
            "    // TODO: implement test\n"
            "  });\n"
            "});\n"
        )
        full_path.write_text(starter, encoding='utf-8')

        # Register in DB
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_scripts (script_path, environment_id, assessment_id, description, test_type, tags, ai_config, browser, viewport, created_by_id, created_at, updated_at)
                   VALUES (%s, %s::uuid, %s, %s, 'functional', '[]'::jsonb, '{}'::jsonb, 'chromium', '1920x1080', %s, now(), now())""",
                [script_path, environment_id, assessment_id, name, request.user.id]
            )

        return JsonResponse({'ok': True, 'path': script_path})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_update_assessment(request):
    """Update assessment details."""
    try:
        data = json.loads(request.body)
        numeric_id = data.get('numeric_id')
        if not numeric_id:
            return JsonResponse({'error': 'numeric_id required'}, status=400)

        fields = []
        params = []
        for col in ('name', 'subject', 'grade', 'year', 'intro_screens'):
            if col in data:
                fields.append(f'{col} = %s')
                params.append(data[col] if data[col] != '' else None)

        if not fields:
            return JsonResponse({'error': 'No fields to update'}, status=400)

        fields.append('updated_at = now()')
        params.append(numeric_id)

        with connection.cursor() as cursor:
            cursor.execute(
                f'UPDATE assessments SET {", ".join(fields)} WHERE numeric_id = %s',
                params
            )
            if cursor.rowcount == 0:
                return JsonResponse({'error': 'Assessment not found'}, status=404)
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_create_assessment(request):
    """Create a new assessment."""
    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        environment_id = data.get('environment_id')
        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)
        if not environment_id:
            return JsonResponse({'error': 'Environment is required'}, status=400)

        # Generate slug ID from name
        base_id = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        assessment_id = base_id

        # Ensure uniqueness
        with connection.cursor() as cursor:
            suffix = 0
            while True:
                cursor.execute('SELECT 1 FROM assessments WHERE id = %s', [assessment_id])
                if not cursor.fetchone():
                    break
                suffix += 1
                assessment_id = f'{base_id}-{suffix}'

            subject = data.get('subject') or None
            grade = data.get('grade') or None
            year = data.get('year') or None
            form_value = data.get('form_value') or None
            intro_screens = int(data.get('intro_screens', 5) or 5)
            description = data.get('description') or None

            # Get next numeric_id
            cursor.execute('SELECT COALESCE(MAX(numeric_id), 0) + 1 FROM assessments')
            numeric_id = cursor.fetchone()[0]

            cursor.execute(
                """INSERT INTO assessments (id, numeric_id, name, environment_id, subject, grade, year, form_value, intro_screens, description, created_at, updated_at)
                   VALUES (%s, %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s, now(), now())""",
                [assessment_id, numeric_id, name, environment_id, subject, grade, year, form_value, intro_screens, description]
            )
        return JsonResponse({'ok': True, 'id': assessment_id, 'numeric_id': numeric_id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_create_item(request):
    """Create a single item."""
    try:
        data = json.loads(request.body)
        item_id = (data.get('item_id') or '').strip()
        environment_id = data.get('environment_id')
        if not item_id:
            return JsonResponse({'error': 'item_id is required'}, status=400)
        if not environment_id:
            return JsonResponse({'error': 'environment_id is required'}, status=400)

        title = data.get('title') or None
        assessment_id = data.get('assessment_id') or None
        category = data.get('category') or None
        tier = data.get('tier') or None

        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO items (item_id, title, environment_id, assessment_id, category, tier, languages, metadata, created_at, updated_at)
                   VALUES (%s, %s, %s::uuid, %s, %s, %s, '[]'::jsonb, '{}'::jsonb, now(), now())
                   RETURNING numeric_id""",
                [item_id, title, environment_id, assessment_id, category, tier]
            )
            numeric_id = cursor.fetchone()[0]
        return JsonResponse({'ok': True, 'numeric_id': numeric_id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_bulk_import_items(request):
    """Bulk import/upsert items for an assessment."""
    try:
        data = json.loads(request.body)
        assessment_id = data.get('assessment_id')
        environment_id = data.get('environment_id')
        items = data.get('items', [])

        if not assessment_id:
            return JsonResponse({'error': 'assessment_id is required'}, status=400)
        if not environment_id:
            return JsonResponse({'error': 'environment_id is required'}, status=400)
        if not items:
            return JsonResponse({'error': 'items list is empty'}, status=400)

        created = 0
        updated = 0
        with connection.cursor() as cursor:
            for item in items:
                item_id = (item.get('item_id') or '').strip()
                if not item_id:
                    continue
                title = item.get('title') or None
                category = item.get('category') or None
                tier = item.get('tier') or None
                position = item.get('position')

                cursor.execute(
                    """INSERT INTO items (item_id, title, environment_id, assessment_id, category, tier, position, languages, metadata, created_at, updated_at)
                       VALUES (%s, %s, %s::uuid, %s, %s, %s, %s, '[]'::jsonb, '{}'::jsonb, now(), now())
                       ON CONFLICT (item_id) DO UPDATE SET
                         title = COALESCE(EXCLUDED.title, items.title),
                         environment_id = EXCLUDED.environment_id,
                         assessment_id = EXCLUDED.assessment_id,
                         category = COALESCE(EXCLUDED.category, items.category),
                         tier = COALESCE(EXCLUDED.tier, items.tier),
                         position = COALESCE(EXCLUDED.position, items.position),
                         updated_at = now()
                       RETURNING (xmax = 0) AS inserted""",
                    [item_id, title, environment_id, assessment_id, category, tier, position]
                )
                row = cursor.fetchone()
                if row and row[0]:
                    created += 1
                else:
                    updated += 1
        return JsonResponse({'ok': True, 'created': created, 'updated': updated})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_delete_assessment(request):
    """Delete a single assessment and its associated items."""
    try:
        data = json.loads(request.body)
        assessment_id = data.get('assessment_id')
        if not assessment_id:
            return JsonResponse({'error': 'assessment_id required'}, status=400)
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM assessments WHERE id = %s', [assessment_id])
            if cursor.rowcount == 0:
                return JsonResponse({'error': 'Assessment not found'}, status=404)
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_delete_assessments_bulk(request):
    """Delete multiple assessments by ID list."""
    try:
        data = json.loads(request.body)
        ids = data.get('ids', [])
        if not ids:
            return JsonResponse({'error': 'No IDs provided'}, status=400)
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM assessments WHERE id = ANY(%s)', [ids])
            deleted = cursor.rowcount
        return JsonResponse({'ok': True, 'deleted': deleted})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
            SELECT a.id, a.numeric_id, a.name, a.subject, a.grade, e.name AS environment_name
            FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id
            {where_clause}
            ORDER BY a.name LIMIT %s OFFSET %s
        """, params + [page_size, (page - 1) * page_size])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size})
