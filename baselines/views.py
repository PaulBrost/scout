import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection
from core.mixins import get_user_env_ids


@login_required(login_url='/login/')
def index(request):
    status_filter = request.GET.get('status', '')
    env_filter = request.GET.get('environment', '')

    where = []
    params = []

    # RBAC scoping
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'baselines/list.html', {
                'baselines': [], 'environments': [],
                'status_filter': status_filter, 'env_filter': env_filter,
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('b.environment_id = ANY(%s::uuid[])')

    if status_filter == 'pending':
        where.append('b.approved_at IS NULL')
    elif status_filter == 'approved':
        where.append('b.approved_at IS NOT NULL')

    if env_filter:
        params.append(env_filter)
        where.append('b.environment_id = %s::uuid')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT b.id, b.item_id, b.browser, b.device_profile, b.version,
                   b.screenshot_path, b.approved_by, b.approved_at, b.created_at,
                   b.environment_id, e.name AS environment_name,
                   i.title AS item_title
            FROM baselines b
            LEFT JOIN environments e ON b.environment_id = e.id
            LEFT JOIN items i ON i.item_id = b.item_id
            {where_clause}
            ORDER BY b.created_at DESC
        """, params)
        cols = [c[0] for c in cursor.description]
        baselines = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Load environments for filter
    env_query = 'SELECT id, name FROM environments ORDER BY name'
    env_params = []
    if env_ids is not None:
        env_query = 'SELECT id, name FROM environments WHERE id = ANY(%s::uuid[]) ORDER BY name'
        env_params = [tuple(str(e) for e in env_ids)]
    with connection.cursor() as cursor:
        cursor.execute(env_query, env_params)
        environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]

    return render(request, 'baselines/list.html', {
        'baselines': baselines,
        'environments': environments,
        'status_filter': status_filter,
        'env_filter': env_filter,
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_approve(request, baseline_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Admin only'}, status=403)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE baselines SET approved_by = %s, approved_at = now()
                WHERE id = %s
            """, [request.user.username, str(baseline_id)])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_reject(request, baseline_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Admin only'}, status=403)
    try:
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM baselines WHERE id = %s', [str(baseline_id)])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
