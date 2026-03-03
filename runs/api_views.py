from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from core.models import TestRun


@login_required(login_url='/login/')
def runs_list(request):
    runs = list(
        TestRun.objects.values('id', 'status', 'trigger_type', 'started_at', 'completed_at', 'summary')
        .order_by('-started_at')[:20]
    )
    # Serialize UUIDs and datetimes
    for r in runs:
        r['id'] = str(r['id'])
        if r['started_at']:
            r['started_at'] = r['started_at'].isoformat()
        if r['completed_at']:
            r['completed_at'] = r['completed_at'].isoformat()
    return JsonResponse({'runs': runs})


@login_required(login_url='/login/')
def run_detail(request, run_id):
    try:
        run = TestRun.objects.get(pk=run_id)
    except TestRun.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    data = {
        'id': str(run.id),
        'status': run.status,
        'trigger_type': run.trigger_type,
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'summary': run.summary,
        'config': run.config,
    }
    return JsonResponse(data)
