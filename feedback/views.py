import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/')
        if not request.user.is_staff and not getattr(request, 'is_impersonating', False):
            return HttpResponseForbidden('Admin access required.')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


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


# ─── User-facing form ───

@login_required(login_url='/login/')
def feedback_form(request):
    return render(request, 'feedback/form.html', {
        'success': request.GET.get('success'),
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_submit(request):
    try:
        data = json.loads(request.body)
        feedback_type = data.get('type', 'feedback')
        subject = (data.get('subject') or '').strip()
        message = (data.get('message') or '').strip()
        page_url = data.get('page_url') or None

        if not subject:
            return JsonResponse({'error': 'Subject is required.'}, status=400)
        if not message:
            return JsonResponse({'error': 'Message is required.'}, status=400)
        if feedback_type not in ('issue', 'suggestion', 'feedback'):
            feedback_type = 'feedback'

        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO feedback (id, user_id, feedback_type, subject, message, page_url, created_at)
                   VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, now())""",
                [request.user.id, feedback_type, subject, message, page_url]
            )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Admin views ───

@admin_required
def admin_list(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(500, max(1, int(request.GET.get('page_size', 25))))
    type_filter = request.GET.get('type', '')
    search = request.GET.get('search', '').strip()

    where = []
    params = []

    if type_filter:
        params.append(type_filter)
        where.append('f.feedback_type = %s')
    if search:
        params.append(f'%{search.lower()}%')
        params.append(f'%{search.lower()}%')
        where.append('(LOWER(f.subject) LIKE %s OR LOWER(f.message) LIKE %s)')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM feedback f {where_clause}', params
        )
        total = cursor.fetchone()[0]

        offset = (page - 1) * page_size
        cursor.execute(f"""
            SELECT f.id, f.feedback_type, f.subject, f.message, f.page_url, f.created_at,
                   u.username, u.first_name, u.last_name
            FROM feedback f
            LEFT JOIN auth_user u ON f.user_id = u.id
            {where_clause}
            ORDER BY f.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        cols = [c[0] for c in cursor.description]
        items = [dict(zip(cols, row)) for row in cursor.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    start_item = (page - 1) * page_size + 1 if total > 0 else 0
    end_item = min(page * page_size, total)

    return render(request, 'feedback/admin_list.html', {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'page_size_options': [10, 25, 50, 100],
        'type_filter': type_filter,
        'search': search,
        'total_pages': total_pages,
        'start_item': start_item,
        'end_item': end_item,
        'page_range': build_page_range(page, total_pages),
    })


@admin_required
def admin_detail(request, feedback_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT f.id, f.feedback_type, f.subject, f.message, f.page_url, f.created_at,
                   u.username, u.first_name, u.last_name, u.email
            FROM feedback f
            LEFT JOIN auth_user u ON f.user_id = u.id
            WHERE f.id = %s
        """, [str(feedback_id)])
        cols = [c[0] for c in cursor.description]
        row = cursor.fetchone()
    if not row:
        raise Http404
    item = dict(zip(cols, row))
    return render(request, 'feedback/admin_detail.html', {'item': item})


@csrf_exempt
@require_http_methods(["POST"])
@admin_required
def admin_delete(request):
    try:
        data = json.loads(request.body)
        ids = data.get('ids', [])
        if not ids:
            return JsonResponse({'error': 'No IDs provided'}, status=400)
        with connection.cursor() as cursor:
            cursor.execute(
                'DELETE FROM feedback WHERE id = ANY(%s::uuid[])', [ids]
            )
            deleted = cursor.rowcount
        return JsonResponse({'ok': True, 'deleted': deleted})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
