import json
import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import connection
from core.mixins import get_user_env_ids

# ── Recording session state (one at a time) ──
_record_lock = threading.Lock()
_recording_session = {}  # {session_id, process, output_file, started_at, base_url, last_code, status}


@login_required(login_url='/login/')
def builder_view(request):
    file_content = None
    file_path = None
    filename = None
    script_meta = None
    run_history = []
    assessment = None
    items = []
    assessments = []
    environments = []

    tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)

    if request.GET.get('file'):
        file_path = request.GET['file']
        full_path = (tests_dir / file_path).resolve()
        if str(full_path).startswith(str(tests_dir)) and full_path.exists():
            file_content = full_path.read_text(encoding='utf-8')
            filename = full_path.name

        # Load script metadata
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT ts.*, i.title AS item_title, i.numeric_id AS item_numeric_id,
                              a.name AS assessment_name, e.name AS environment_name
                       FROM test_scripts ts
                       LEFT JOIN items i ON ts.item_id = i.item_id
                       LEFT JOIN assessments a ON ts.assessment_id = a.id
                       LEFT JOIN environments e ON ts.environment_id = e.id
                       WHERE ts.script_path = %s""",
                    [file_path]
                )
                cols = [c[0] for c in cursor.description]
                row = cursor.fetchone()
                if row:
                    script_meta = dict(zip(cols, row))
        except Exception:
            pass

        # Load run history
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT trs.id, trs.run_id, trs.status, trs.duration_ms, trs.error_message,
                              trs.completed_at, trs.trace_path, trs.video_path,
                              r.trigger_type, s.name AS suite_name
                       FROM test_run_scripts trs
                       JOIN test_runs r ON r.id = trs.run_id
                       LEFT JOIN test_suites s ON r.suite_id = s.id
                       WHERE trs.script_path = %s
                       ORDER BY trs.completed_at DESC NULLS LAST LIMIT 50""",
                    [file_path]
                )
                cols = [c[0] for c in cursor.description]
                run_history = [dict(zip(cols, r)) for r in cursor.fetchall()]
        except Exception:
            pass

    # Load assessment info
    assessment_id = request.GET.get('assessment') or (script_meta and script_meta.get('assessment_id'))
    if assessment_id:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT a.id, a.name, a.subject, a.grade, e.name AS env_name
                       FROM assessments a LEFT JOIN environments e ON a.environment_id = e.id
                       WHERE a.id = %s""",
                    [assessment_id]
                )
                cols = [c[0] for c in cursor.description]
                row = cursor.fetchone()
                if row:
                    assessment = dict(zip(cols, row))
        except Exception:
            pass

    # Load items and assessments for dropdowns
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT numeric_id, item_id, title FROM items ORDER BY numeric_id')
            cols = [c[0] for c in cursor.description]
            items = [dict(zip(cols, r)) for r in cursor.fetchall()]
            cursor.execute('SELECT id, name FROM assessments ORDER BY name')
            cols = [c[0] for c in cursor.description]
            assessments = [dict(zip(cols, r)) for r in cursor.fetchall()]
    except Exception:
        pass

    # Load environments for the user (RBAC-scoped)
    env_ids = get_user_env_ids(request.user)
    try:
        with connection.cursor() as cursor:
            if env_ids is None:
                cursor.execute('SELECT id, name FROM environments ORDER BY name')
            else:
                cursor.execute(
                    'SELECT id, name FROM environments WHERE id = ANY(%s::uuid[]) ORDER BY name',
                    [tuple(str(e) for e in env_ids)]
                )
            environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]
    except Exception:
        pass

    return render(request, 'builder/builder.html', {
        'file_content': file_content,
        'file_path': file_path,
        'filename': filename,
        'script_meta': script_meta,
        'run_history': run_history,
        'assessment': assessment,
        'items': items,
        'assessments': assessments,
        'environments': environments,
        'test_type': request.GET.get('type'),
        'baseline_version': request.GET.get('baseline'),
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_chat(request):
    try:
        data = json.loads(request.body)
        message = data.get('message')
        if not message:
            return JsonResponse({'error': 'Message is required'}, status=400)
        from builder.chat_manager import chat
        result = chat(
            message,
            data.get('conversationId'),
            data.get('currentCode', ''),
            data.get('filename', ''),
        )
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': str(e), 'conversationId': data.get('conversationId')})


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_save(request):
    try:
        data = json.loads(request.body)
        code = data.get('code')
        environment_id = data.get('environment_id')
        if not code:
            return JsonResponse({'error': 'No code to save'}, status=400)
        tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR) / 'generated'
        tests_dir.mkdir(parents=True, exist_ok=True)
        filename = f'generated-{int(time.time())}.spec.js'
        filepath = tests_dir / filename
        filepath.write_text(code, encoding='utf-8')
        # Register in DB with environment
        rel_path = f'generated/{filename}'
        with connection.cursor() as cursor:
            if environment_id:
                cursor.execute(
                    """INSERT INTO test_scripts (script_path, environment_id, test_type, tags, created_at, updated_at)
                       VALUES (%s, %s::uuid, 'functional', '[]'::jsonb, now(), now())
                       ON CONFLICT (script_path) DO UPDATE SET updated_at = now()""",
                    [rel_path, environment_id]
                )
            else:
                cursor.execute(
                    """INSERT INTO test_scripts (script_path, test_type, tags, created_at, updated_at)
                       VALUES (%s, 'functional', '[]'::jsonb, now(), now())
                       ON CONFLICT (script_path) DO UPDATE SET updated_at = now()""",
                    [rel_path]
                )
        return JsonResponse({'path': rel_path})
    except Exception as e:
        return JsonResponse({'error': str(e)})


# ── Recording API endpoints ──

@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_record_start(request):
    global _recording_session
    try:
        data = json.loads(request.body)
        environment_id = data.get('environment_id')
        if not environment_id:
            return JsonResponse({'error': 'environment_id is required'}, status=400)

        # RBAC check
        env_ids = get_user_env_ids(request.user)
        if env_ids is not None and environment_id not in [str(e) for e in env_ids]:
            return JsonResponse({'error': 'Access denied to this environment'}, status=403)

        # Look up base_url from environments table
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT base_url FROM environments WHERE id = %s::uuid',
                [environment_id]
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return JsonResponse({'error': 'Environment has no base_url configured'}, status=400)
            base_url = row[0]

        with _record_lock:
            if _recording_session.get('status') == 'recording':
                return JsonResponse({'error': 'Another recording is already active'}, status=409)

            session_id = str(uuid.uuid4())
            fd, output_file = tempfile.mkstemp(suffix='.spec.js')
            os.close(fd)

            tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
            cmd = [
                'npx', 'playwright', 'codegen',
                base_url,
                '--output', output_file,
                '--target', 'playwright-test',
            ]

            proc = subprocess.Popen(
                cmd,
                cwd=str(tests_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            _recording_session = {
                'session_id': session_id,
                'process': proc,
                'output_file': output_file,
                'started_at': time.time(),
                'base_url': base_url,
                'last_code': '',
                'status': 'recording',
            }

            # Daemon thread that waits for the process to exit naturally
            def _wait_for_exit():
                global _recording_session
                proc.wait()
                with _record_lock:
                    if _recording_session.get('session_id') == session_id:
                        _recording_session['status'] = 'stopped'

            t = threading.Thread(target=_wait_for_exit, daemon=True)
            t.start()

        return JsonResponse({
            'session_id': session_id,
            'status': 'recording',
            'base_url': base_url,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def api_record_status(request):
    with _record_lock:
        if not _recording_session:
            return JsonResponse({'active': False, 'status': 'idle'})

        session = _recording_session
        output_file = session.get('output_file', '')
        code = ''
        try:
            if output_file and os.path.exists(output_file):
                code = open(output_file, 'r', encoding='utf-8').read()
        except Exception:
            pass

        changed = code != session.get('last_code', '')
        if changed:
            session['last_code'] = code

        proc = session.get('process')
        if proc and proc.poll() is not None:
            session['status'] = 'stopped'

        elapsed = time.time() - session.get('started_at', time.time())

        return JsonResponse({
            'active': session['status'] == 'recording',
            'status': session['status'],
            'code': code,
            'changed': changed,
            'elapsed_seconds': round(elapsed, 1),
        })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_record_stop(request):
    global _recording_session
    with _record_lock:
        if not _recording_session or _recording_session.get('status') not in ('recording', 'stopped'):
            return JsonResponse({'ok': True, 'code': ''})

        session = _recording_session
        proc = session.get('process')
        code = ''

        # Terminate the process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        # Read final code
        output_file = session.get('output_file', '')
        try:
            if output_file and os.path.exists(output_file):
                code = open(output_file, 'r', encoding='utf-8').read()
        except Exception:
            pass

        # Cleanup temp file
        try:
            if output_file and os.path.exists(output_file):
                os.unlink(output_file)
        except Exception:
            pass

        _recording_session = {}

    return JsonResponse({'ok': True, 'code': code})
