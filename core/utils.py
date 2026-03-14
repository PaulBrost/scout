"""Shared utilities for SCOUT."""
import threading
from django.db import close_old_connections


def spawn_background_task(fn, *args, **kwargs):
    """Run fn in a daemon thread with proper DB connection cleanup.

    Django only manages connections for the request/response cycle.
    Background threads must close connections explicitly or they leak
    until PostgreSQL runs out of connection slots.
    """
    def wrapper():
        close_old_connections()  # drop any inherited stale connection
        try:
            fn(*args, **kwargs)
        finally:
            close_old_connections()  # release connection when done

    threading.Thread(target=wrapper, daemon=True).start()
