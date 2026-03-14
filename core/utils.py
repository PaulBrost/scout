"""Shared utilities for SCOUT."""
import threading
from django.db import connection


def spawn_background_task(fn, *args, **kwargs):
    """Run fn in a daemon thread with proper DB connection cleanup.

    Django only manages connections for the request/response cycle.
    Background threads must close connections explicitly or they leak
    until PostgreSQL runs out of connection slots.
    """
    def wrapper():
        try:
            fn(*args, **kwargs)
        finally:
            connection.close()

    threading.Thread(target=wrapper, daemon=True).start()
