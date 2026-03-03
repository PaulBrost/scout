import json
from pathlib import Path
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import connection


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
                              a.name AS assessment_name
                       FROM test_scripts ts
                       LEFT JOIN items i ON ts.item_id = i.item_id
                       LEFT JOIN assessments a ON ts.assessment_id = a.id
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

    return render(request, 'builder/builder.html', {
        'file_content': file_content,
        'file_path': file_path,
        'filename': filename,
        'script_meta': script_meta,
        'run_history': run_history,
        'assessment': assessment,
        'items': items,
        'assessments': assessments,
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
        if not code:
            return JsonResponse({'error': 'No code to save'}, status=400)
        tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR) / 'generated'
        tests_dir.mkdir(parents=True, exist_ok=True)
        import time
        filename = f'generated-{int(time.time())}.spec.js'
        filepath = tests_dir / filename
        filepath.write_text(code, encoding='utf-8')
        # Register in DB
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO test_scripts (script_path) VALUES (%s) ON CONFLICT (script_path) DO UPDATE SET updated_at = now()',
                [f'generated/{filename}']
            )
        return JsonResponse({'path': f'generated/{filename}'})
    except Exception as e:
        return JsonResponse({'error': str(e)})
