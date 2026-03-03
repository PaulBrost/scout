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


def execute_single_script(run_id, script_path):
    """django-q task: ad-hoc single script run."""
    from executor.runner import execute_run
    execute_run(run_id, [script_path])
