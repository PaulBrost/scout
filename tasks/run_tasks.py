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

    # Read run config for options like headed mode
    options = {}
    with connection.cursor() as cursor:
        cursor.execute('SELECT config FROM test_runs WHERE id = %s', [run_id])
        row = cursor.fetchone()
        if row and row[0]:
            run_config = row[0]
            if isinstance(run_config, str):
                try:
                    run_config = json.loads(run_config)
                except (json.JSONDecodeError, TypeError):
                    run_config = {}
            if isinstance(run_config, dict) and run_config.get('headed'):
                options['headed'] = True

    execute_run(run_id, [script_path], options=options)

    # Post-execution pipeline
    _run_post_execution(run_id)


def _run_post_execution(run_id):
    """Dispatch post-execution analysis, catching errors to avoid failing the run."""
    try:
        from tasks.post_execution import dispatch_post_execution
        dispatch_post_execution(run_id)
    except Exception as e:
        print(f'[RunTasks] Post-execution failed for run {str(run_id)[:8]}: {e}')
