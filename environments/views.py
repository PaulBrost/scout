import json
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
    return render(request, 'environments/edit.html', {'environment': None})


@admin_required
def environment_edit(request, env_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT * FROM environments WHERE id = %s', [env_id])
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        raise Http404
    environment = dict(zip(cols, row))
    return render(request, 'environments/edit.html', {'environment': environment})


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

    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO environments (name, base_url, auth_type, credentials, notes, is_default)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            [name, base_url, auth_type, json.dumps(creds), notes, is_default]
        )
        env_id = cursor.fetchone()[0]

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

    creds = {}
    if request.POST.get('username'):
        creds['username'] = request.POST.get('username')
    if request.POST.get('password'):
        creds['password'] = request.POST.get('password')

    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE environments SET name=%s, base_url=%s, auth_type=%s, credentials=%s,
               notes=%s, is_default=%s, updated_at=now() WHERE id=%s""",
            [name, base_url, auth_type, json.dumps(creds), notes, is_default, env_id]
        )
    return redirect('/environments/')


@admin_required
def environment_delete(request, env_id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM environments WHERE id = %s', [env_id])
    return redirect('/environments/')
