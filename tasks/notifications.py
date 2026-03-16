"""Email notifications for completed test runs."""
import json
from django.db import connection
from django.conf import settings
from django.core.mail import EmailMessage


def send_run_notifications(run_id):
    """Check notification settings for scripts in a run and send emails."""
    if not getattr(settings, 'EMAIL_HOST_USER', ''):
        return

    # Get run details
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT r.status, r.summary, r.completed_at, r.environment_id,
                   e.name AS environment_name,
                   COALESCE(s.name, ts.description, trs.script_path) AS run_label
            FROM test_runs r
            LEFT JOIN environments e ON e.id = r.environment_id
            LEFT JOIN test_suites s ON s.id = r.suite_id
            LEFT JOIN test_run_scripts trs ON trs.run_id = r.id
            LEFT JOIN test_scripts ts ON ts.script_path = trs.script_path
            WHERE r.id = %s
            LIMIT 1
        """, [run_id])
        row = cursor.fetchone()

    if not row:
        return

    run_status, run_summary, completed_at, environment_id, env_name, run_label = row
    if isinstance(run_summary, str):
        try:
            run_summary = json.loads(run_summary)
        except Exception:
            run_summary = {}
    run_summary = run_summary or {}

    # Get scripts with notification settings
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT trs.script_path, trs.status, trs.error_message, trs.duration_ms,
                   ts.notify_emails, ts.notify_level, ts.description
            FROM test_run_scripts trs
            LEFT JOIN test_scripts ts ON ts.script_path = trs.script_path
            WHERE trs.run_id = %s
        """, [run_id])
        cols = [c[0] for c in cursor.description]
        scripts = [dict(zip(cols, r)) for r in cursor.fetchall()]

    # Determine if issues exist
    has_issues = _check_for_issues(run_id, run_status, run_summary)

    # Collect recipients based on notification level
    recipients = set()
    for script in scripts:
        level = script.get('notify_level') or 'disabled'
        emails_str = script.get('notify_emails') or ''

        if level == 'disabled' or not emails_str.strip():
            continue

        should_notify = (level == 'all') or (level == 'issues' and has_issues)
        if should_notify:
            for addr in emails_str.split(';'):
                addr = addr.strip()
                if addr:
                    recipients.add(addr)

    if not recipients:
        return

    subject = _build_subject(run_id, run_status, run_label, env_name, has_issues)
    body = _build_body(run_id, run_status, run_summary, run_label, env_name,
                       completed_at, scripts, has_issues)

    try:
        reply_to = getattr(settings, 'EMAIL_REPLY_TO', '')
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', '') or settings.EMAIL_HOST_USER,
            to=list(recipients),
            reply_to=[reply_to] if reply_to else [],
        )
        # Release DB connection before SMTP call
        connection.close()
        msg.send(fail_silently=False)
        print(f'[Notify] Sent email for run {str(run_id)[:8]} to {len(recipients)} recipients')
    except Exception as e:
        print(f'[Notify] Email send failed for run {str(run_id)[:8]}: {e}')


def _check_for_issues(run_id, run_status, run_summary):
    """Return True if the run has any issues (Playwright failures, AI issues, flagged screenshots)."""
    if run_status in ('failed',):
        return True

    if run_summary.get('failed', 0) > 0 or run_summary.get('errors', 0) > 0:
        return True

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM ai_analyses WHERE run_id = %s AND issues_found = true",
            [run_id]
        )
        if cursor.fetchone()[0] > 0:
            return True

        cursor.execute(
            "SELECT COUNT(*) FROM run_screenshots WHERE run_id = %s AND flagged = true",
            [run_id]
        )
        if cursor.fetchone()[0] > 0:
            return True

    return False


def _build_subject(run_id, status, run_label, env_name, has_issues):
    short_id = str(run_id)[:8]
    label = run_label or short_id
    env_part = f' [{env_name}]' if env_name else ''

    if status == 'cancelled':
        return f'SCOUT{env_part} — {label} was cancelled'
    elif has_issues:
        return f'SCOUT{env_part} — {label} completed with issues'
    else:
        return f'SCOUT{env_part} — {label} completed successfully'


def _build_body(run_id, status, summary, run_label, env_name,
                completed_at, scripts, has_issues):
    lines = [
        'SCOUT Test Run Report',
        '=' * 40,
        '',
        f'Run:         {run_label or run_id}',
        f'Run ID:      {run_id}',
        f'Status:      {status}',
    ]
    if env_name:
        lines.append(f'Environment: {env_name}')
    if completed_at:
        lines.append(f'Completed:   {completed_at}')

    if summary:
        lines.append('')
        lines.append('Summary')
        lines.append('-' * 20)
        for key in ('passed', 'failed', 'errors', 'skipped'):
            val = summary.get(key, 0)
            if val:
                lines.append(f'  {key.capitalize():12s} {val}')

    lines.append('')
    lines.append('Scripts')
    lines.append('-' * 20)
    for s in scripts:
        name = s.get('description') or s.get('script_path', '?')
        dur = f' ({s["duration_ms"]}ms)' if s.get('duration_ms') else ''
        lines.append(f'  [{s["status"]}] {name}{dur}')
        if s.get('error_message'):
            lines.append(f'           Error: {s["error_message"]}')

    lines.append('')
    lines.append(f'View results: /runs/{run_id}/')

    return '\n'.join(lines)
