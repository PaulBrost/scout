from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import connection
from core.mixins import get_user_env_ids, get_owner_filter


@login_required(login_url='/login/')
def index(request):
    # Build scope filters
    where = []
    params = []
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        params.append(list(str(e) for e in env_ids))
        where.append('(r.environment_id = ANY(%s::uuid[]) OR r.environment_id IS NULL)')
    owner_id, _ = get_owner_filter(request)
    if owner_id is not None:
        where.append('(r.created_by_id = %s OR r.created_by_id IS NULL)')
        params.append(owner_id)
    run_where = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        # Latest run
        cursor.execute(f"""
            SELECT r.id, r.started_at, r.completed_at, r.status, r.trigger_type, r.summary,
                   s.name AS suite_name,
                   (SELECT COALESCE(ts.description, trs.script_path)
                    FROM test_run_scripts trs
                    LEFT JOIN test_scripts ts ON ts.script_path = trs.script_path
                    WHERE trs.run_id = r.id LIMIT 1) AS first_script_name
            FROM test_runs r
            LEFT JOIN test_suites s ON r.suite_id = s.id
            {run_where}
            ORDER BY r.started_at DESC LIMIT 1
        """, params)
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        latest_run = dict(zip(cols, row)) if row else None

        # Recent runs (5) — include test/script names for display
        cursor.execute(f"""
            SELECT r.id, r.started_at, r.status, r.trigger_type, r.summary, s.name AS suite_name,
                   (SELECT string_agg(
                       COALESCE(ts.description, replace(replace(trs.script_path, 'tests/', ''), '.spec.js', '')),
                       ', ' ORDER BY trs.script_path
                    )
                    FROM test_run_scripts trs
                    LEFT JOIN test_scripts ts ON ts.script_path = trs.script_path
                    WHERE trs.run_id = r.id
                   ) AS test_names
            FROM test_runs r
            LEFT JOIN test_suites s ON r.suite_id = s.id
            {run_where}
            ORDER BY r.started_at DESC LIMIT 5
        """, params)
        cols = [c[0] for c in cursor.description]
        recent_runs = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # Pass rate trend (last 10 runs)
        cursor.execute(f"""
            SELECT r.id, r.started_at, r.status, r.summary
            FROM test_runs r
            {run_where}
            ORDER BY r.started_at DESC LIMIT 10
        """, params)
        cols = [c[0] for c in cursor.description]
        trend = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # Pending review issues (from AI analysis or screenshots)
        rv_where_parts = ["rv.status = 'pending'"]
        rv_params = []
        if env_ids is not None:
            rv_where_parts.append('(tr.environment_id = ANY(%s::uuid[]) OR tr.environment_id IS NULL)')
            rv_params.append(list(str(e) for e in env_ids))
        if owner_id is not None:
            rv_where_parts.append('(tr.created_by_id = %s OR tr.created_by_id IS NULL)')
            rv_params.append(owner_id)
        cursor.execute(f"""
            SELECT COUNT(*) FROM reviews rv
            LEFT JOIN ai_analyses aa ON rv.analysis_id = aa.id
            LEFT JOIN run_screenshots rs ON rv.screenshot_id = rs.id
            LEFT JOIN test_runs tr ON COALESCE(aa.run_id, rs.run_id) = tr.id
            WHERE {' AND '.join(rv_where_parts)}
        """, rv_params)
        ai_flag_count = cursor.fetchone()[0]

    import json
    # Parse summary JSON
    for run in recent_runs:
        if isinstance(run.get('summary'), str):
            try:
                run['summary'] = json.loads(run['summary'])
            except Exception:
                run['summary'] = {}
    if latest_run and isinstance(latest_run.get('summary'), str):
        try:
            latest_run['summary'] = json.loads(latest_run['summary'])
        except Exception:
            latest_run['summary'] = {}

    return render(request, 'dashboard/index.html', {
        'latest_run': latest_run,
        'recent_runs': recent_runs,
        'trend': trend,
        'ai_flag_count': ai_flag_count,
    })


@login_required(login_url='/login/')
def api_trend(request):
    limit = min(int(request.GET.get('limit', 10)), 50)
    where = []
    params = []
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        params.append(list(str(e) for e in env_ids))
        where.append('(r.environment_id = ANY(%s::uuid[]) OR r.environment_id IS NULL)')
    if not request.user.is_staff:
        where.append('(r.created_by_id = %s OR r.created_by_id IS NULL)')
        params.append(request.user.id)
    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''
    params.append(limit)
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT r.id, r.started_at, r.status, r.summary
            FROM test_runs r {where_clause} ORDER BY r.started_at DESC LIMIT %s
        """, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return JsonResponse({'trend': rows})


@login_required(login_url='/login/')
def api_ai_flags(request):
    where_parts = ["aa.status = 'pending'", "aa.issues_found = true"]
    params = []
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        where_parts.append('(r.environment_id = ANY(%s::uuid[]) OR r.environment_id IS NULL)')
        params.append(list(str(e) for e in env_ids))
    if not request.user.is_staff:
        where_parts.append('(r.created_by_id = %s OR r.created_by_id IS NULL)')
        params.append(request.user.id)
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT COUNT(*) FROM ai_analyses aa
            JOIN test_runs r ON aa.run_id = r.id
            WHERE {' AND '.join(where_parts)}
        """, params)
        count = cursor.fetchone()[0]
    return JsonResponse({'count': count})
