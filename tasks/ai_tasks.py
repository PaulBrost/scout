"""django-q2 task functions for AI analysis queue."""
import json
from django.db import connection


def process_ai_queue():
    """Process pending AI analysis items."""
    from ai.provider import get_provider_for_feature

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT aa.id, aa.analysis_type, tr_item.screenshot_path, tr_item.item_id,
                   i.title
            FROM ai_analyses aa
            LEFT JOIN test_results tr_item ON tr_item.run_id = aa.run_id AND tr_item.item_id = aa.item_id
            LEFT JOIN items i ON i.item_id = aa.item_id
            WHERE aa.status = 'pending'
            ORDER BY aa.created_at
            LIMIT 10
        """)
        cols = [c[0] for c in cursor.description]
        pending = [dict(zip(cols, row)) for row in cursor.fetchall()]

    if not pending:
        return

    for item in pending:
        analysis_id = item['id']
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE ai_analyses SET status = 'processing' WHERE id = %s",
                    [analysis_id]
                )

            # Run analysis based on type — select provider per feature
            if item['analysis_type'] == 'screenshot' and item.get('screenshot_path'):
                provider = get_provider_for_feature('vision')
                import base64
                from pathlib import Path
                from django.conf import settings
                archive_root = Path(settings.SCOUT_ARCHIVE_DIR)
                path = archive_root / item['screenshot_path']
                if not path.exists():
                    path = Path(settings.PLAYWRIGHT_PROJECT_ROOT) / item['screenshot_path']
                if path.exists():
                    b64 = base64.b64encode(path.read_bytes()).decode()
                    result = provider.analyze_screenshot(b64, item.get('title', ''))
                    issues = result.get('issues', [])
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """UPDATE ai_analyses SET status = 'completed', issues_found = %s,
                               issues = %s, raw_response = %s, model_used = %s, duration_ms = %s
                               WHERE id = %s""",
                            [len(issues) > 0, json.dumps(issues), result.get('raw', ''),
                             result.get('model', ''), result.get('durationMs', 0), analysis_id]
                        )
                        continue

            # Mark as skipped if no data to process
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE ai_analyses SET status = 'skipped' WHERE id = %s",
                    [analysis_id]
                )
        except Exception as e:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE ai_analyses SET status = 'error', raw_response = %s WHERE id = %s",
                    [str(e), analysis_id]
                )
