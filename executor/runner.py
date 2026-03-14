"""SCOUT — Playwright Execution Engine
Spawns Playwright test processes, captures output, parses results.
"""
import os
import shutil
import subprocess
import json
import time
import tempfile
import re
from pathlib import Path
from django.conf import settings
from django.db import connection


def archive_artifacts(run_id, script_path, snapshots, trace_path, video_path):
    """Copy screenshots, trace, and video to persistent archive.
    Returns (archived_snapshots, archived_trace, archived_video) with paths
    relative to SCOUT_ARCHIVE_DIR.
    """
    archive_root = Path(settings.SCOUT_ARCHIVE_DIR)
    pw_root = Path(settings.PLAYWRIGHT_PROJECT_ROOT)
    script_stem = Path(script_path).stem

    dest_dir = archive_root / 'runs' / str(run_id) / script_stem
    dest_dir.mkdir(parents=True, exist_ok=True)

    archived_snapshots = []
    for snap in snapshots:
        src = pw_root / snap['file_path']
        if not src.exists():
            archived_snapshots.append(snap)
            continue
        dest_file = dest_dir / src.name
        if dest_file.exists():
            base, ext = dest_file.stem, dest_file.suffix
            counter = 1
            while dest_file.exists():
                dest_file = dest_dir / f'{base}_{counter}{ext}'
                counter += 1
        shutil.copy2(str(src), str(dest_file))
        archived_snapshots.append({
            **snap,
            'file_path': str(dest_file.relative_to(archive_root)),
        })

    archived_trace = None
    if trace_path:
        src = pw_root / trace_path
        if src.exists():
            dest_file = dest_dir / src.name
            shutil.copy2(str(src), str(dest_file))
            archived_trace = str(dest_file.relative_to(archive_root))
        else:
            archived_trace = trace_path

    archived_video = None
    if video_path:
        src = pw_root / video_path
        if src.exists():
            dest_file = dest_dir / src.name
            shutil.copy2(str(src), str(dest_file))
            archived_video = str(dest_file.relative_to(archive_root))
        else:
            archived_video = video_path

    return archived_snapshots, archived_trace, archived_video


def find_artifacts(script_path):
    """Scan test-results/ for trace and video artifacts."""
    results_dir = Path(settings.PLAYWRIGHT_PROJECT_ROOT) / 'test-results'
    trace_path = None
    video_path = None

    try:
        if not results_dir.exists():
            return trace_path, video_path

        basename = Path(script_path).stem.replace('.', '-')
        for entry in results_dir.iterdir():
            if not entry.is_dir():
                continue
            if not entry.name.lower().startswith(basename.lower()):
                continue
            for f in entry.iterdir():
                if not trace_path and f.name == 'trace.zip':
                    trace_path = f'test-results/{entry.name}/trace.zip'
                if not video_path and f.suffix in ('.webm', '.mp4'):
                    video_path = f'test-results/{entry.name}/{f.name}'
    except Exception:
        pass

    return trace_path, video_path


def find_snapshots(script_path, pre_existing_pngs=None):
    """Scan -snapshots/ dir AND test-results/ for captured screenshot PNGs.
    pre_existing_pngs: dict of {Path: mtime} that existed before the script ran.
    Returns list of dicts: [{name, file_path, project_name}, ...]
    """
    pw_root = Path(settings.PLAYWRIGHT_PROJECT_ROOT)
    tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
    spec_file = tests_dir / script_path
    snapshots_dir = spec_file.parent / f'{spec_file.name}-snapshots'
    results = []

    # 1) Scan the per-spec -snapshots/ directory (Playwright baselines)
    try:
        if snapshots_dir.exists():
            for f in sorted(snapshots_dir.iterdir()):
                if f.suffix.lower() != '.png':
                    continue
                stem = f.stem
                project_name = 'unknown'
                name = stem
                for proj in ('chrome-desktop', 'firefox-desktop', 'chromebook', 'edge-desktop', 'webkit-desktop'):
                    idx = stem.find(f'-{proj}')
                    if idx != -1:
                        name = stem[:idx]
                        project_name = proj
                        break
                rel_path = str(f.relative_to(pw_root))
                results.append({'name': name, 'file_path': rel_path, 'project_name': project_name})
    except Exception:
        pass

    # 2) Scan test-results/ for new or modified PNGs from this run
    if pre_existing_pngs is not None:
        results_dir = pw_root / 'test-results'
        try:
            if results_dir.exists():
                for f in sorted(results_dir.rglob('*.png')):
                    # Skip files that existed before and weren't modified
                    if f in pre_existing_pngs and f.stat().st_mtime == pre_existing_pngs[f]:
                        continue
                    stem = f.stem
                    # Classify by suffix pattern: *-diff, *-actual, or plain
                    category = ''
                    name = stem
                    if stem.endswith('-diff'):
                        category = 'diff'
                        name = stem[:-5]
                    elif stem.endswith('-actual'):
                        category = 'actual'
                        name = stem[:-7]
                    display_name = f'{name} ({category})' if category else name
                    rel_path = str(f.relative_to(pw_root))
                    results.append({'name': display_name, 'file_path': rel_path, 'project_name': 'comparison'})
        except Exception:
            pass

    return results


def extract_error_message(stdout, stderr, json_report):
    """Extract a meaningful error from Playwright output."""
    if json_report and json_report.get('suites'):
        errors = []

        def walk_suites(suites):
            for suite in suites:
                for spec in suite.get('specs', []):
                    for test in spec.get('tests', []):
                        for result in test.get('results', []):
                            if result.get('status') in ('failed', 'timedOut'):
                                msg = (result.get('error') or {}).get('message', '')
                                if msg:
                                    errors.append(f"{spec['title']}: {msg.split(chr(10))[0]}")
                walk_suites(suite.get('suites', []))

        walk_suites(json_report['suites'])
        if errors:
            return '; '.join(errors)[:500]

    # Fallback: extract from stdout
    error_lines = []
    capturing = False
    for line in stdout.split('\n'):
        if re.search(r'Error:|AssertionError:|TimeoutError:|expect\(', line):
            capturing = True
        if capturing:
            error_lines.append(line.strip())
            if len(error_lines) >= 5:
                break
    if error_lines:
        return '\n'.join(error_lines)[:500]

    if stderr.strip():
        return stderr.strip().split('\n')[0][:500]

    return 'Test failed (see execution log for details)'


def classify_failures(json_report):
    """Analyze Playwright JSON report to separate screenshot comparison failures from other failures.

    Returns (screenshot_mismatches: list[str], other_failures: list[str]).
    screenshot_mismatches contains the names of screenshots that didn't match.
    other_failures contains descriptions of non-screenshot errors.
    """
    screenshot_mismatches = []
    other_failures = []

    if not json_report or not json_report.get('suites'):
        return screenshot_mismatches, other_failures

    def walk_suites(suites):
        for suite in suites:
            for spec in suite.get('specs', []):
                for test_entry in spec.get('tests', []):
                    for result in test_entry.get('results', []):
                        if result.get('status') not in ('failed', 'timedOut'):
                            continue
                        for error in (result.get('errors') or [result.get('error')] if result.get('error') else []):
                            if not error:
                                continue
                            msg = error.get('message', '') if isinstance(error, dict) else str(error)
                            if 'toHaveScreenshot' in msg or 'Screenshot comparison' in msg:
                                # Extract screenshot name from the call
                                m = re.search(r'toHaveScreenshot\(["\']([^"\']+)', msg)
                                screenshot_mismatches.append(m.group(1) if m else spec.get('title', 'unknown'))
                            else:
                                other_failures.append(msg.split('\n')[0][:200])
                        if result.get('status') == 'timedOut' and not result.get('errors') and not result.get('error'):
                            other_failures.append('Test timed out')
            walk_suites(suite.get('suites', []))

    walk_suites(json_report['suites'])
    return screenshot_mismatches, other_failures


BROWSER_TO_PROJECT = {
    'chromium': 'chrome-desktop',
    'firefox': 'firefox-desktop',
    'webkit': 'webkit-desktop',
}


def execute_script(script_path, project='', timeout=None, env_vars=None, headed=False, viewport=None):
    """Execute a single Playwright test script."""
    if timeout is None:
        timeout = settings.SCOUT_SCRIPT_TIMEOUT / 1000  # convert ms to seconds

    tests_dir = Path(settings.PLAYWRIGHT_TESTS_DIR)
    project_root = Path(settings.PLAYWRIGHT_PROJECT_ROOT)
    full_path = tests_dir / script_path

    if not full_path.exists():
        return {
            'status': 'error',
            'duration_ms': 0,
            'error_message': f'Script not found: {full_path}',
            'execution_log': f'Error: Script file does not exist at {full_path}',
            'json_report': None,
            'trace_path': None,
            'video_path': None,
        }

    # Clear cached session state so tests always start from login/form selection,
    # not from a resumed page.  This is critical for environments like NAEP Gates
    # (which resumes mid-assessment) and PIAAC (which needs filter selection).
    session_file = project_root / 'auth' / 'session.json'
    if session_file.exists():
        try:
            session_file.unlink()
        except OSError:
            pass

    results_dir = project_root / 'test-results'

    # Wipe test-results clean before each run — artifacts are archived to
    # persistent storage after execution, so this is safe scratch space.
    if results_dir.exists():
        shutil.rmtree(results_dir, ignore_errors=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    pre_existing_pngs = {}

    json_file = results_dir / f'run-{int(time.time())}-{os.urandom(3).hex()}.json'

    args = ['npx', 'playwright', 'test', str(full_path), '--reporter=list,json', '--retries=0']
    if headed:
        args.append('--headed')
        # Default to single project so only one browser window opens
        if not project:
            project = 'chrome-desktop'
    if project:
        args.append(f'--project={project}')

    env = os.environ.copy()
    env['PLAYWRIGHT_JSON_OUTPUT_NAME'] = str(json_file)
    env['FORCE_COLOR'] = '0'
    env['CI'] = '1'
    if viewport:
        env['SCOUT_VIEWPORT'] = viewport
    if env_vars:
        env.update(env_vars)

    start_time = time.time()
    timed_out = False

    try:
        proc = subprocess.Popen(
            args,
            cwd=str(project_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout_bytes, stderr_bytes = proc.communicate()
            exit_code = -1
            timed_out = True
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            'status': 'error',
            'duration_ms': duration_ms,
            'error_message': f'Process error: {e}',
            'execution_log': f'Failed to spawn process: {e}',
            'json_report': None,
            'trace_path': None,
            'video_path': None,
        }

    duration_ms = int((time.time() - start_time) * 1000)
    stdout = stdout_bytes.decode('utf-8', errors='replace')
    stderr = stderr_bytes.decode('utf-8', errors='replace')

    # Build execution log
    log_lines = [
        f'[0ms] Running: {" ".join(args)}',
        f'[0ms] CWD: {project_root}',
        '',
    ]
    if stdout.strip():
        log_lines += ['-- Playwright Output -----------------', stdout.strip()]
    if stderr.strip():
        log_lines += ['', '-- Stderr ----------------------------', stderr.strip()]
    log_lines += ['']
    if timed_out:
        log_lines.append(f'[{duration_ms}ms] TIMED OUT ({timeout}s limit)')
    elif exit_code == 0:
        log_lines.append(f'[{duration_ms}ms] Passed ({duration_ms / 1000:.1f}s)')
    else:
        log_lines.append(f'[{duration_ms}ms] Failed (exit code {exit_code}) ({duration_ms / 1000:.1f}s)')

    execution_log = '\n'.join(log_lines)

    # Parse JSON report
    json_report = None
    try:
        if json_file.exists():
            json_report = json.loads(json_file.read_text())
            json_file.unlink()
    except Exception:
        pass

    # Determine status
    screenshot_mismatches = []
    if timed_out:
        status = 'error'
        error_message = f'Timeout: Script exceeded {timeout}s limit'
    elif exit_code == 0:
        status = 'passed'
        error_message = None
    else:
        # Check if the only failures are screenshot comparison mismatches.
        # If so, the test execution itself succeeded — flag issues separately.
        ss_mismatches, other_failures = classify_failures(json_report)
        if ss_mismatches and not other_failures:
            status = 'passed'
            screenshot_mismatches = ss_mismatches
            error_message = None
        else:
            status = 'failed'
            error_message = extract_error_message(stdout, stderr, json_report)
            screenshot_mismatches = ss_mismatches

    trace_path, video_path = find_artifacts(script_path)
    snapshots = find_snapshots(script_path, pre_existing_pngs=pre_existing_pngs)

    return {
        'status': status,
        'duration_ms': duration_ms,
        'error_message': error_message,
        'execution_log': execution_log,
        'json_report': json_report,
        'exit_code': exit_code,
        'trace_path': trace_path,
        'video_path': video_path,
        'snapshots': snapshots,
        'screenshot_mismatches': screenshot_mismatches,
    }


def prepare_test_data(run_id, environment_id):
    """Serialize TestDataSets for the environment into a temp JSON file.
    Returns the path to the temp file, or None if no data sets exist."""
    if not environment_id:
        return None

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT name, data_type, data, assessment_id, description
            FROM test_data_sets
            WHERE environment_id = %s
            ORDER BY data_type, name
        """, [str(environment_id)])
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if not rows:
        return None

    # Organize by data_type
    test_data = {}
    for row in rows:
        dt = row['data_type']
        if dt not in test_data:
            test_data[dt] = []
        test_data[dt].append({
            'name': row['name'],
            'assessment_id': row['assessment_id'],
            'description': row['description'],
            'entries': row['data'] if isinstance(row['data'], list) else [],
        })

    # Write to temp file
    data_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.json', prefix=f'scout-data-{str(run_id)[:8]}-',
        delete=False
    )
    json.dump(test_data, data_file, default=str)
    data_file.close()
    return data_file.name


def execute_run(run_id, script_paths, options=None):
    """Execute all scripts in a run sequentially, updating DB as each completes."""
    options = options or {}
    passed = failed = errors = issues = 0

    # Prepare test data and environment config if environment is set on the run
    test_data_path = None
    env_config_json = None
    is_baseline_run = False
    with connection.cursor() as cursor:
        cursor.execute('SELECT environment_id, trigger_type FROM test_runs WHERE id = %s', [run_id])
        row = cursor.fetchone()
        if row and row[1] == 'baseline':
            is_baseline_run = True
        if row and row[0]:
            environment_id = row[0]
            test_data_path = prepare_test_data(run_id, environment_id)

            # Fetch full environment config so Playwright helpers can use it
            cursor.execute(
                'SELECT base_url, auth_type, credentials, launcher_config FROM environments WHERE id = %s',
                [str(environment_id)]
            )
            env_row = cursor.fetchone()
            if env_row:
                # Raw SQL returns JSON columns as strings; parse them
                creds = env_row[2]
                if isinstance(creds, str):
                    try:
                        creds = json.loads(creds)
                    except (json.JSONDecodeError, TypeError):
                        creds = {}
                launcher = env_row[3]
                if isinstance(launcher, str):
                    try:
                        launcher = json.loads(launcher)
                    except (json.JSONDecodeError, TypeError):
                        launcher = {}
                env_config = {
                    'base_url': env_row[0],
                    'auth_type': env_row[1],
                    'credentials': creds if isinstance(creds, dict) else {},
                    'launcher_config': launcher if isinstance(launcher, dict) else {},
                }
                env_config_json = json.dumps(env_config, default=str)

    # Mark run as actually started (execution picked up by worker)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE test_runs SET started_at = now() WHERE id = %s AND started_at IS NULL",
            [run_id]
        )

    # Fetch run_script entries (id, script_path, browser, viewport) in order
    run_script_entries = []
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT id, script_path, browser, viewport FROM test_run_scripts WHERE run_id = %s ORDER BY script_path',
            [run_id]
        )
        run_script_entries = [{'id': r[0], 'script_path': r[1], 'browser': r[2] or 'chromium', 'viewport': r[3] or '1920x1080'} for r in cursor.fetchall()]

    for entry in run_script_entries:
        # Check if run was cancelled before starting next script
        with connection.cursor() as cursor:
            cursor.execute('SELECT status FROM test_runs WHERE id = %s', [run_id])
            run_row = cursor.fetchone()
            if run_row and run_row[0] == 'cancelled':
                # Mark remaining scripts as cancelled
                cursor.execute(
                    "UPDATE test_run_scripts SET status = 'cancelled', completed_at = now() WHERE run_id = %s AND status IN ('pending', 'queued')",
                    [run_id]
                )
                print(f'[Executor] Run {str(run_id)[:8]} cancelled by user')
                if test_data_path:
                    try:
                        os.unlink(test_data_path)
                    except OSError:
                        pass
                return

        script_path = entry['script_path']
        run_script_id = entry['id']

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE test_run_scripts SET status = 'running', started_at = now() WHERE id = %s",
                [run_script_id]
            )

        try:
            env_vars = dict(options.get('env') or {})
            if test_data_path:
                env_vars['SCOUT_TEST_DATA'] = test_data_path
            if env_config_json:
                env_vars['SCOUT_ENV_CONFIG'] = env_config_json

            # Per-entry browser/viewport from test_run_scripts
            script_project = options.get('project') or BROWSER_TO_PROJECT.get(entry['browser'], 'chrome-desktop')

            result = execute_script(
                script_path,
                project=script_project,
                env_vars=env_vars if env_vars else None,
                viewport=entry['viewport'],
            )

            # Archive artifacts to persistent storage
            archived_snaps, archived_trace, archived_video = archive_artifacts(
                run_id, script_path,
                result.get('snapshots', []),
                result.get('trace_path'),
                result.get('video_path'),
            )

            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE test_run_scripts
                       SET status = %s, duration_ms = %s, error_message = %s,
                           execution_log = %s, trace_path = %s, video_path = %s, completed_at = now()
                       WHERE id = %s""",
                    [result['status'], result['duration_ms'], result['error_message'],
                     result['execution_log'], archived_trace, archived_video,
                     run_script_id]
                )

            # Save captured snapshots as RunScreenshot records (archived paths)
            # Auto-flag comparison artifacts (diff/actual from screenshot mismatches)
            # Skip auto-flagging for baseline runs — comparison diffs are expected
            ss_mismatches = result.get('screenshot_mismatches', [])
            for snap in archived_snaps:
                is_comparison = snap.get('project_name') == 'comparison' and not is_baseline_run
                with connection.cursor() as cursor:
                    cursor.execute(
                        """INSERT INTO run_screenshots (id, run_id, run_script_id, name, file_path, project_name, flagged, flag_notes, created_at)
                           VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, now())
                           ON CONFLICT DO NOTHING""",
                        [run_id, run_script_id, snap['name'], snap['file_path'], snap['project_name'],
                         is_comparison, 'Screenshot comparison mismatch' if is_comparison else None]
                    )

            script_issues = len(ss_mismatches)
            issues += script_issues

            if result['status'] == 'passed':
                passed += 1
            elif result['status'] == 'error':
                errors += 1
            else:
                failed += 1
        except Exception as e:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE test_run_scripts
                       SET status = 'error', error_message = %s, execution_log = %s, completed_at = now()
                       WHERE id = %s""",
                    [f'Execution engine error: {e}', f'Internal error: {e}', run_script_id]
                )
            errors += 1

    run_status = 'completed' if (failed + errors) == 0 else 'failed'
    summary = json.dumps({'passed': passed, 'failed': failed, 'errors': errors, 'issues': issues, 'total': len(run_script_entries)})

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE test_runs SET status = %s, completed_at = now(), summary = %s WHERE id = %s",
            [run_status, summary, run_id]
        )

    # Clean up temp test data file
    if test_data_path:
        try:
            os.unlink(test_data_path)
        except OSError:
            pass

    print(f'[Executor] Run {str(run_id)[:8]} complete: {passed} passed, {failed} failed, {errors} errors')
