"""django-q2 task functions for test execution."""
import json
import shutil
import uuid
from pathlib import Path
from django.db import connection
from django.conf import settings


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


def execute_scheduled_suite(suite_id):
    """django-q scheduled task: create a run from a suite and execute it."""
    suite_id = str(suite_id)

    with connection.cursor() as cursor:
        # Fetch suite
        cursor.execute(
            'SELECT id, name, environment_id, schedule, created_by_id FROM test_suites WHERE id = %s',
            [suite_id]
        )
        row = cursor.fetchone()
    if not row:
        print(f'[Scheduled] Suite {suite_id[:8]} not found, skipping')
        return

    _sid, suite_name, environment_id, schedule, created_by_id = row
    schedule = schedule or {}
    if isinstance(schedule, str):
        try:
            schedule = json.loads(schedule)
        except Exception:
            schedule = {}

    # Check if schedule is still enabled
    if not schedule.get('enabled'):
        print(f'[Scheduled] Suite {suite_id[:8]} schedule disabled, skipping')
        return

    # Check end_date
    end_date = schedule.get('end_date')
    if end_date:
        from datetime import date
        try:
            if date.fromisoformat(end_date) < date.today():
                print(f'[Scheduled] Suite {suite_id[:8]} schedule expired ({end_date}), disabling')
                schedule['enabled'] = False
                with connection.cursor() as cursor:
                    cursor.execute(
                        'UPDATE test_suites SET schedule = %s::jsonb WHERE id = %s',
                        [json.dumps(schedule), suite_id]
                    )
                    # Remove the django-q schedule
                    dq_id = schedule.get('dq_schedule_id')
                    if dq_id:
                        try:
                            from django_q.models import Schedule as DQSchedule
                            DQSchedule.objects.filter(id=dq_id).delete()
                        except Exception:
                            pass
                return
        except (ValueError, TypeError):
            pass

    # Fetch suite scripts
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT script_path, browser, viewport FROM test_suite_scripts WHERE suite_id = %s ORDER BY added_at',
            [suite_id]
        )
        suite_entries = [{'script_path': r[0], 'browser': r[1] or 'chromium', 'viewport': r[2] or '1920x1080'} for r in cursor.fetchall()]

    if not suite_entries:
        print(f'[Scheduled] Suite {suite_id[:8]} has no scripts, skipping')
        return

    # Merge ai_config from all scripts
    ai_config = {'text_analysis': False, 'visual_analysis': False}
    script_paths_list = [e['script_path'] for e in suite_entries]
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT ai_config FROM test_scripts WHERE script_path = ANY(%s) AND ai_config IS NOT NULL',
            [script_paths_list]
        )
        for (cfg_row,) in cursor.fetchall():
            cfg = cfg_row or {}
            if isinstance(cfg, str):
                try:
                    cfg = json.loads(cfg)
                except Exception:
                    cfg = {}
            if cfg.get('text_analysis'):
                ai_config['text_analysis'] = True
            if cfg.get('visual_analysis'):
                ai_config['visual_analysis'] = True

    run_config = json.dumps({'ai_config': ai_config})

    # Create run
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO test_runs (id, status, trigger_type, suite_id, environment_id, config, notes, queued_at, created_by_id)
               VALUES (gen_random_uuid(), 'running', 'scheduled', %s, %s, %s::jsonb, %s, now(), %s) RETURNING id""",
            [suite_id, str(environment_id) if environment_id else None, run_config,
             f"Scheduled: {suite_name}", created_by_id]
        )
        run_id = cursor.fetchone()[0]
        for entry in suite_entries:
            cursor.execute(
                """INSERT INTO test_run_scripts (id, run_id, script_path, browser, viewport, status)
                   VALUES (gen_random_uuid(), %s, %s, %s, %s, 'queued')""",
                [str(run_id), entry['script_path'], entry['browser'], entry['viewport']]
            )

    print(f'[Scheduled] Created run {str(run_id)[:8]} for suite {suite_id[:8]} ({suite_name})')

    # Execute
    try:
        execute_suite_run(str(run_id))
    except Exception as e:
        print(f'[Scheduled] Execution error for run {str(run_id)[:8]}: {e}')
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE test_runs SET status='failed', completed_at=now() WHERE id=%s",
                [str(run_id)]
            )


def execute_single_script(run_id, script_path):
    """django-q task: ad-hoc single script run."""
    from executor.runner import execute_run
    execute_run(run_id, [script_path])

    # Post-execution pipeline
    _run_post_execution(run_id)


def execute_baseline_generation(run_id, script_path):
    """Run a script and promote its screenshots to baselines for the test."""
    from executor.runner import execute_run
    execute_run(run_id, [script_path])

    # Promote run screenshots to baselines
    _promote_screenshots_to_baselines(run_id, script_path)

    print(f'[RunTasks] Baseline generation complete for run {str(run_id)[:8]}')


def _promote_screenshots_to_baselines(run_id, script_path):
    """Copy run screenshots into the baselines archive and upsert DB records."""
    archive_root = Path(settings.SCOUT_ARCHIVE_DIR)
    script_stem = Path(script_path).stem

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT rs.id, rs.name, rs.file_path, rs.project_name,
                   trs.browser, trs.viewport
            FROM run_screenshots rs
            JOIN test_run_scripts trs ON trs.id = rs.run_script_id
            WHERE rs.run_id = %s
              AND rs.project_name != 'comparison'
        """, [str(run_id)])
        cols = [c[0] for c in cursor.description]
        screenshots = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if not screenshots:
        print(f'[RunTasks] No screenshots to promote for run {str(run_id)[:8]}')
        return

    baselines_dir = archive_root / 'baselines' / script_stem
    baselines_dir.mkdir(parents=True, exist_ok=True)
    promoted = 0

    for ss in screenshots:
        src = archive_root / ss['file_path']
        if not src.exists():
            continue

        dest = baselines_dir / f"{ss['name']}.png"
        shutil.copy2(str(src), str(dest))
        rel_path = str(dest.relative_to(archive_root))

        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO test_script_baselines
                    (id, script_path, name, browser, viewport, file_path, source_run_id, created_at, updated_at)
                VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, now(), now())
                ON CONFLICT (script_path, name, browser, viewport)
                DO UPDATE SET file_path = EXCLUDED.file_path,
                              source_run_id = EXCLUDED.source_run_id,
                              updated_at = now()
            """, [script_path, ss['name'], ss['browser'] or 'chromium',
                  ss['viewport'] or '1920x1080', rel_path, str(run_id)])
        promoted += 1

    print(f'[RunTasks] Promoted {promoted} screenshots to baselines for {script_path}')


def _run_post_execution(run_id):
    """Dispatch post-execution analysis, catching errors to avoid failing the run."""
    # Compare screenshots against stored baselines (skip for baseline-generation runs)
    try:
        _compare_against_baselines(run_id)
    except Exception as e:
        print(f'[RunTasks] Baseline comparison failed for run {str(run_id)[:8]}: {e}')

    try:
        from tasks.post_execution import dispatch_post_execution
        dispatch_post_execution(run_id)
    except Exception as e:
        print(f'[RunTasks] Post-execution failed for run {str(run_id)[:8]}: {e}')

    # Send email notifications after all analysis is complete
    try:
        from tasks.notifications import send_run_notifications
        send_run_notifications(run_id)
    except Exception as e:
        print(f'[RunTasks] Notification failed for run {str(run_id)[:8]}: {e}')


def _compare_against_baselines(run_id):
    """Compare run screenshots against stored script baselines, flag mismatches."""
    # Skip baseline-generation runs
    with connection.cursor() as cursor:
        cursor.execute("SELECT trigger_type FROM test_runs WHERE id = %s", [str(run_id)])
        row = cursor.fetchone()
        if row and row[0] == 'baseline':
            return

    # Get all screenshots from this run with their script/browser/viewport info
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT rs.id, rs.name, rs.file_path, rs.project_name,
                   trs.script_path, trs.browser, trs.viewport
            FROM run_screenshots rs
            JOIN test_run_scripts trs ON trs.id = rs.run_script_id
            WHERE rs.run_id = %s
              AND rs.project_name != 'comparison'
        """, [str(run_id)])
        cols = [c[0] for c in cursor.description]
        screenshots = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if not screenshots:
        return

    from tasks.post_execution import _compute_pixel_diff, _resolve_artifact_path
    archive_root = Path(settings.SCOUT_ARCHIVE_DIR)
    threshold = getattr(settings, 'BASELINE_DIFF_THRESHOLD', 0.01)
    compared = 0
    flagged = 0

    for ss in screenshots:
        # Look up matching baseline
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT file_path FROM test_script_baselines
                WHERE script_path = %s AND name = %s AND browser = %s AND viewport = %s
                LIMIT 1
            """, [ss['script_path'], ss['name'], ss['browser'] or 'chromium',
                  ss['viewport'] or '1920x1080'])
            bl_row = cursor.fetchone()

        if not bl_row:
            continue

        baseline_path = _resolve_artifact_path(bl_row[0])
        screenshot_path = _resolve_artifact_path(ss['file_path'])

        if not baseline_path.exists() or not screenshot_path.exists():
            continue

        diff_ratio = _compute_pixel_diff(baseline_path, screenshot_path, ss['id'], archive_root)
        compared += 1

        if diff_ratio > threshold:
            flagged += 1
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE run_screenshots
                    SET flagged = true, flag_notes = %s
                    WHERE id = %s
                """, [f'Baseline diff: {diff_ratio:.2%}', ss['id']])

    if compared > 0:
        print(f'[RunTasks] Baseline comparison for run {str(run_id)[:8]}: {compared} compared, {flagged} flagged')
