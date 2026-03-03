import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.db import connection


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/')
        if not request.user.is_staff:
            return HttpResponseForbidden('Admin access required.')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


@admin_required
def ai_settings(request):
    with connection.cursor() as cursor:
        cursor.execute('SELECT key, value FROM ai_settings ORDER BY key')
        cols = [c[0] for c in cursor.description]
        settings_rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        settings_dict = {r['key']: r['value'] for r in settings_rows}

        cursor.execute('SELECT * FROM ai_tools ORDER BY category, name')
        cols = [c[0] for c in cursor.description]
        tools = [dict(zip(cols, row)) for row in cursor.fetchall()]

    return render(request, 'admin_config/ai_settings.html', {
        'settings': settings_dict,
        'tools': tools,
        'provider': settings.AI_PROVIDER,
        'success': request.GET.get('success'),
    })


@admin_required
def update_prompt(request):
    if request.method != 'POST':
        return redirect('/admin-config/ai/')
    prompt = request.POST.get('prompt', '')
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO ai_settings (key, value, updated_at) VALUES ('system_prompt', %s, now())
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
            [json.dumps(prompt)]
        )
    return redirect('/admin-config/ai/?success=prompt')


@csrf_exempt
@require_http_methods(["POST"])
@admin_required
def toggle_tool(request, tool_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute('UPDATE ai_tools SET enabled = NOT enabled WHERE id = %s', [tool_id])
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)})


@admin_required
def update_settings(request):
    if request.method != 'POST':
        return redirect('/admin-config/ai/')
    max_turns = request.POST.get('max_conversation_turns')
    tool_calling = request.POST.get('tool_calling_enabled')
    with connection.cursor() as cursor:
        if max_turns is not None:
            cursor.execute(
                """INSERT INTO ai_settings (key, value, updated_at) VALUES ('max_conversation_turns', %s, now())
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
                [json.dumps(int(max_turns) if max_turns.isdigit() else 50)]
            )
        if tool_calling is not None:
            cursor.execute(
                """INSERT INTO ai_settings (key, value, updated_at) VALUES ('tool_calling_enabled', %s, now())
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
                [json.dumps(tool_calling == 'true')]
            )
    return redirect('/admin-config/ai/?success=settings')
