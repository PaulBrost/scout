import json
from pathlib import Path
from django.shortcuts import render
from django.http import JsonResponse
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
    search = request.GET.get('search', '').strip()
    test_type_filter = request.GET.get('test_type', '')
    env_filter = request.GET.get('environment', '')

    where = []
    params = []

    # RBAC scoping
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'test_cases/list.html', {
                'scripts': [], 'total': 0, 'page': 1, 'page_size': page_size,
                'page_size_options': [10, 25, 50, 100], 'search': search,
                'test_type_filter': test_type_filter, 'env_filter': env_filter,
                'environments': [], 'test_types': [],
                'total_pages': 1, 'start_item': 0, 'end_item': 0, 'page_range': [],
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('ts.environment_id = ANY(%s::uuid[])')

    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(ts.script_path) LIKE %s OR LOWER(ts.description) LIKE %s)')
    if test_type_filter:
        params.append(test_type_filter)
        where.append('ts.test_type = %s')
    if env_filter:
        params.append(env_filter)
        where.append('ts.environment_id = %s::uuid')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM test_scripts ts {where_clause}',
            params
        )
        total = cursor.fetchone()[0]

        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT ts.id, ts.script_path, ts.description, ts.item_id, ts.assessment_id,
                   ts.test_type, ts.tags, ts.category, ts.updated_at, ts.environment_id,
                   i.title AS item_title, i.numeric_id AS item_numeric_id,
                   e.name AS environment_name
            FROM test_scripts ts
            LEFT JOIN items i ON ts.item_id = i.item_id
            LEFT JOIN environments e ON ts.environment_id = e.id
            {where_clause}
            ORDER BY ts.script_path
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        scripts = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Load environments for filter dropdown
    env_query = 'SELECT id, name FROM environments ORDER BY name'
    env_params = []
    if env_ids is not None:
        env_query = 'SELECT id, name FROM environments WHERE id = ANY(%s::uuid[]) ORDER BY name'
        env_params = [tuple(str(e) for e in env_ids)]
    with connection.cursor() as cursor:
        cursor.execute(env_query, env_params)
        environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = offset + 1 if total > 0 else 0
    end_item = min(offset + page_size, total)

    test_types = [
        ('functional', 'Functional'),
        ('visual_regression', 'Visual Regression'),
        ('ai_content', 'AI Content'),
        ('ai_visual', 'AI Visual'),
    ]

    return render(request, 'test_cases/list.html', {
        'scripts': scripts, 'total': total, 'page': page, 'page_size': page_size,
        'page_size_options': [10, 25, 50, 100], 'search': search,
        'test_type_filter': test_type_filter,
        'env_filter': env_filter, 'environments': environments,
        'test_types': test_types,
        'total_pages': total_pages, 'start_item': start_item, 'end_item': end_item,
        'page_range': build_page_range(page, total_pages),
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_save(request):
    try:
        data = json.loads(request.body)
        file_path = data.get('path')
        content = data.get('content')
        environment_id = data.get('environment_id')
        if not file_path or content is None:
            return JsonResponse({'error': 'Path and content required'}, status=400)

        tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
        full_path = (tests_dir / file_path).resolve()
        if not str(full_path).startswith(str(tests_dir)):
            return JsonResponse({'error': 'Access denied'}, status=403)

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')

        with connection.cursor() as cursor:
            if environment_id:
                cursor.execute(
                    """INSERT INTO test_scripts (script_path, environment_id)
                       VALUES (%s, %s::uuid)
                       ON CONFLICT (script_path) DO UPDATE SET updated_at = now()""",
                    [file_path, environment_id]
                )
            else:
                cursor.execute(
                    """INSERT INTO test_scripts (script_path)
                       VALUES (%s)
                       ON CONFLICT (script_path) DO UPDATE SET updated_at = now()""",
                    [file_path]
                )
        return JsonResponse({'success': True, 'path': file_path})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_dry_run(request):
    """Validate script (Node.js syntax check via subprocess)."""
    try:
        data = json.loads(request.body)
        code = data.get('code', '')
        if not code:
            return JsonResponse({'error': 'No code provided'}, status=400)
        import tempfile
        import subprocess
        with tempfile.NamedTemporaryFile(suffix='.js', mode='w', delete=False) as f:
            f.write(code)
            tmp_path = f.name
        result = subprocess.run(['node', '--check', tmp_path], capture_output=True, text=True, timeout=10)
        import os
        os.unlink(tmp_path)
        if result.returncode == 0:
            return JsonResponse({'success': True, 'message': 'Syntax valid — no errors found'})
        else:
            return JsonResponse({'error': result.stderr.strip()[:500]})
    except Exception as e:
        return JsonResponse({'error': str(e)})


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_associate(request):
    try:
        data = json.loads(request.body)
        script_path = data.get('scriptPath')
        if not script_path:
            return JsonResponse({'error': 'scriptPath required'}, status=400)

        item_id = data.get('itemId') or None
        assessment_id = data.get('assessmentId') or None
        category = data.get('category') or None
        test_type = data.get('testType') or None
        description = data.get('description') or None
        environment_id = data.get('environmentId') or None

        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_scripts (script_path, item_id, assessment_id, category, test_type, description, environment_id, updated_at)
                   VALUES (%s, %s, %s, %s, COALESCE(%s, 'functional'), %s, %s::uuid, now())
                   ON CONFLICT (script_path) DO UPDATE SET
                     item_id = COALESCE(EXCLUDED.item_id, test_scripts.item_id),
                     assessment_id = COALESCE(EXCLUDED.assessment_id, test_scripts.assessment_id),
                     category = COALESCE(EXCLUDED.category, test_scripts.category),
                     test_type = COALESCE(EXCLUDED.test_type, test_scripts.test_type),
                     description = COALESCE(EXCLUDED.description, test_scripts.description),
                     environment_id = COALESCE(EXCLUDED.environment_id, test_scripts.environment_id),
                     updated_at = now()""",
                [script_path, item_id, assessment_id, category, test_type, description, environment_id]
            )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def api_list(request):
    """RBAC-scoped list of test scripts from DB."""
    search = request.GET.get('search', '').strip()
    env_id = request.GET.get('environment_id', '').strip()

    where = []
    params = []

    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return JsonResponse({'scripts': [], 'total': 0}, default=str)
        params.append(tuple(str(e) for e in env_ids))
        where.append('ts.environment_id = ANY(%s::uuid[])')

    if search:
        s = search.lower()
        params.append(f'%{s}%')
        where.append('LOWER(ts.script_path) LIKE %s')

    if env_id:
        params.append(env_id)
        where.append('ts.environment_id = %s::uuid')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT ts.id, ts.script_path, ts.description, ts.item_id,
                   ts.assessment_id, ts.category, ts.test_type, ts.tags,
                   ts.environment_id, e.name AS environment_name
            FROM test_scripts ts
            LEFT JOIN environments e ON ts.environment_id = e.id
            {where_clause}
            ORDER BY ts.script_path
        """, params)
        cols = [c[0] for c in cursor.description]
        scripts = [dict(zip(cols, row)) for row in cursor.fetchall()]

    return JsonResponse({'scripts': scripts, 'total': len(scripts)}, default=str)
