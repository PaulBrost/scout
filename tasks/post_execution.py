"""Post-execution pipeline — dispatches analysis handlers based on test_type."""
import json
import base64
import time
from pathlib import Path
from django.db import connection
from django.conf import settings


def dispatch_post_execution(run_id):
    """Look up test_types for scripts in this run and queue appropriate handlers."""
    with connection.cursor() as cursor:
        # Find distinct test_types for scripts in this run
        cursor.execute("""
            SELECT DISTINCT ts.test_type
            FROM test_run_scripts trs
            JOIN test_scripts ts ON ts.script_path = trs.script_path
            WHERE trs.run_id = %s
        """, [run_id])
        test_types = {row[0] for row in cursor.fetchall()}

    if not test_types:
        return

    # Dispatch handlers for each test_type
    if 'visual_regression' in test_types:
        try:
            compare_baselines(run_id)
        except Exception as e:
            print(f'[PostExec] compare_baselines error for run {str(run_id)[:8]}: {e}')

    if 'ai_content' in test_types:
        try:
            run_text_analysis(run_id)
        except Exception as e:
            print(f'[PostExec] run_text_analysis error for run {str(run_id)[:8]}: {e}')

    if 'ai_visual' in test_types:
        try:
            run_visual_analysis(run_id)
        except Exception as e:
            print(f'[PostExec] run_visual_analysis error for run {str(run_id)[:8]}: {e}')

    print(f'[PostExec] Completed post-execution for run {str(run_id)[:8]}, types: {test_types}')


def compare_baselines(run_id):
    """Compare screenshots against approved baselines for visual_regression scripts."""
    project_root = Path(settings.PLAYWRIGHT_PROJECT_ROOT)

    with connection.cursor() as cursor:
        # Get test results with screenshots for visual_regression scripts in this run
        cursor.execute("""
            SELECT tr.id, tr.item_id, tr.browser, tr.device_profile, tr.screenshot_path,
                   r.environment_id
            FROM test_results tr
            JOIN test_runs r ON r.id = tr.run_id
            WHERE tr.run_id = %s
              AND tr.screenshot_path IS NOT NULL
        """, [run_id])
        cols = [c[0] for c in cursor.description]
        results = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if not results:
        return

    for result in results:
        result_id = result['id']
        item_id = result['item_id']
        browser = result['browser']
        device_profile = result['device_profile'] or 'default'
        screenshot_path = project_root / result['screenshot_path']
        environment_id = result.get('environment_id')

        if not screenshot_path.exists():
            continue

        # Look for approved baseline
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, screenshot_path
                FROM baselines
                WHERE item_id = %s AND browser = %s AND device_profile = %s
                  AND approved_at IS NOT NULL
                ORDER BY approved_at DESC
                LIMIT 1
            """, [item_id, browser, device_profile])
            baseline_row = cursor.fetchone()

        if baseline_row:
            baseline_id, baseline_screenshot = baseline_row
            baseline_path = project_root / baseline_screenshot

            if baseline_path.exists():
                diff_ratio = _compute_pixel_diff(baseline_path, screenshot_path, result_id, project_root)

                with connection.cursor() as cursor:
                    diff_file = f'test-results/diffs/{result_id}.png'
                    cursor.execute("""
                        UPDATE test_results SET diff_ratio = %s, diff_path = %s
                        WHERE id = %s
                    """, [diff_ratio, diff_file, result_id])

                # If diff exceeds threshold, create analysis + review
                threshold = getattr(settings, 'BASELINE_DIFF_THRESHOLD', 0.01)
                if diff_ratio > threshold:
                    _create_analysis_and_review(
                        run_id, item_id, result_id,
                        'screenshot_diff',
                        [{'type': 'visual_diff', 'severity': 'high',
                          'message': f'Screenshot differs from baseline by {diff_ratio:.2%}',
                          'diff_ratio': diff_ratio}]
                    )
        else:
            # No approved baseline — create a pending baseline from this screenshot
            _create_pending_baseline(
                item_id, browser, device_profile,
                result['screenshot_path'], environment_id
            )


def run_text_analysis(run_id):
    """Run AI text content analysis on test results for ai_content scripts."""
    from ai.provider import get_provider_for_feature

    with connection.cursor() as cursor:
        # Get results for ai_content scripts
        cursor.execute("""
            SELECT tr.id, tr.item_id, trs.execution_log
            FROM test_results tr
            JOIN test_run_scripts trs ON trs.run_id = tr.run_id AND trs.script_path IN (
                SELECT ts.script_path FROM test_scripts ts WHERE ts.test_type = 'ai_content'
            )
            WHERE tr.run_id = %s
        """, [run_id])
        cols = [c[0] for c in cursor.description]
        results = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if not results:
        return

    provider = get_provider_for_feature('text')

    for result in results:
        text = result.get('execution_log') or ''
        if not text.strip():
            continue

        start = time.time()
        try:
            analysis = provider.analyze_text(text)
            duration_ms = int((time.time() - start) * 1000)
            issues = analysis.get('issues', [])

            _create_analysis_and_review(
                run_id, result['item_id'], result['id'],
                'text_content', issues,
                raw_response=analysis.get('raw', ''),
                model_used=analysis.get('model', ''),
                duration_ms=duration_ms,
            )
        except Exception as e:
            print(f'[PostExec] Text analysis failed for result {result["id"]}: {e}')


def run_visual_analysis(run_id):
    """Run AI visual layout analysis on screenshots for ai_visual scripts."""
    from ai.provider import get_provider_for_feature

    project_root = Path(settings.PLAYWRIGHT_PROJECT_ROOT)

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT tr.id, tr.item_id, tr.screenshot_path, i.title
            FROM test_results tr
            LEFT JOIN items i ON i.item_id = tr.item_id
            WHERE tr.run_id = %s
              AND tr.screenshot_path IS NOT NULL
        """, [run_id])
        cols = [c[0] for c in cursor.description]
        results = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if not results:
        return

    provider = get_provider_for_feature('vision')

    for result in results:
        screenshot_path = project_root / result['screenshot_path']
        if not screenshot_path.exists():
            continue

        start = time.time()
        try:
            b64 = base64.b64encode(screenshot_path.read_bytes()).decode()
            analysis = provider.analyze_screenshot(b64, result.get('title') or '')
            duration_ms = int((time.time() - start) * 1000)
            issues = analysis.get('issues', [])

            _create_analysis_and_review(
                run_id, result['item_id'], result['id'],
                'visual_layout', issues,
                raw_response=analysis.get('raw', ''),
                model_used=analysis.get('model', ''),
                duration_ms=duration_ms,
            )
        except Exception as e:
            print(f'[PostExec] Visual analysis failed for result {result["id"]}: {e}')


def _compute_pixel_diff(baseline_path, screenshot_path, result_id, project_root):
    """Compute pixel difference ratio between two images using Pillow."""
    try:
        from PIL import Image
        import numpy as np

        baseline_img = Image.open(baseline_path).convert('RGB')
        screenshot_img = Image.open(screenshot_path).convert('RGB')

        # Resize to same dimensions if needed
        if baseline_img.size != screenshot_img.size:
            screenshot_img = screenshot_img.resize(baseline_img.size)

        baseline_arr = np.array(baseline_img)
        screenshot_arr = np.array(screenshot_img)

        # Compute per-pixel difference
        diff = np.abs(baseline_arr.astype(int) - screenshot_arr.astype(int))
        # A pixel is "different" if any channel differs by more than 10
        diff_mask = np.any(diff > 10, axis=2)
        diff_ratio = float(np.sum(diff_mask)) / float(diff_mask.size)

        # Save diff image
        diff_dir = project_root / 'test-results' / 'diffs'
        diff_dir.mkdir(parents=True, exist_ok=True)
        diff_visual = Image.fromarray((diff_mask * 255).astype(np.uint8))
        diff_visual.save(diff_dir / f'{result_id}.png')

        return diff_ratio
    except ImportError:
        print('[PostExec] Pillow or numpy not installed, skipping pixel diff')
        return 0.0
    except Exception as e:
        print(f'[PostExec] Pixel diff error: {e}')
        return 0.0


def _create_analysis_and_review(run_id, item_id, test_result_id, analysis_type, issues,
                                raw_response='', model_used='', duration_ms=0):
    """Create an AIAnalysis record, and a Review if issues were found."""
    issues_found = len(issues) > 0

    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO ai_analyses (run_id, item_id, test_result_id, analysis_type,
                                     status, issues_found, issues, raw_response,
                                     model_used, duration_ms)
            VALUES (%s, %s, %s, %s, 'completed', %s, %s, %s, %s, %s)
            RETURNING id
        """, [run_id, item_id, test_result_id, analysis_type,
              issues_found, json.dumps(issues), raw_response,
              model_used, duration_ms])
        analysis_id = cursor.fetchone()[0]

        if issues_found:
            cursor.execute("""
                INSERT INTO reviews (analysis_id, status)
                VALUES (%s, 'pending')
            """, [str(analysis_id)])


def _create_pending_baseline(item_id, browser, device_profile, screenshot_path, environment_id):
    """Create a pending baseline (no approval) from a first-run screenshot."""
    if not item_id:
        return

    with connection.cursor() as cursor:
        # Check if one already exists (any version)
        cursor.execute("""
            SELECT id FROM baselines
            WHERE item_id = %s AND browser = %s AND device_profile = %s
            LIMIT 1
        """, [item_id, browser, device_profile])
        if cursor.fetchone():
            return  # Baseline already exists

        cursor.execute("""
            INSERT INTO baselines (item_id, environment_id, browser, device_profile,
                                   version, screenshot_path)
            VALUES (%s, %s, %s, %s, '1.0', %s)
        """, [item_id, environment_id, browser, device_profile, screenshot_path])
