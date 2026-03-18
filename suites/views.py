import json
from datetime import datetime, date, time, timedelta
import zoneinfo
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection
from django.utils import timezone
from core.mixins import get_user_env_ids, build_user_scope_sql, can_user_access_record


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

    valid_sorts = {
        'name': 's.name',
        'scripts': 'script_count',
        'schedule': 's.schedule',
        'updated': 's.updated_at',
    }
    order_col = valid_sorts.get(sort, 's.name')

    where = []
    params = []

    # Environment scoping
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'suites/list.html', {
                'suites': [], 'total': 0, 'page': 1, 'page_size': page_size,
                'page_size_options': [10, 25, 50, 100],
                'sort': sort, 'direction': direction.lower(), 'search': search,
                'total_pages': 1, 'start_item': 0, 'end_item': 0, 'page_range': [],
            })
        params.append(list(str(e) for e in env_ids))
        where.append('s.environment_id = ANY(%s::uuid[])')

    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(s.name) LIKE %s OR LOWER(s.description) LIKE %s)')

    # User-level scoping
    if not request.user.is_staff:
        where.append('(s.created_by_id = %s OR s.created_by_id IS NULL)')
        params.append(request.user.id)

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM test_suites s {where_clause}',
            params
        )
        total = cursor.fetchone()[0]

        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT s.*,
                   (SELECT COUNT(*) FROM test_suite_scripts ss WHERE ss.suite_id = s.id) AS script_count,
                   tr.started_at AS last_run_at, tr.status AS last_run_status,
                   e.name AS environment_name,
                   COALESCE((s.schedule->>'enabled')::boolean, false) AS schedule_enabled
            FROM test_suites s
            LEFT JOIN environments e ON s.environment_id = e.id
            LEFT JOIN LATERAL (
                SELECT started_at, status FROM test_runs WHERE suite_id = s.id
                ORDER BY started_at DESC LIMIT 1
            ) tr ON true
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        suites = [dict(zip(cols, row)) for row in cursor.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = (page - 1) * page_size + 1 if total > 0 else 0
    end_item = min(page * page_size, total)

    return render(request, 'suites/list.html', {
        'suites': suites,
        'total': total,
        'page': page,
        'page_size': page_size,
        'page_size_options': [10, 25, 50, 100],
        'sort': sort,
        'direction': direction.lower(),
        'search': search,
        'total_pages': total_pages,
        'start_item': start_item,
        'end_item': end_item,
        'page_range': build_page_range(page, total_pages),
    })


def _get_scripts_for_environment(env_id, assessment_id=None, item_id=None, user=None):
    """Query DB for test scripts belonging to an environment, optionally filtered by assessment/item."""
    if not env_id:
        return []
    where = ['ts.environment_id = %s::uuid']
    params = [str(env_id)]
    if item_id:
        where.append('ts.item_id = %s')
        params.append(item_id)
    elif assessment_id:
        where.append('ts.assessment_id = %s')
        params.append(assessment_id)
    if user and not user.is_staff:
        where.append('(ts.created_by_id = %s OR ts.created_by_id IS NULL)')
        params.append(user.id)
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT ts.script_path, ts.description, ts.category, ts.test_type,
                   ts.assessment_id, ts.item_id
            FROM test_scripts ts
            WHERE {' AND '.join(where)}
            ORDER BY ts.script_path
        """, params)
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


@login_required(login_url='/login/')
def suite_new(request):
    from core.models import Environment
    env_ids = get_user_env_ids(request.user)
    if env_ids is None:
        environments = list(Environment.objects.values('id', 'name').order_by('name'))
    else:
        environments = list(Environment.objects.filter(id__in=env_ids).values('id', 'name').order_by('name'))
    return render(request, 'suites/detail.html', {
        'suite': None,
        'suite_scripts_json': '[]',
        'environments': environments,
    })


@login_required(login_url='/login/')
def suite_detail(request, suite_id):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT s.*, e.name AS environment_name FROM test_suites s LEFT JOIN environments e ON s.environment_id = e.id WHERE s.id = %s',
            [suite_id]
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        raise Http404

    suite = dict(zip(cols, row))

    # User-level access check
    if not can_user_access_record(request.user, suite.get('created_by_id')):
        raise Http404

    # Load suite script entries with browser/viewport and description from test_scripts
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ss.id, ss.script_path, ss.browser, ss.viewport,
                   ts.description, ts.test_type
            FROM test_suite_scripts ss
            LEFT JOIN test_scripts ts ON ss.script_path = ts.script_path
            WHERE ss.suite_id = %s
            ORDER BY ss.added_at
        """, [suite_id])
        cols = [c[0] for c in cursor.description]
        suite_scripts = [dict(zip(cols, row)) for row in cursor.fetchall()]

    from core.models import Environment
    env_ids = get_user_env_ids(request.user)
    if env_ids is None:
        environments = list(Environment.objects.values('id', 'name').order_by('name'))
    else:
        environments = list(Environment.objects.filter(id__in=env_ids).values('id', 'name').order_by('name'))

    # Parse schedule for template
    schedule = suite.get('schedule') or {}
    if isinstance(schedule, str):
        try:
            schedule = json.loads(schedule)
        except Exception:
            schedule = {}

    # Get user timezone for default
    user_tz = 'America/New_York'
    try:
        user_tz = request.user.settings.timezone
    except Exception:
        pass

    return render(request, 'suites/detail.html', {
        'suite': suite,
        'suite_scripts_json': json.dumps(suite_scripts, default=str),
        'environments': environments,
        'schedule': schedule,
        'schedule_json': json.dumps(schedule, default=str),
        'user_timezone': user_tz,
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def suite_create(request):
    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)
        description = data.get('description') or None
        scripts = data.get('scripts') or []
        environment_id = data.get('environment_id') or None

        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_suites (id, name, description, created_by_id, browser_profiles, environment_id, created_at, updated_at)
                   VALUES (gen_random_uuid(), %s, %s, %s, '[]'::jsonb, %s, now(), now()) RETURNING id""",
                [name, description, request.user.id, environment_id]
            )
            suite_id = cursor.fetchone()[0]
            for entry in scripts:
                sp = entry.get('script_path') if isinstance(entry, dict) else entry
                browser = entry.get('browser', 'chromium') if isinstance(entry, dict) else 'chromium'
                viewport = entry.get('viewport', '1920x1080') if isinstance(entry, dict) else '1920x1080'
                cursor.execute(
                    """INSERT INTO test_suite_scripts (suite_id, script_path, browser, viewport, added_at)
                       VALUES (%s, %s, %s, %s, now())
                       ON CONFLICT (suite_id, script_path, browser, viewport) DO NOTHING""",
                    [str(suite_id), sp, browser, viewport]
                )
        return JsonResponse({'id': str(suite_id), 'redirect': f'/suites/{suite_id}/'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT", "POST"])
@login_required(login_url='/login/')
def suite_update(request, suite_id):
    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)
        description = data.get('description') or None
        scripts = data.get('scripts') or []
        environment_id = data.get('environment_id') or None

        # Verify ownership
        with connection.cursor() as cursor:
            cursor.execute('SELECT created_by_id FROM test_suites WHERE id = %s', [suite_id])
            row = cursor.fetchone()
        if not row:
            return JsonResponse({'error': 'Suite not found'}, status=404)
        if not can_user_access_record(request.user, row[0]):
            return JsonResponse({'error': 'Access denied'}, status=403)

        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE test_suites SET name=%s, description=%s,
                   environment_id=%s, updated_at=now()
                   WHERE id=%s""",
                [name, description, environment_id, suite_id]
            )
            cursor.execute('DELETE FROM test_suite_scripts WHERE suite_id = %s', [suite_id])
            for entry in scripts:
                sp = entry.get('script_path') if isinstance(entry, dict) else entry
                browser = entry.get('browser', 'chromium') if isinstance(entry, dict) else 'chromium'
                viewport = entry.get('viewport', '1920x1080') if isinstance(entry, dict) else '1920x1080'
                cursor.execute(
                    """INSERT INTO test_suite_scripts (suite_id, script_path, browser, viewport, added_at)
                       VALUES (%s, %s, %s, %s, now())""",
                    [suite_id, sp, browser, viewport]
                )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
@login_required(login_url='/login/')
def suite_delete(request, suite_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT created_by_id, schedule FROM test_suites WHERE id = %s', [suite_id])
            row = cursor.fetchone()
        if not row:
            return JsonResponse({'error': 'Suite not found'}, status=404)
        if not can_user_access_record(request.user, row[0]):
            return JsonResponse({'error': 'Access denied'}, status=403)

        # Clean up django-q schedule if present
        schedule = row[1] or {}
        if isinstance(schedule, str):
            try:
                schedule = json.loads(schedule)
            except Exception:
                schedule = {}
        dq_id = schedule.get('dq_schedule_id')
        if dq_id:
            try:
                from django_q.models import Schedule as DQSchedule
                DQSchedule.objects.filter(id=dq_id).delete()
            except Exception:
                pass

        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM test_suites WHERE id = %s', [suite_id])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def suite_run(request, suite_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM test_suites WHERE id = %s', [suite_id])
            cols = [c[0] for c in cursor.description]
            row = cursor.fetchone()
        if not row:
            return JsonResponse({'error': 'Suite not found'}, status=404)
        suite = dict(zip(cols, row))

        # Verify suite ownership
        if not can_user_access_record(request.user, suite.get('created_by_id')):
            return JsonResponse({'error': 'Access denied'}, status=403)

        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT script_path, browser, viewport FROM test_suite_scripts WHERE suite_id = %s ORDER BY added_at',
                [suite_id]
            )
            suite_entries = [{'script_path': r[0], 'browser': r[1] or 'chromium', 'viewport': r[2] or '1920x1080'} for r in cursor.fetchall()]

        if not suite_entries:
            return JsonResponse({'error': 'Suite has no scripts'}, status=400)

        # Merge ai_config from all scripts in suite (OR logic: if any script wants analysis, enable it)
        ai_config = {'text_analysis': False, 'visual_analysis': False}
        script_paths_list = [e['script_path'] for e in suite_entries]
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT ai_config FROM test_scripts WHERE script_path = ANY(%s) AND ai_config IS NOT NULL',
                [script_paths_list]
            )
            for (cfg_row,) in cursor.fetchall():
                cfg = cfg_row or {}
                if isinstance(cfg, str):
                    try:
                        cfg = json.loads(cfg)
                    except Exception:
                        cfg = {}
                if cfg.get('text_analysis'):
                    ai_config['text_analysis'] = True
                if cfg.get('visual_analysis'):
                    ai_config['visual_analysis'] = True

        run_config = json.dumps({'ai_config': ai_config})

        # Create run
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO test_runs (id, status, trigger_type, suite_id, environment_id, config, notes, queued_at, created_by_id)
                   VALUES (gen_random_uuid(), 'running', 'dashboard', %s, %s, %s::jsonb, %s, now(), %s) RETURNING id""",
                [suite_id, suite.get('environment_id'), run_config, f"Suite: {suite['name']}", request.user.id]
            )
            run_id = cursor.fetchone()[0]
            for entry in suite_entries:
                cursor.execute(
                    """INSERT INTO test_run_scripts (id, run_id, script_path, browser, viewport, status)
                       VALUES (gen_random_uuid(), %s, %s, %s, %s, 'queued')""",
                    [str(run_id), entry['script_path'], entry['browser'], entry['viewport']]
                )

        # Run task in background thread
        from core.utils import spawn_background_task
        def _run_suite(rid=str(run_id)):
            try:
                from tasks.run_tasks import execute_suite_run
                execute_suite_run(rid)
            except Exception as e:
                print(f'[suite_run] error: {e}')
                from django.db import connection as conn
                with conn.cursor() as cur:
                    cur.execute("UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
        spawn_background_task(_run_suite)

        return JsonResponse({'runId': str(run_id), 'status': 'running', 'scripts': len(suite_entries)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def run_script(request):
    try:
        data = json.loads(request.body)
        script_path = data.get('scriptPath')
        if not script_path:
            return JsonResponse({'error': 'scriptPath required'}, status=400)

        with connection.cursor() as cursor:
            # Look up environment_id, browser, viewport, ai_config from test_scripts
            cursor.execute('SELECT environment_id, browser, viewport, ai_config FROM test_scripts WHERE script_path = %s', [script_path])
            ts_row = cursor.fetchone()
            environment_id = ts_row[0] if ts_row else None
            script_browser = (ts_row[1] if ts_row else None) or 'chromium'
            script_viewport = (ts_row[2] if ts_row else None) or '1920x1080'
            script_ai_config = ts_row[3] if ts_row else {}
            if isinstance(script_ai_config, str):
                try:
                    script_ai_config = json.loads(script_ai_config)
                except Exception:
                    script_ai_config = {}
            if not script_ai_config:
                script_ai_config = {}
            if not environment_id and data.get('environment_id'):
                environment_id = data['environment_id']
            # Allow POST body to override browser/viewport for this run
            if data.get('browser'):
                script_browser = data['browser']
            if data.get('viewport'):
                script_viewport = data['viewport']

            scheduled_at = data.get('scheduled_at')
            # AI config: POST body overrides script defaults
            ai_config = data.get('ai_config', script_ai_config)
            config = {'ai_config': ai_config}
            if scheduled_at:
                config['scheduled_at'] = scheduled_at

            run_status = 'scheduled' if scheduled_at else 'running'

            cursor.execute(
                """INSERT INTO test_runs (id, status, trigger_type, environment_id, config, notes, queued_at, created_by_id)
                   VALUES (gen_random_uuid(), %s, 'manual', %s, %s, %s, now(), %s) RETURNING id""",
                [run_status, str(environment_id) if environment_id else None,
                 json.dumps(config), f'Ad-hoc: {script_path}', request.user.id]
            )
            run_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO test_run_scripts (id, run_id, script_path, browser, viewport, status)
                   VALUES (gen_random_uuid(), %s, %s, %s, %s, 'queued')""",
                [str(run_id), script_path, script_browser, script_viewport]
            )

        # Only queue for immediate execution if not scheduled
        if not scheduled_at:
            from core.utils import spawn_background_task
            def _run_task(rid=str(run_id), sp=script_path):
                try:
                    from tasks.run_tasks import execute_single_script
                    execute_single_script(rid, sp)
                except Exception as e:
                    print(f'[run_script] run error: {e}')
                    from django.db import connection as conn
                    with conn.cursor() as cur:
                        cur.execute("UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
                        cur.execute("UPDATE test_run_scripts SET status='error', error_message=%s, completed_at=now() WHERE run_id=%s AND status IN ('queued','running')", [str(e), rid])
            spawn_background_task(_run_task)

        return JsonResponse({'runId': str(run_id), 'status': run_status})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def api_list(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('pageSize', 25))))
    sort = request.GET.get('sort', 'name')
    direction = 'DESC' if request.GET.get('dir', 'asc') == 'desc' else 'ASC'
    search = request.GET.get('search', '').strip()

    valid_sorts = {'name': 's.name', 'scripts': 'script_count', 'updated': 's.updated_at'}
    order_col = valid_sorts.get(sort, 's.name')

    where = []
    params = []

    # Environment scoping
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return JsonResponse({'rows': [], 'total': 0, 'page': page, 'pageSize': page_size}, json_dumps_params={'default': str})
        params.append(list(str(e) for e in env_ids))
        where.append('s.environment_id = ANY(%s::uuid[])')

    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(s.name) LIKE %s OR LOWER(s.description) LIKE %s)')

    # User-level scoping
    if not request.user.is_staff:
        where.append('(s.created_by_id = %s OR s.created_by_id IS NULL)')
        params.append(request.user.id)

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM test_suites s {where_clause}', params)
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT s.*,
                   (SELECT COUNT(*) FROM test_suite_scripts ss WHERE ss.suite_id = s.id) AS script_count,
                   tr.started_at AS last_run_at, tr.status AS last_run_status
            FROM test_suites s
            LEFT JOIN LATERAL (
                SELECT started_at, status FROM test_runs WHERE suite_id = s.id ORDER BY started_at DESC LIMIT 1
            ) tr ON true
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_scripts_by_environment(request):
    """Return test scripts for a given environment (with RBAC), optionally filtered by assessment/item."""
    env_id = request.GET.get('environment_id', '').strip()
    if not env_id:
        return JsonResponse({'scripts': []})

    # RBAC check
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None and env_id not in [str(e) for e in env_ids]:
        return JsonResponse({'scripts': []})

    assessment_id = request.GET.get('assessment_id', '').strip() or None
    item_id = request.GET.get('item_id', '').strip() or None
    scripts = _get_scripts_for_environment(env_id, assessment_id=assessment_id, item_id=item_id, user=request.user)
    return JsonResponse({'scripts': scripts}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_assessments_by_environment(request):
    """Return assessments for a given environment."""
    env_id = request.GET.get('environment_id', '').strip()
    if not env_id:
        return JsonResponse({'assessments': []})

    env_ids = get_user_env_ids(request.user)
    if env_ids is not None and env_id not in [str(e) for e in env_ids]:
        return JsonResponse({'assessments': []})

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, name, item_count
            FROM assessments
            WHERE environment_id = %s::uuid
            ORDER BY name
        """, [str(env_id)])
        cols = [c[0] for c in cursor.description]
        assessments = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return JsonResponse({'assessments': assessments}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_items_by_assessment(request):
    """Return items for a given assessment."""
    assessment_id = request.GET.get('assessment_id', '').strip()
    if not assessment_id:
        return JsonResponse({'items': []})

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT item_id, title
            FROM items
            WHERE assessment_id = %s
            ORDER BY position, item_id
        """, [assessment_id])
        cols = [c[0] for c in cursor.description]
        items = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return JsonResponse({'items': items}, json_dumps_params={'default': str})


# ═══════════════════════════════════════════════════════════════════
#  Suite Scheduling
# ═══════════════════════════════════════════════════════════════════

DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _compute_next_run(schedule_data):
    """Compute the next run datetime (timezone-aware) from schedule config."""
    tz_name = schedule_data.get('timezone', 'America/New_York')
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo('America/New_York')

    now = datetime.now(tz)
    time_str = schedule_data.get('time', '09:00')
    try:
        hh, mm = [int(x) for x in time_str.split(':')]
    except Exception:
        hh, mm = 9, 0
    run_time = time(hh, mm)
    pattern = schedule_data.get('pattern', 'daily')

    if pattern == 'once':
        once_date = schedule_data.get('once_date')
        if once_date:
            try:
                d = date.fromisoformat(once_date)
                return datetime.combine(d, run_time, tzinfo=tz)
            except Exception:
                pass
        return datetime.combine(now.date(), run_time, tzinfo=tz)

    if pattern == 'hourly':
        interval = int(schedule_data.get('interval_hours', 4))
        # Next occurrence: round up to next interval boundary from start of day
        candidate = datetime.combine(now.date(), run_time, tzinfo=tz)
        while candidate <= now:
            candidate += timedelta(hours=interval)
        return candidate

    if pattern == 'daily':
        candidate = datetime.combine(now.date(), run_time, tzinfo=tz)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if pattern == 'weekly':
        days = schedule_data.get('days_of_week', [0])  # 0=Mon
        if not days:
            days = [0]
        # Find next matching weekday
        for offset in range(8):
            candidate = datetime.combine(now.date() + timedelta(days=offset), run_time, tzinfo=tz)
            if candidate > now and candidate.weekday() in days:
                return candidate
        # Fallback
        return datetime.combine(now.date() + timedelta(days=1), run_time, tzinfo=tz)

    if pattern == 'monthly':
        day_of_month = int(schedule_data.get('day_of_month', 1))
        day_of_month = max(1, min(28, day_of_month))
        try:
            candidate = datetime.combine(
                now.date().replace(day=day_of_month), run_time, tzinfo=tz
            )
        except ValueError:
            candidate = datetime.combine(now.date().replace(day=1), run_time, tzinfo=tz)
        if candidate <= now:
            # Next month
            if now.month == 12:
                candidate = candidate.replace(year=now.year + 1, month=1)
            else:
                candidate = candidate.replace(month=now.month + 1)
        return candidate

    return datetime.combine(now.date() + timedelta(days=1), run_time, tzinfo=tz)


def _build_cron_expression(schedule_data):
    """Build a cron expression for weekly schedules."""
    time_str = schedule_data.get('time', '09:00')
    try:
        hh, mm = [int(x) for x in time_str.split(':')]
    except Exception:
        hh, mm = 9, 0
    days = schedule_data.get('days_of_week', [0])
    # Convert Python weekday (0=Mon) to cron weekday (1=Mon, 7=Sun)
    cron_days = ','.join(str(d + 1) for d in sorted(days))
    return f'{mm} {hh} * * {cron_days}'


def _sync_dq_schedule(suite_id, schedule_data):
    """Create or update the django-q Schedule record. Returns the schedule ID."""
    from django_q.models import Schedule as DQSchedule

    name = f'suite_schedule_{suite_id}'
    func = 'tasks.run_tasks.execute_scheduled_suite'
    args = f"('{suite_id}',)"
    pattern = schedule_data.get('pattern', 'daily')
    next_run = _compute_next_run(schedule_data)

    # Check end_date for repeats
    end_date = schedule_data.get('end_date')
    repeats = -1  # infinite

    defaults = {
        'func': func,
        'args': args,
        'next_run': next_run,
        'repeats': repeats,
    }

    if pattern == 'once':
        defaults['schedule_type'] = DQSchedule.ONCE
        defaults['repeats'] = 1
    elif pattern == 'hourly':
        defaults['schedule_type'] = DQSchedule.MINUTES
        defaults['minutes'] = int(schedule_data.get('interval_hours', 4)) * 60
    elif pattern == 'daily':
        defaults['schedule_type'] = DQSchedule.DAILY
    elif pattern == 'weekly':
        defaults['schedule_type'] = DQSchedule.CRON
        defaults['cron'] = _build_cron_expression(schedule_data)
    elif pattern == 'monthly':
        defaults['schedule_type'] = DQSchedule.MONTHLY
    else:
        defaults['schedule_type'] = DQSchedule.DAILY

    obj, _created = DQSchedule.objects.update_or_create(name=name, defaults=defaults)
    return obj.id


def _build_schedule_summary(schedule_data):
    """Build a human-readable schedule summary."""
    pattern = schedule_data.get('pattern', 'daily')
    time_str = schedule_data.get('time', '09:00')
    tz_name = schedule_data.get('timezone', 'America/New_York')
    # Short tz display
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
        tz_abbr = datetime.now(tz).strftime('%Z')
    except Exception:
        tz_abbr = tz_name

    if pattern == 'once':
        once_date = schedule_data.get('once_date', 'TBD')
        return f'Once on {once_date} at {time_str} {tz_abbr}'
    if pattern == 'hourly':
        hours = schedule_data.get('interval_hours', 4)
        return f'Every {hours} hours starting at {time_str} {tz_abbr}'
    if pattern == 'daily':
        return f'Daily at {time_str} {tz_abbr}'
    if pattern == 'weekly':
        days = schedule_data.get('days_of_week', [])
        day_labels = [DAY_NAMES[d] for d in sorted(days) if d < 7]
        return f'Every {", ".join(day_labels)} at {time_str} {tz_abbr}'
    if pattern == 'monthly':
        dom = schedule_data.get('day_of_month', 1)
        return f'Monthly on day {dom} at {time_str} {tz_abbr}'
    return 'Unknown schedule'


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def save_schedule(request, suite_id):
    """Save or update a suite's schedule."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Verify ownership
    with connection.cursor() as cursor:
        cursor.execute('SELECT created_by_id FROM test_suites WHERE id = %s', [suite_id])
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'error': 'Suite not found'}, status=404)
    if not can_user_access_record(request.user, row[0]):
        return JsonResponse({'error': 'Access denied'}, status=403)

    pattern = data.get('pattern', 'daily')
    if pattern not in ('once', 'hourly', 'daily', 'weekly', 'monthly'):
        return JsonResponse({'error': 'Invalid pattern'}, status=400)

    schedule_data = {
        'enabled': bool(data.get('enabled', True)),
        'pattern': pattern,
        'time': data.get('time', '09:00'),
        'timezone': data.get('timezone', 'America/New_York'),
        'interval_hours': data.get('interval_hours'),
        'days_of_week': data.get('days_of_week', []),
        'day_of_month': data.get('day_of_month'),
        'once_date': data.get('once_date'),
        'end_date': data.get('end_date') or None,
        'created_by_id': request.user.id,
    }

    if schedule_data['enabled']:
        dq_id = _sync_dq_schedule(str(suite_id), schedule_data)
        schedule_data['dq_schedule_id'] = dq_id
    else:
        # Disable: remove django-q schedule
        from django_q.models import Schedule as DQSchedule
        DQSchedule.objects.filter(name=f'suite_schedule_{suite_id}').delete()
        schedule_data['dq_schedule_id'] = None

    next_run = _compute_next_run(schedule_data)
    schedule_data['next_run'] = next_run.isoformat()
    summary = _build_schedule_summary(schedule_data)

    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE test_suites SET schedule = %s::jsonb, updated_at = now() WHERE id = %s',
            [json.dumps(schedule_data, default=str), str(suite_id)]
        )

    return JsonResponse({
        'ok': True,
        'schedule': schedule_data,
        'summary': summary,
        'next_run': next_run.isoformat(),
    }, json_dumps_params={'default': str})


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def delete_schedule(request, suite_id):
    """Remove a suite's schedule."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT created_by_id, schedule FROM test_suites WHERE id = %s', [suite_id])
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'error': 'Suite not found'}, status=404)
    if not can_user_access_record(request.user, row[0]):
        return JsonResponse({'error': 'Access denied'}, status=403)

    # Remove django-q schedule
    schedule = row[1] or {}
    if isinstance(schedule, str):
        try:
            schedule = json.loads(schedule)
        except Exception:
            schedule = {}
    dq_id = schedule.get('dq_schedule_id')
    if dq_id:
        try:
            from django_q.models import Schedule as DQSchedule
            DQSchedule.objects.filter(id=dq_id).delete()
        except Exception:
            pass

    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE test_suites SET schedule = NULL, updated_at = now() WHERE id = %s',
            [str(suite_id)]
        )

    return JsonResponse({'ok': True})
