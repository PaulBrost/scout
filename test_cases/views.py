import json
from pathlib import Path
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import connection


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


def get_all_test_scripts():
    """Scan filesystem + merge with DB registry."""
    tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
    scripts = {}

    # Scan filesystem
    if tests_dir.exists():
        for f in tests_dir.rglob('*.spec.js'):
            rel = str(f.relative_to(tests_dir))
            scripts[rel] = {
                'script_path': rel,
                'source': 'filesystem',
                'item_id': None,
                'assessment_id': None,
                'category': None,
                'description': None,
            }

    # Merge DB registry
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT ts.script_path, ts.description, ts.item_id, ts.assessment_id, ts.category,
                          ts.updated_at, i.title AS item_title
                   FROM test_scripts ts LEFT JOIN items i ON ts.item_id = i.item_id
                   ORDER BY ts.script_path"""
            )
            cols = [c[0] for c in cursor.description]
            for row in cursor.fetchall():
                d = dict(zip(cols, row))
                scripts[d['script_path']] = {**scripts.get(d['script_path'], {}), **d, 'source': 'registered'}
    except Exception:
        pass

    return list(scripts.values())


@login_required(login_url='/login/')
def index(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('page_size', 25))))
    search = request.GET.get('search', '').strip()
    category_filter = request.GET.get('category', '')

    all_scripts = get_all_test_scripts()

    # Filter
    filtered = all_scripts
    if search:
        s = search.lower()
        filtered = [sc for sc in filtered if s in sc['script_path'].lower()
                    or s in (sc.get('description') or '').lower()]
    if category_filter:
        filtered = [sc for sc in filtered if sc.get('category') == category_filter]

    total = len(filtered)
    offset = (page - 1) * page_size
    scripts = filtered[offset:offset + page_size]

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = offset + 1 if total > 0 else 0
    end_item = min(offset + page_size, total)

    return render(request, 'test_cases/list.html', {
        'scripts': scripts, 'total': total, 'page': page, 'page_size': page_size,
        'page_size_options': [10, 25, 50, 100], 'search': search, 'category_filter': category_filter,
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
        if not file_path or content is None:
            return JsonResponse({'error': 'Path and content required'}, status=400)

        tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
        full_path = (tests_dir / file_path).resolve()
        if not str(full_path).startswith(str(tests_dir)):
            return JsonResponse({'error': 'Access denied'}, status=403)

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')

        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO test_scripts (script_path) VALUES (%s) ON CONFLICT (script_path) DO UPDATE SET updated_at = now()',
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
        # Write to temp file and run node --check
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
        description = data.get('description') or None

        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_scripts (script_path, item_id, assessment_id, category, description, updated_at)
                   VALUES (%s, %s, %s, %s, %s, now())
                   ON CONFLICT (script_path) DO UPDATE SET
                     item_id = COALESCE(EXCLUDED.item_id, test_scripts.item_id),
                     assessment_id = COALESCE(EXCLUDED.assessment_id, test_scripts.assessment_id),
                     category = COALESCE(EXCLUDED.category, test_scripts.category),
                     description = COALESCE(EXCLUDED.description, test_scripts.description),
                     updated_at = now()""",
                [script_path, item_id, assessment_id, category, description]
            )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def api_list(request):
    scripts = get_all_test_scripts()
    search = request.GET.get('search', '').strip()
    if search:
        s = search.lower()
        scripts = [sc for sc in scripts if s in sc['script_path'].lower()]
    return JsonResponse({'scripts': scripts, 'total': len(scripts)}, default=str)
