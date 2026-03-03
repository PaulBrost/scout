"""django-q2 task functions for test execution."""
import json
from django.db import connection


def execute_suite_run(run_id):
    """django-q task: runs all scripts in a run, updates DB."""
    from executor.runner import execute_run

    # Fetch script paths for this run
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT script_path FROM test_run_scripts WHERE run_id = %s ORDER BY script_path',
            [run_id]
        )
        script_paths = [row[0] for row in cursor.fetchall()]

    if not script_paths:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE test_runs SET status = 'failed', completed_at = now() WHERE id = %s",
                [run_id]
            )
        return

    execute_run(run_id, script_paths)

    # Post-execution pipeline
    _run_post_execution(run_id)


def execute_single_script(run_id, script_path):
    """django-q task: ad-hoc single script run."""
    from executor.runner import execute_run
    execute_run(run_id, [script_path])

    # Post-execution pipeline
    _run_post_execution(run_id)


def _run_post_execution(run_id):
    """Dispatch post-execution analysis, catching errors to avoid failing the run."""
    try:
        from tasks.post_execution import dispatch_post_execution
        dispatch_post_execution(run_id)
    except Exception as e:
        print(f'[RunTasks] Post-execution failed for run {str(run_id)[:8]}: {e}')
