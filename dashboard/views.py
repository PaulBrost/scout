from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import connection


@login_required(login_url='/login/')
def index(request):
    with connection.cursor() as cursor:
        # Latest run
        cursor.execute("""
            SELECT r.id, r.started_at, r.completed_at, r.status, r.trigger_type, r.summary,
                   s.name AS suite_name
            FROM test_runs r
            LEFT JOIN test_suites s ON r.suite_id = s.id
            ORDER BY r.started_at DESC LIMIT 1
        """)
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        latest_run = dict(zip(cols, row)) if row else None

        # Recent runs (5)
        cursor.execute("""
            SELECT r.id, r.started_at, r.status, r.trigger_type, r.summary, s.name AS suite_name
            FROM test_runs r
            LEFT JOIN test_suites s ON r.suite_id = s.id
            ORDER BY r.started_at DESC LIMIT 5
        """)
        cols = [c[0] for c in cursor.description]
        recent_runs = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # Pass rate trend (last 10 runs)
        cursor.execute("""
            SELECT id, started_at, status, summary
            FROM test_runs
            ORDER BY started_at DESC LIMIT 10
        """)
        cols = [c[0] for c in cursor.description]
        trend = [dict(zip(cols, row)) for row in cursor.fetchall()]

        # Pending AI flags
        cursor.execute("""
            SELECT COUNT(*) FROM ai_analyses
            WHERE status = 'pending' AND issues_found = true
        """)
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
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, started_at, status, summary
            FROM test_runs ORDER BY started_at DESC LIMIT %s
        """, [limit])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return JsonResponse({'trend': rows})


@login_required(login_url='/login/')
def api_ai_flags(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM ai_analyses
            WHERE status = 'pending' AND issues_found = true
        """)
        count = cursor.fetchone()[0]
    return JsonResponse({'count': count})
