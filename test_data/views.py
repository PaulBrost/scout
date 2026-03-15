import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection
from core.mixins import get_user_env_ids


@login_required(login_url='/login/')
def index(request):
    env_filter = request.GET.get('environment', '')
    type_filter = request.GET.get('data_type', '')

    where = []
    params = []

    # RBAC scoping
    env_ids = get_user_env_ids(request.user)
    if env_ids is not None:
        if not env_ids:
            return render(request, 'test_data/list.html', {
                'datasets': [], 'environments': [],
                'env_filter': env_filter, 'type_filter': type_filter,
            })
        params.append(tuple(str(e) for e in env_ids))
        where.append('td.environment_id = ANY(%s::uuid[])')

    if env_filter:
        params.append(env_filter)
        where.append('td.environment_id = %s::uuid')

    if type_filter:
        params.append(type_filter)
        where.append('td.data_type = %s')

    where_clause = 'WHERE ' + ' AND '.join(where) if where else ''

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT td.id, td.name, td.data_type, td.description,
                   td.created_at, td.updated_at,
                   td.environment_id, e.name AS environment_name,
                   td.assessment_id, a.name AS assessment_name,
                   td.item_id, i.title AS item_title,
                   jsonb_array_length(CASE WHEN jsonb_typeof(td.data) = 'array' THEN td.data ELSE '[]'::jsonb END) AS entry_count
            FROM test_data_sets td
            LEFT JOIN environments e ON td.environment_id = e.id
            LEFT JOIN assessments a ON td.assessment_id = a.id
            LEFT JOIN items i ON td.item_id = i.item_id
            {where_clause}
            ORDER BY td.name
        """, params)
        cols = [c[0] for c in cursor.description]
        datasets = [dict(zip(cols, row)) for row in cursor.fetchall()]

    # Environments for filter
    env_query = 'SELECT id, name FROM environments ORDER BY name'
    env_params = []
    if env_ids is not None:
        env_query = 'SELECT id, name FROM environments WHERE id = ANY(%s::uuid[]) ORDER BY name'
        env_params = [tuple(str(e) for e in env_ids)]
    with connection.cursor() as cursor:
        cursor.execute(env_query, env_params)
        environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]

    return render(request, 'test_data/list.html', {
        'datasets': datasets,
        'environments': environments,
        'env_filter': env_filter,
        'type_filter': type_filter,
    })


@login_required(login_url='/login/')
def detail(request, dataset_id=None):
    dataset = None
    if dataset_id:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT td.*, e.name AS environment_name, a.name AS assessment_name,
                       i.title AS item_title
                FROM test_data_sets td
                LEFT JOIN environments e ON td.environment_id = e.id
                LEFT JOIN assessments a ON td.assessment_id = a.id
                LEFT JOIN items i ON td.item_id = i.item_id
                WHERE td.id = %s
            """, [str(dataset_id)])
            cols = [c[0] for c in cursor.description]
            row = cursor.fetchone()
        if not row:
            raise Http404
        dataset = dict(zip(cols, row))
        # Ensure data is serializable
        if isinstance(dataset.get('data'), str):
            try:
                dataset['data'] = json.loads(dataset['data'])
            except Exception:
                dataset['data'] = []

    # Load environments for form (RBAC scoped)
    env_ids = get_user_env_ids(request.user)
    with connection.cursor() as cursor:
        if env_ids is None:
            cursor.execute('SELECT id, name FROM environments ORDER BY name')
        else:
            cursor.execute(
                'SELECT id, name FROM environments WHERE id = ANY(%s::uuid[]) ORDER BY name',
                [tuple(str(e) for e in env_ids)]
            )
        environments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]

    # Load assessments and items for current dataset's environment (edit mode)
    assessments = []
    items = []
    if dataset and dataset.get('environment_id'):
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT id, name FROM assessments WHERE environment_id = %s ORDER BY name',
                [str(dataset['environment_id'])]
            )
            assessments = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]

            if dataset.get('assessment_id'):
                cursor.execute(
                    'SELECT item_id, title FROM items WHERE assessment_id = %s ORDER BY position, item_id',
                    [str(dataset['assessment_id'])]
                )
                items = [{'item_id': r[0], 'title': r[1]} for r in cursor.fetchall()]

    return render(request, 'test_data/detail.html', {
        'dataset': dataset,
        'environments': environments,
        'assessments': assessments,
        'items': items,
        'data_json': json.dumps(dataset['data'], indent=2) if dataset else '[]',
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required(login_url='/login/')
def api_save(request, dataset_id=None):
    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required'}, status=400)

        environment_id = data.get('environment_id')
        if not environment_id:
            return JsonResponse({'error': 'Environment is required'}, status=400)

        assessment_id = data.get('assessment_id') or None
        item_id = data.get('item_id') or None
        data_type = data.get('data_type', 'custom')
        description = data.get('description') or None
        entries = data.get('data', [])

        # Validate JSON data
        if not isinstance(entries, list):
            return JsonResponse({'error': 'Data must be a JSON array'}, status=400)

        with connection.cursor() as cursor:
            if dataset_id:
                cursor.execute("""
                    UPDATE test_data_sets
                    SET name = %s, environment_id = %s, assessment_id = %s,
                        item_id = %s, data_type = %s, description = %s,
                        data = %s, updated_at = now()
                    WHERE id = %s
                """, [name, environment_id, assessment_id, item_id,
                      data_type, description, json.dumps(entries), str(dataset_id)])
                return JsonResponse({'ok': True, 'id': str(dataset_id)})
            else:
                cursor.execute("""
                    INSERT INTO test_data_sets (name, environment_id, assessment_id,
                                                item_id, data_type, description, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, [name, environment_id, assessment_id, item_id,
                      data_type, description, json.dumps(entries)])
                new_id = cursor.fetchone()[0]
                return JsonResponse({'ok': True, 'id': str(new_id),
                                     'redirect': f'/test-data/{new_id}/'})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in data field'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
@login_required(login_url='/login/')
def api_delete(request, dataset_id):
    try:
        with connection.cursor() as cursor:
            # Also clean up junction table references
            cursor.execute('DELETE FROM test_script_data_sets WHERE data_set_id = %s', [str(dataset_id)])
            cursor.execute('DELETE FROM test_data_sets WHERE id = %s', [str(dataset_id)])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='/login/')
def api_assessments(request):
    """Return assessments for a given environment."""
    env_id = request.GET.get('environment_id', '')
    if not env_id:
        return JsonResponse({'assessments': []})
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT id, name FROM assessments WHERE environment_id = %s ORDER BY name',
            [env_id]
        )
        rows = [{'id': str(r[0]), 'name': r[1]} for r in cursor.fetchall()]
    return JsonResponse({'assessments': rows})


@login_required(login_url='/login/')
def api_items(request):
    """Return items for a given assessment."""
    assessment_id = request.GET.get('assessment_id', '')
    if not assessment_id:
        return JsonResponse({'items': []})
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT item_id, title FROM items WHERE assessment_id = %s ORDER BY position, item_id',
            [assessment_id]
        )
        rows = [{'item_id': r[0], 'title': r[1]} for r in cursor.fetchall()]
    return JsonResponse({'items': rows})
