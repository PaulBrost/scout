import json
import shutil
import mimetypes
from pathlib import Path
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.db import connection
from django.conf import settings
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_POST
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
    sort = request.GET.get('sort', 'started')
    direction = 'ASC' if request.GET.get('dir', 'desc') == 'asc' else 'DESC'
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '').strip()

    valid_sorts = {
        'started': 'r.queued_at',
        'status': 'r.status',
        'trigger': 'r.trigger_type',
        'suite': 's.name',
    }
    order_col = valid_sorts.get(sort, 'r.queued_at')

    where = []
    params = []

    # RBAC scoping via environment
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'runs/list.html', {
                'runs': [], 'total': 0, 'page': 1, 'page_size': page_size,
                'page_size_options': [10, 25, 50, 100],
                'sort': sort, 'direction': 'asc' if direction == 'ASC' else 'desc',
                'search': search, 'status_filter': status_filter,
                'total_pages': 1, 'start_item': 0, 'end_item': 0, 'page_range': [],
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('(r.environment_id = ANY(%s::uuid[]) OR r.environment_id IS NULL)')

    if status_filter:
        params.append(status_filter)
        where.append('r.status = %s')
    if search:
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(r.notes) LIKE %s OR LOWER(s.name) LIKE %s)')
        params.append(f'%{search.lower()}%')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id {where_clause}',
            params
        )
        total = cursor.fetchone()[0]

        offset = (page - 1) * page_size
        row_params = params + [page_size, offset]
        cursor.execute(f"""
            SELECT r.id, r.queued_at, r.started_at, r.completed_at, r.status, r.trigger_type, r.summary, r.notes,
                   s.id AS suite_id, s.name AS suite_name,
                   (SELECT COUNT(*) FROM test_run_scripts rs WHERE rs.run_id = r.id) AS script_count,
                   (SELECT COALESCE(ts.description, trs.script_path)
                    FROM test_run_scripts trs
                    LEFT JOIN test_scripts ts ON ts.script_path = trs.script_path
                    WHERE trs.run_id = r.id LIMIT 1) AS first_script_name
            FROM test_runs r
            LEFT JOIN test_suites s ON r.suite_id = s.id
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, row_params)
        cols = [c[0] for c in cursor.description]
        runs = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Parse summary JSON
    for run in runs:
        if isinstance(run.get('summary'), str):
            try:
                run['summary'] = json.loads(run['summary'])
            except Exception:
                run['summary'] = {}

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = (page - 1) * page_size + 1 if total > 0 else 0
    end_item = min(page * page_size, total)

    return render(request, 'runs/list.html', {
        'runs': runs,
        'total': total,
        'page': page,
        'page_size': page_size,
        'page_size_options': [10, 25, 50, 100],
        'sort': sort,
        'direction': 'asc' if direction == 'ASC' else 'desc',
        'search': search,
        'status_filter': status_filter,
        'total_pages': total_pages,
        'start_item': start_item,
        'end_item': end_item,
        'page_range': build_page_range(page, total_pages),
    })


@login_required(login_url='/login/')
@ensure_csrf_cookie
def detail(request, run_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT r.*, s.name AS suite_name, s.id AS suite_id
               FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id
               WHERE r.id = %s""",
            [run_id]
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        from django.http import Http404
        raise Http404
    run = dict(zip(cols, row))

    # RBAC: non-admin users can only view runs for their assigned environments
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        run_env = str(run.get('environment_id') or '')
        if run_env and run_env not in [str(e) for e in env_ids]:
            raise Http404

    # Parse summary
    if isinstance(run.get('summary'), str):
        try:
            run['summary'] = json.loads(run['summary'])
        except Exception:
            run['summary'] = {}

    # Script results with test name/summary and linked assessment/item from test_scripts
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT trs.*, ts.description AS test_name, ts.test_summary,
                   ts.item_id, ts.assessment_id, ts.environment_id AS script_env_id,
                   i.title AS item_title, i.numeric_id AS item_numeric_id,
                   a.name AS assessment_name, a.numeric_id AS assessment_numeric_id,
                   e.name AS environment_name
            FROM test_run_scripts trs
            LEFT JOIN test_scripts ts ON trs.script_path = ts.script_path
            LEFT JOIN items i ON ts.item_id = i.item_id
            LEFT JOIN assessments a ON ts.assessment_id = a.id
            LEFT JOIN environments e ON ts.environment_id = e.id
            WHERE trs.run_id = %s
            ORDER BY trs.completed_at DESC NULLS LAST, trs.script_path
        """, [run_id])
        cols = [c[0] for c in cursor.description]
        script_results = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # For ad-hoc runs, derive a test name from the first script result
    if not run.get('suite_id') and script_results:
        run['test_name'] = script_results[0].get('test_name') or script_results[0].get('script_path', '')

    # Collect unique assessment/item/environment links across all scripts in this run
    run_assessment = None
    run_item = None
    run_environment = None
    for sr in script_results:
        if not run_assessment and sr.get('assessment_name'):
            run_assessment = {
                'name': sr['assessment_name'],
                'numeric_id': sr['assessment_numeric_id'],
            }
        if not run_item and sr.get('item_id'):
            run_item = {
                'item_id': sr['item_id'],
                'title': sr.get('item_title'),
                'numeric_id': sr['item_numeric_id'],
            }
        if not run_environment and sr.get('environment_name'):
            run_environment = {
                'name': sr['environment_name'],
                'id': sr['script_env_id'],
            }

    # Screenshots with review status
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT rs.*, rv.status AS review_status, rv.id AS review_id
               FROM run_screenshots rs
               LEFT JOIN reviews rv ON rv.screenshot_id = rs.id
                   AND rv.source_type = 'screenshot'
               WHERE rs.run_id = %s
               ORDER BY regexp_replace(rs.name, '\\d+', '', 'g'),
                        COALESCE(NULLIF(regexp_replace(rs.name, '\\D+', '', 'g'), '')::numeric, 0),
                        rs.name""",
            [run_id]
        )
        cols = [c[0] for c in cursor.description]
        screenshots = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # AI Analyses
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, analysis_type, status, issues_found, issues, summary,
                   model_used, duration_ms, screenshot_name, created_at
            FROM ai_analyses WHERE run_id = %s
            ORDER BY created_at DESC
        """, [run_id])
        cols = [c[0] for c in cursor.description]
        analyses = [dict(zip(cols, r)) for r in cursor.fetchall()]

    for a in analyses:
        if isinstance(a.get('issues'), str):
            try:
                a['issues'] = json.loads(a['issues'])
            except Exception:
                a['issues'] = []

    # Check if any script in this run has ai_config enabled
    ai_config_enabled = False
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ts.ai_config FROM test_run_scripts trs
            JOIN test_scripts ts ON ts.script_path = trs.script_path
            WHERE trs.run_id = %s AND ts.ai_config IS NOT NULL
            LIMIT 1
        """, [run_id])
        row = cursor.fetchone()
        if row and row[0]:
            cfg = row[0]
            if isinstance(cfg, str):
                try:
                    cfg = json.loads(cfg)
                except Exception:
                    cfg = {}
            ai_config_enabled = bool(cfg.get('text_analysis') or cfg.get('visual_analysis'))

    # Load AI analysis enabled flags from ai_settings
    text_analysis_enabled = True
    vision_analysis_enabled = True
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT key, value FROM ai_settings WHERE key IN ('text_analysis_enabled', 'vision_analysis_enabled')"
        )
        for key, val in cursor.fetchall():
            if isinstance(val, str):
                val = val.strip().strip('"').lower()
            if key == 'text_analysis_enabled':
                text_analysis_enabled = val not in (False, 'false', '0', '')
            elif key == 'vision_analysis_enabled':
                vision_analysis_enabled = val not in (False, 'false', '0', '')

    # Check if any script in this run has extracted page text ([SCOUT_TEXT] markers)
    has_extracted_text = False
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 1 FROM test_run_scripts
            WHERE run_id = %s AND execution_log LIKE '%%[SCOUT_TEXT]%%'
            LIMIT 1
        """, [run_id])
        has_extracted_text = cursor.fetchone() is not None

    return render(request, 'runs/detail.html', {
        'run': run,
        'script_results': script_results,
        'screenshots': screenshots,
        'analyses': analyses,
        'analyses_json': json.dumps([{
            'analysis_type': a['analysis_type'],
            'status': a['status'],
            'issues_found': a['issues_found'],
            'issues': a['issues'],
            'summary': a.get('summary') or '',
        } for a in analyses], default=str),
        'summaries_json': json.dumps([sr.get('test_summary') or '' for sr in script_results], default=str),
        'ai_config_enabled': ai_config_enabled,
        'text_analysis_enabled': text_analysis_enabled,
        'vision_analysis_enabled': vision_analysis_enabled,
        'has_extracted_text': has_extracted_text,
        'run_assessment': run_assessment,
        'run_item': run_item,
        'run_environment': run_environment,
    })


@login_required(login_url='/login/')
def script_detail(request, run_id, script_id):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT * FROM test_run_scripts WHERE run_id = %s AND id = %s',
            [run_id, script_id]
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse(dict(zip(cols, row)), json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_run_status(request, run_id):
    """Lightweight JSON endpoint for polling run status + script results."""
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT status, summary, queued_at, started_at, completed_at FROM test_runs WHERE id = %s',
            [run_id]
        )
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'error': 'Not found'}, status=404)

    run_status = row[0]
    summary = row[1]
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except Exception:
            summary = {}

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT id, script_path, status, duration_ms, error_message,
                      execution_log IS NOT NULL AS has_log,
                      CASE WHEN status = 'running' THEN execution_log ELSE NULL END AS live_log,
                      started_at, completed_at, browser, viewport
               FROM test_run_scripts WHERE run_id = %s
               ORDER BY completed_at DESC NULLS LAST, script_path""",
            [run_id]
        )
        cols = [c[0] for c in cursor.description]
        scripts = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return JsonResponse({
        'status': run_status,
        'summary': summary,
        'queued_at': row[2],
        'started_at': row[3],
        'completed_at': row[4],
        'scripts': scripts,
    }, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_list(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('pageSize', 25))))
    sort = request.GET.get('sort', 'started')
    direction = 'ASC' if request.GET.get('dir', 'desc') == 'asc' else 'DESC'
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '').strip()

    valid_sorts = {'started': 'r.queued_at', 'status': 'r.status', 'trigger': 'r.trigger_type', 'suite': 's.name'}
    order_col = valid_sorts.get(sort, 'r.queued_at')

    where = []
    params = []

    # RBAC scoping via environment
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return JsonResponse({'rows': [], 'total': 0, 'page': page, 'pageSize': page_size})
        params.append(tuple(str(e) for e in env_ids))
        where.append('(r.environment_id = ANY(%s::uuid[]) OR r.environment_id IS NULL)')

    if status_filter:
        params.append(status_filter)
        where.append('r.status = %s')
    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(r.notes) LIKE %s OR LOWER(s.name) LIKE %s)')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id {where_clause}',
            params
        )
        total = cursor.fetchone()[0]
        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT r.id, r.queued_at, r.started_at, r.completed_at, r.status, r.trigger_type, r.summary,
                   s.name AS suite_name,
                   (SELECT COUNT(*) FROM test_run_scripts rs WHERE rs.run_id = r.id) AS script_count
            FROM test_runs r LEFT JOIN test_suites s ON r.suite_id = s.id
            {where_clause}
            ORDER BY {order_col} {direction}
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return JsonResponse({'rows': rows, 'total': total, 'page': page, 'pageSize': page_size}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_latest(request):
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM test_runs ORDER BY queued_at DESC NULLS LAST LIMIT 1')
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'run': None})
    run = dict(zip(cols, row))
    if isinstance(run.get('summary'), str):
        try:
            run['summary'] = json.loads(run['summary'])
        except Exception:
            pass
    return JsonResponse({'run': run}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def serve_screenshot(request, file_path):
    """Serve a screenshot/artifact from archive, falling back to Playwright root."""
    allowed_ext = ('.png', '.jpg', '.jpeg', '.webp')

    # Try archive directory first (persistent storage)
    archive_root = Path(settings.SCOUT_ARCHIVE_DIR)
    full_path = (archive_root / file_path).resolve()
    if (str(full_path).startswith(str(archive_root.resolve()))
            and full_path.exists() and full_path.is_file()
            and full_path.suffix.lower() in allowed_ext):
        content_type = mimetypes.guess_type(str(full_path))[0] or 'image/png'
        return HttpResponse(full_path.read_bytes(), content_type=content_type)

    # Fallback: Playwright project root (legacy paths)
    pw_root = Path(settings.PLAYWRIGHT_PROJECT_ROOT)
    full_path = (pw_root / file_path).resolve()
    if not str(full_path).startswith(str(pw_root.resolve())):
        raise Http404
    if not full_path.exists() or not full_path.is_file():
        raise Http404
    if full_path.suffix.lower() not in allowed_ext:
        raise Http404

    content_type = mimetypes.guess_type(str(full_path))[0] or 'image/png'
    return HttpResponse(full_path.read_bytes(), content_type=content_type)


@login_required(login_url='/login/')
@require_POST
def api_flag_screenshot(request, screenshot_id):
    """Toggle the flagged status of a screenshot, with optional notes."""
    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    with connection.cursor() as cursor:
        cursor.execute('SELECT flagged FROM run_screenshots WHERE id = %s', [screenshot_id])
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'error': 'Not found'}, status=404)

    new_flagged = data.get('flagged', not row[0])
    flag_notes = data.get('notes', None)
    review_status = data.get('review_status', 'pending')

    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE run_screenshots SET flagged = %s, flag_notes = %s WHERE id = %s',
            [new_flagged, flag_notes, screenshot_id]
        )

        if new_flagged:
            # Upsert a review for this screenshot
            cursor.execute(
                "SELECT id FROM reviews WHERE screenshot_id = %s AND source_type = 'screenshot'",
                [str(screenshot_id)]
            )
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    "UPDATE reviews SET status = %s, notes = %s WHERE id = %s",
                    [review_status, flag_notes, existing[0]]
                )
            else:
                cursor.execute(
                    """INSERT INTO reviews (id, screenshot_id, source_type, status, notes, created_at)
                       VALUES (gen_random_uuid(), %s, 'screenshot', %s, %s, now())""",
                    [str(screenshot_id), review_status, flag_notes]
                )
        else:
            # Remove any pending review when unflagging
            cursor.execute(
                "DELETE FROM reviews WHERE screenshot_id = %s AND source_type = 'screenshot' AND status = 'pending'",
                [str(screenshot_id)]
            )

    return JsonResponse({'id': str(screenshot_id), 'flagged': new_flagged, 'flag_notes': flag_notes, 'review_status': review_status})


@login_required(login_url='/login/')
def api_runs_with_screenshots(request):
    """Return recent runs that have screenshots, for comparison dropdown.

    Scoped to runs that share the same script(s) as the given `for_run` param,
    so only related runs appear (same test, same assessment).
    """
    search = request.GET.get('q', '').strip()
    exclude_run = request.GET.get('exclude', '')
    for_run = request.GET.get('for_run', '')
    limit = min(20, max(1, int(request.GET.get('limit', 15))))

    where = ["(SELECT COUNT(*) FROM run_screenshots rs WHERE rs.run_id = r.id) > 0"]
    params = []

    if exclude_run:
        where.append("r.id != %s::uuid")
        params.append(exclude_run)

    # Scope to runs that share the same script_path(s) as the current run
    if for_run:
        where.append("""EXISTS (
            SELECT 1 FROM test_run_scripts trs2
            WHERE trs2.run_id = r.id
              AND trs2.script_path IN (
                  SELECT script_path FROM test_run_scripts WHERE run_id = %s::uuid
              )
        )""")
        params.append(for_run)

    if search:
        where.append("""(r.id::text LIKE %s OR LOWER(COALESCE(r.notes, '')) LIKE %s
                        OR LOWER(COALESCE(s.name, '')) LIKE %s
                        OR LOWER(COALESCE(ts.description, '')) LIKE %s)""")
        q = f'%{search.lower()}%'
        params.extend([q, q, q, q])

    # RBAC
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return JsonResponse({'runs': []})
        where.append('(r.environment_id = ANY(%s::uuid[]) OR r.environment_id IS NULL)')
        params.append(tuple(str(e) for e in env_ids))

    where_sql = ' AND '.join(where)
    params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT r.id, r.status, r.trigger_type, r.queued_at, r.completed_at,
                   COALESCE(s.name, ts.description, trs.script_path) AS label,
                   (SELECT COUNT(*) FROM run_screenshots rs WHERE rs.run_id = r.id) AS screenshot_count
            FROM test_runs r
            LEFT JOIN test_suites s ON r.suite_id = s.id
            LEFT JOIN test_run_scripts trs ON trs.run_id = r.id
            LEFT JOIN test_scripts ts ON ts.script_path = trs.script_path
            WHERE {where_sql}
            ORDER BY r.queued_at DESC
            LIMIT %s
        """, params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Deduplicate by run id (joins may produce multiple rows per run)
    seen = set()
    runs = []
    for row in rows:
        rid = str(row['id'])
        if rid not in seen:
            seen.add(rid)
            runs.append(row)

    return JsonResponse({'runs': runs}, json_dumps_params={'default': str})


@login_required(login_url='/login/')
def api_run_screenshots(request, run_id):
    """Return screenshots for a run as JSON."""
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT id, run_id, run_script_id, name, file_path, project_name, flagged, flag_notes, created_at
               FROM run_screenshots WHERE run_id = %s
               ORDER BY regexp_replace(name, '\\d+', '', 'g'),
                        COALESCE(NULLIF(regexp_replace(name, '\\D+', '', 'g'), '')::numeric, 0),
                        name""",
            [run_id]
        )
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    return JsonResponse({'screenshots': rows}, json_dumps_params={'default': str})


@csrf_exempt
@require_POST
@login_required(login_url='/login/')
def api_clear_analyses(request, run_id):
    """Delete all AI analyses (and related reviews) for a run."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM reviews WHERE analysis_id IN (SELECT id FROM ai_analyses WHERE run_id = %s)', [str(run_id)])
            cursor.execute('DELETE FROM ai_analyses WHERE run_id = %s', [str(run_id)])
            deleted = cursor.rowcount
        return JsonResponse({'ok': True, 'deleted': deleted})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
@require_POST
def api_run_analyze(request, run_id):
    """Trigger AI analysis on a completed run's artifacts."""
    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    analysis_type = data.get('type', 'both')  # 'text', 'visual', or 'both'

    # Verify run exists and is complete
    with connection.cursor() as cursor:
        cursor.execute('SELECT status FROM test_runs WHERE id = %s', [run_id])
        row = cursor.fetchone()
    if not row:
        return JsonResponse({'error': 'Run not found'}, status=404)
    if row[0] in ('running', 'scheduled'):
        return JsonResponse({'error': 'Run is still in progress'}, status=400)

    from core.utils import spawn_background_task

    def _run_analysis(rid=str(run_id), atype=analysis_type):
        try:
            from tasks.post_execution import run_analysis_on_demand
            run_analysis_on_demand(rid, atype)
        except Exception as e:
            print(f'[Analysis] on-demand error: {e}')

    spawn_background_task(_run_analysis)

    return JsonResponse({'ok': True, 'type': analysis_type})


@csrf_exempt
@require_POST
@login_required(login_url='/login/')
def api_retry_run(request, run_id):
    """Re-trigger execution for a stuck run (running/scheduled but no scripts started)."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status, suite_id FROM test_runs WHERE id = %s",
                [str(run_id)]
            )
            row = cursor.fetchone()
        if not row:
            return JsonResponse({'error': 'Run not found'}, status=404)

        run_status, suite_id = row

        if run_status not in ('running', 'scheduled', 'failed'):
            return JsonResponse({'error': f'Run is {run_status}, cannot retry'}, status=400)

        # Reset run and script statuses
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE test_runs SET status = 'running', queued_at = now(), started_at = NULL, completed_at = NULL WHERE id = %s",
                [str(run_id)]
            )
            cursor.execute(
                "UPDATE test_run_scripts SET status = 'queued', started_at = NULL, completed_at = NULL, "
                "error_message = NULL, execution_log = NULL, duration_ms = NULL "
                "WHERE run_id = %s AND status NOT IN ('passed')",
                [str(run_id)]
            )
            # Get script paths for execution
            cursor.execute(
                "SELECT script_path FROM test_run_scripts WHERE run_id = %s ORDER BY script_path",
                [str(run_id)]
            )
            script_paths = [r[0] for r in cursor.fetchall()]

        if not script_paths:
            return JsonResponse({'error': 'No scripts in this run'}, status=400)

        from core.utils import spawn_background_task
        if suite_id or len(script_paths) > 1:
            def _run_suite(rid=str(run_id)):
                try:
                    from tasks.run_tasks import execute_suite_run
                    execute_suite_run(rid)
                except Exception as e:
                    print(f'[retry_run] error: {e}')
                    from django.db import connection as conn
                    with conn.cursor() as cur:
                        cur.execute("UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
            spawn_background_task(_run_suite)
        else:
            def _run_task(rid=str(run_id), sp=script_paths[0]):
                try:
                    from tasks.run_tasks import execute_single_script
                    execute_single_script(rid, sp)
                except Exception as e:
                    print(f'[retry_run] error: {e}')
                    from django.db import connection as conn
                    with conn.cursor() as cur:
                        cur.execute("UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
                        cur.execute("UPDATE test_run_scripts SET status='error', error_message=%s, completed_at=now() WHERE run_id=%s AND status IN ('queued','running')", [str(e), rid])
            spawn_background_task(_run_task)

        return JsonResponse({'ok': True, 'scripts': len(script_paths)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
@login_required(login_url='/login/')
def api_cancel_run(request, run_id):
    """Cancel a running or scheduled test run."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE test_runs SET status = 'cancelled', completed_at = now() WHERE id = %s AND status IN ('running', 'scheduled')",
                [str(run_id)]
            )
            if cursor.rowcount == 0:
                return JsonResponse({'error': 'Run not found or not in a cancellable state'}, status=400)
            # Mark any pending/running scripts as cancelled
            cursor.execute(
                "UPDATE test_run_scripts SET status = 'cancelled', completed_at = now() WHERE run_id = %s AND status IN ('pending', 'running', 'queued')",
                [str(run_id)]
            )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
@login_required(login_url='/login/')
def api_delete_run(request, run_id):
    """Delete a single run and all related data."""
    try:
        with connection.cursor() as cursor:
            # Delete in FK order to avoid constraint violations
            cursor.execute('UPDATE test_script_baselines SET source_run_id = NULL WHERE source_run_id = %s', [str(run_id)])
            cursor.execute('DELETE FROM reviews WHERE analysis_id IN (SELECT id FROM ai_analyses WHERE run_id = %s)', [str(run_id)])
            cursor.execute('DELETE FROM reviews WHERE screenshot_id IN (SELECT id FROM run_screenshots WHERE run_id = %s)', [str(run_id)])
            cursor.execute('DELETE FROM ai_analyses WHERE run_id = %s', [str(run_id)])
            cursor.execute('DELETE FROM run_screenshots WHERE run_id = %s', [str(run_id)])
            cursor.execute('DELETE FROM test_results WHERE run_id = %s', [str(run_id)])
            cursor.execute('DELETE FROM test_run_scripts WHERE run_id = %s', [str(run_id)])
            cursor.execute('DELETE FROM test_runs WHERE id = %s', [str(run_id)])
            if cursor.rowcount == 0:
                return JsonResponse({'error': 'Run not found'}, status=404)
        # Clean up archived artifacts
        archive_dir = Path(settings.SCOUT_ARCHIVE_DIR) / 'runs' / str(run_id)
        if archive_dir.exists():
            shutil.rmtree(archive_dir, ignore_errors=True)
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
@login_required(login_url='/login/')
def api_delete_runs_bulk(request):
    """Delete multiple runs by ID list."""
    try:
        data = json.loads(request.body)
        ids = data.get('ids', [])
        if not ids:
            return JsonResponse({'error': 'No IDs provided'}, status=400)
        with connection.cursor() as cursor:
            # Delete in FK order to avoid constraint violations
            cursor.execute('UPDATE test_script_baselines SET source_run_id = NULL WHERE source_run_id = ANY(%s::uuid[])', [ids])
            cursor.execute('DELETE FROM reviews WHERE analysis_id IN (SELECT id FROM ai_analyses WHERE run_id = ANY(%s::uuid[]))', [ids])
            cursor.execute('DELETE FROM reviews WHERE screenshot_id IN (SELECT id FROM run_screenshots WHERE run_id = ANY(%s::uuid[]))', [ids])
            cursor.execute('DELETE FROM ai_analyses WHERE run_id = ANY(%s::uuid[])', [ids])
            cursor.execute('DELETE FROM run_screenshots WHERE run_id = ANY(%s::uuid[])', [ids])
            cursor.execute('DELETE FROM test_results WHERE run_id = ANY(%s::uuid[])', [ids])
            cursor.execute('DELETE FROM test_run_scripts WHERE run_id = ANY(%s::uuid[])', [ids])
            cursor.execute('DELETE FROM test_runs WHERE id = ANY(%s::uuid[])', [ids])
            deleted = cursor.rowcount
        # Clean up archived artifacts
        archive_root = Path(settings.SCOUT_ARCHIVE_DIR) / 'runs'
        for rid in ids:
            archive_dir = archive_root / str(rid)
            if archive_dir.exists():
                shutil.rmtree(archive_dir, ignore_errors=True)
        return JsonResponse({'ok': True, 'deleted': deleted})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def api_run_analyses(request, run_id):
    """Return AI analysis results for a run, plus progress info."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, analysis_type, status, issues_found, issues, summary,
                   model_used, duration_ms, screenshot_name, created_at
            FROM ai_analyses WHERE run_id = %s
            ORDER BY created_at DESC
        """, [run_id])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Parse issues JSON if stored as string
    for row in rows:
        if isinstance(row.get('issues'), str):
            try:
                row['issues'] = json.loads(row['issues'])
            except Exception:
                row['issues'] = []

    # Fetch analysis progress if available
    progress = None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT value FROM ai_settings WHERE key = %s",
            [f'analysis_progress_{run_id}']
        )
        prow = cursor.fetchone()
        if prow:
            p = prow[0]
            if isinstance(p, str):
                try:
                    p = json.loads(p)
                except Exception:
                    p = None
            progress = p

    return JsonResponse({'analyses': rows, 'progress': progress}, json_dumps_params={'default': str})


@csrf_exempt
@require_POST
@login_required(login_url='/login/')
def api_rerun(request, run_id):
    """Create a duplicate run with the same config/scripts and trigger execution."""
    try:
        import uuid as _uuid

        with connection.cursor() as cursor:
            # Get original run details
            cursor.execute(
                "SELECT suite_id, environment_id, config, trigger_type, notes FROM test_runs WHERE id = %s",
                [str(run_id)]
            )
            row = cursor.fetchone()
        if not row:
            return JsonResponse({'error': 'Run not found'}, status=404)

        suite_id, environment_id, config, trigger_type, notes = row
        new_run_id = str(_uuid.uuid4())

        with connection.cursor() as cursor:
            # Create new run
            cursor.execute("""
                INSERT INTO test_runs (id, suite_id, environment_id, config, status, trigger_type, notes, queued_at)
                VALUES (%s, %s, %s, %s, 'scheduled', 'manual', %s, now())
            """, [new_run_id, suite_id, environment_id, config, notes])

            # Copy script entries from original run
            cursor.execute("""
                SELECT script_path, browser, viewport FROM test_run_scripts WHERE run_id = %s ORDER BY script_path
            """, [str(run_id)])
            scripts = cursor.fetchall()

            for sp, browser, viewport in scripts:
                cursor.execute("""
                    INSERT INTO test_run_scripts (id, run_id, script_path, status, browser, viewport)
                    VALUES (gen_random_uuid(), %s, %s, 'queued', %s, %s)
                """, [new_run_id, sp, browser, viewport])

        if not scripts:
            return JsonResponse({'error': 'No scripts in original run'}, status=400)

        script_paths = [s[0] for s in scripts]

        from core.utils import spawn_background_task
        if suite_id or len(script_paths) > 1:
            def _run_suite(rid=new_run_id):
                try:
                    from tasks.run_tasks import execute_suite_run
                    execute_suite_run(rid)
                except Exception as e:
                    print(f'[rerun] error: {e}')
                    from django.db import connection as conn
                    with conn.cursor() as cur:
                        cur.execute("UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
            spawn_background_task(_run_suite)
        else:
            def _run_task(rid=new_run_id, sp=script_paths[0]):
                try:
                    from tasks.run_tasks import execute_single_script
                    execute_single_script(rid, sp)
                except Exception as e:
                    print(f'[rerun] error: {e}')
                    from django.db import connection as conn
                    with conn.cursor() as cur:
                        cur.execute("UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s", [rid])
                        cur.execute("UPDATE test_run_scripts SET status='error', error_message=%s, completed_at=now() WHERE run_id=%s AND status IN ('queued','running')", [str(e), rid])
            spawn_background_task(_run_task)

        return JsonResponse({'ok': True, 'run_id': new_run_id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
