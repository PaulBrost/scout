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
