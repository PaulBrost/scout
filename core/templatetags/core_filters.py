from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def split(value, sep):
    return value.split(sep)


@register.filter
def duration(ms):
    """Convert milliseconds to a human-readable duration string."""
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        return '—'
    if ms < 1000:
        return f'{ms}ms'
    total_secs = ms // 1000
    hours = total_secs // 3600
    minutes = (total_secs % 3600) // 60
    secs = total_secs % 60
    if hours:
        return f'{hours}h {minutes:02d}m {secs:02d}s'
    if minutes:
        return f'{minutes}m {secs:02d}s'
    return f'{secs}s'


@register.filter
def shorttime(value):
    """Format a datetime as a compact timestamp: 'Mar 4, 1:23 PM' or 'Mar 3, 8:05 PM'."""
    if not value:
        return '—'
    try:
        local = timezone.localtime(value)
        return local.strftime('%b %-d, %-I:%M %p')
    except Exception:
        return str(value)
