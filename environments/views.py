import json
import uuid
from django.shortcuts import render, redirect
from django.http import JsonResponse, Http404, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
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
def index(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT e.*,
                   (SELECT COUNT(*) FROM assessments a WHERE a.environment_id = e.id) AS assessment_count
            FROM environments e ORDER BY e.name
        """)
        cols = [c[0] for c in cursor.description]
        environments = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return render(request, 'environments/list.html', {'environments': environments})


@admin_required
def environment_new(request):
    return render(request, 'environments/edit.html', {
        'environment': None,
        'launcher_config': {'item_selectors': {}},
    })


def _parse_launcher_config(raw):
    """Parse launcher_config from DB (may be dict or JSON string)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _build_launcher_config(post):
    """Build launcher_config dict from POST data."""
    config = {}
    if post.get('launcher_selector', '').strip():
        config['launcher_selector'] = post['launcher_selector'].strip()
    if post.get('submit_selector', '').strip():
        config['submit_selector'] = post['submit_selector'].strip()
    if post.get('intro_screens', '').strip():
        try:
            config['intro_screens'] = int(post['intro_screens'])
        except ValueError:
            pass

    item_selectors = {}
    for field, key in [('item_next_button', 'next_button'),
                       ('item_finish_button', 'finish_button'),
                       ('item_close_button', 'close_button'),
                       ('item_continue_button', 'continue_button'),
                       ('item_content_frame', 'content_frame')]:
        val = post.get(field, '').strip()
        if val:
            item_selectors[key] = val

    if item_selectors:
        config['item_selectors'] = item_selectors

    # Screen navigation config (used by navigateAllScreens)
    for field in ['end_indicator', 'done_button', 'video_progress_selector']:
        val = post.get(field, '').strip()
        if val:
            config[field] = val
    if post.get('max_screens', '').strip():
        try:
            config['max_screens'] = int(post['max_screens'])
        except ValueError:
            pass

    return config


@admin_required
def environment_edit(request, env_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM environments WHERE id = %s', [env_id])
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        raise Http404
    environment = dict(zip(cols, row))
    launcher_config = _parse_launcher_config(environment.get('launcher_config'))
    # Ensure item_selectors sub-dict exists for template access
    if 'item_selectors' not in launcher_config:
        launcher_config['item_selectors'] = {}
    return render(request, 'environments/edit.html', {
        'environment': environment,
        'launcher_config': launcher_config,
    })


@admin_required
def environment_create(request):
    if request.method != 'POST':
        return redirect('/environments/new/')
    name = request.POST.get('name', '').strip()
    base_url = request.POST.get('base_url', '').strip()
    auth_type = request.POST.get('auth_type', 'password_only')
    notes = request.POST.get('notes', '') or None
    is_default = request.POST.get('is_default') == 'on'

    # Credentials
    creds = {}
    if request.POST.get('username'):
        creds['username'] = request.POST.get('username')
    if request.POST.get('password'):
        creds['password'] = request.POST.get('password')

    launcher_config = _build_launcher_config(request.POST)

    env_id = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO environments (id, name, base_url, auth_type, credentials, launcher_config, notes, is_default, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), now())""",
            [env_id, name, base_url, auth_type, json.dumps(creds), json.dumps(launcher_config), notes, is_default]
        )

    return redirect('/environments/')


@admin_required
def environment_update(request, env_id):
    if request.method != 'POST':
        return redirect(f'/environments/{env_id}/edit/')
    name = request.POST.get('name', '').strip()
    base_url = request.POST.get('base_url', '').strip()
    auth_type = request.POST.get('auth_type', 'password_only')
    notes = request.POST.get('notes', '') or None
    is_default = request.POST.get('is_default') == 'on'

    # Merge credentials with existing — don't wipe password when field is left blank
    with connection.cursor() as cursor:
        cursor.execute('SELECT credentials FROM environments WHERE id = %s', [env_id])
        row = cursor.fetchone()
    existing_creds = {}
    if row and row[0]:
        existing_creds = row[0] if isinstance(row[0], dict) else json.loads(row[0]) if isinstance(row[0], str) else {}

    creds = dict(existing_creds)
    if request.POST.get('username'):
        creds['username'] = request.POST.get('username')
    if request.POST.get('password'):
        creds['password'] = request.POST.get('password')

    launcher_config = _build_launcher_config(request.POST)

    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE environments SET name=%s, base_url=%s, auth_type=%s, credentials=%s,
               launcher_config=%s, notes=%s, is_default=%s, updated_at=now() WHERE id=%s""",
            [name, base_url, auth_type, json.dumps(creds), json.dumps(launcher_config), notes, is_default, env_id]
        )
    return redirect('/environments/')


@admin_required
def environment_delete(request, env_id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM environments WHERE id = %s', [env_id])
    return redirect('/environments/')
