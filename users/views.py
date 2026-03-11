from django.shortcuts import render, redirect
from django.http import Http404, HttpResponseForbidden
from django.db import connection
from django.contrib.auth.hashers import make_password


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/')
        if not request.user.is_staff:
            return HttpResponseForbidden('Admin access required.')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _get_all_environments(cursor):
    cursor.execute('SELECT id, name FROM environments ORDER BY name')
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def _get_user_environment_ids(cursor, user_id):
    cursor.execute(
        'SELECT environment_id FROM user_environments WHERE user_id = %s',
        [user_id],
    )
    return {str(r[0]) for r in cursor.fetchall()}


@admin_required
def index(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT u.id, u.username, u.email, u.first_name, u.last_name,
                   u.is_staff, u.is_active, u.date_joined, u.last_login,
                   (SELECT COUNT(*) FROM user_environments ue WHERE ue.user_id = u.id) AS env_count
            FROM auth_user u ORDER BY u.username
        """)
        cols = [c[0] for c in cursor.description]
        users = [dict(zip(cols, r)) for r in cursor.fetchall()]

    return render(request, 'users/list.html', {'users': users})


@admin_required
def user_new(request):
    with connection.cursor() as cursor:
        environments = _get_all_environments(cursor)
    return render(request, 'users/edit.html', {
        'edit_user': None,
        'environments': environments,
        'user_env_ids': set(),
    })


@admin_required
def user_edit(request, user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT id, username, email, first_name, last_name,
                      is_staff, is_active
               FROM auth_user WHERE id = %s""",
            [user_id],
        )
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
        if not row:
            raise Http404
        edit_user = dict(zip(cols, row))
        environments = _get_all_environments(cursor)
        user_env_ids = _get_user_environment_ids(cursor, user_id)

    return render(request, 'users/edit.html', {
        'edit_user': edit_user,
        'environments': environments,
        'user_env_ids': user_env_ids,
    })


@admin_required
def user_create(request):
    if request.method != 'POST':
        return redirect('/users/new/')

    username = request.POST.get('username', '').strip()
    email = request.POST.get('email', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    password = request.POST.get('password', '').strip()
    is_staff = request.POST.get('is_staff') == 'on'
    is_active = request.POST.get('is_active') == 'on'
    env_ids = request.POST.getlist('environments')

    if not username or not password:
        with connection.cursor() as cursor:
            environments = _get_all_environments(cursor)
        return render(request, 'users/edit.html', {
            'edit_user': None,
            'environments': environments,
            'user_env_ids': set(env_ids),
            'error': 'Username and password are required.',
        })

    hashed = make_password(password)

    with connection.cursor() as cursor:
        # Check for duplicate username
        cursor.execute('SELECT id FROM auth_user WHERE username = %s', [username])
        if cursor.fetchone():
            environments = _get_all_environments(cursor)
            return render(request, 'users/edit.html', {
                'edit_user': None,
                'environments': environments,
                'user_env_ids': set(env_ids),
                'error': f'Username "{username}" already exists.',
            })

        cursor.execute(
            """INSERT INTO auth_user
               (username, email, first_name, last_name, password,
                is_staff, is_active, is_superuser, date_joined)
               VALUES (%s, %s, %s, %s, %s, %s, %s, false, now())
               RETURNING id""",
            [username, email, first_name, last_name, hashed, is_staff, is_active],
        )
        user_id = cursor.fetchone()[0]

        # Assign environments
        for eid in env_ids:
            cursor.execute(
                'INSERT INTO user_environments (user_id, environment_id) VALUES (%s, %s)',
                [user_id, eid],
            )

    return redirect('/users/')


@admin_required
def user_update(request, user_id):
    if request.method != 'POST':
        return redirect(f'/users/{user_id}/edit/')

    username = request.POST.get('username', '').strip()
    email = request.POST.get('email', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    password = request.POST.get('password', '').strip()
    is_staff = request.POST.get('is_staff') == 'on'
    is_active = request.POST.get('is_active') == 'on'
    env_ids = request.POST.getlist('environments')

    with connection.cursor() as cursor:
        # Check the user exists
        cursor.execute('SELECT id FROM auth_user WHERE id = %s', [user_id])
        if not cursor.fetchone():
            raise Http404

        # Check for duplicate username (excluding self)
        cursor.execute(
            'SELECT id FROM auth_user WHERE username = %s AND id != %s',
            [username, user_id],
        )
        if cursor.fetchone():
            cursor.execute(
                """SELECT id, username, email, first_name, last_name,
                          is_staff, is_active
                   FROM auth_user WHERE id = %s""",
                [user_id],
            )
            cols = [c[0] for c in cursor.description]
            edit_user = dict(zip(cols, cursor.fetchone()))
            environments = _get_all_environments(cursor)
            return render(request, 'users/edit.html', {
                'edit_user': edit_user,
                'environments': environments,
                'user_env_ids': set(env_ids),
                'error': f'Username "{username}" already taken by another user.',
            })

        # Update user fields
        if password:
            hashed = make_password(password)
            cursor.execute(
                """UPDATE auth_user
                   SET username=%s, email=%s, first_name=%s, last_name=%s,
                       password=%s, is_staff=%s, is_active=%s
                   WHERE id=%s""",
                [username, email, first_name, last_name, hashed, is_staff, is_active, user_id],
            )
        else:
            cursor.execute(
                """UPDATE auth_user
                   SET username=%s, email=%s, first_name=%s, last_name=%s,
                       is_staff=%s, is_active=%s
                   WHERE id=%s""",
                [username, email, first_name, last_name, is_staff, is_active, user_id],
            )

        # Sync environment assignments: delete all, re-insert selected
        cursor.execute('DELETE FROM user_environments WHERE user_id = %s', [user_id])
        for eid in env_ids:
            cursor.execute(
                'INSERT INTO user_environments (user_id, environment_id) VALUES (%s, %s)',
                [user_id, eid],
            )

    return redirect('/users/')


@admin_required
def user_delete(request, user_id):
    if request.method == 'POST':
        # Prevent self-deletion
        if user_id == request.user.id:
            return HttpResponseForbidden('You cannot delete your own account.')
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM user_environments WHERE user_id = %s', [user_id])
            cursor.execute('DELETE FROM auth_user WHERE id = %s', [user_id])
    return redirect('/users/')
