"""API token authentication and rate limiting."""
import hashlib
import time
import secrets
from collections import defaultdict
from functools import wraps
from django.http import JsonResponse
from django.db import connection
from django.utils import timezone


# In-memory sliding-window rate limiter: {client_id: [timestamp, ...]}
_rate_limit_windows = defaultdict(list)


def generate_api_key():
    """Generate a new API key with scout_ prefix (46 chars total)."""
    return f'scout_{secrets.token_hex(20)}'


def hash_api_key(key):
    """SHA-256 hash of the API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def _get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _check_rate_limit(client_id, limit):
    """Sliding-window rate limit check. Returns (allowed, remaining, reset_epoch)."""
    now = time.time()
    window = 60  # 1 minute

    # Prune expired entries
    _rate_limit_windows[client_id] = [
        t for t in _rate_limit_windows[client_id] if now - t < window
    ]

    current = len(_rate_limit_windows[client_id])
    if current >= limit:
        oldest = min(_rate_limit_windows[client_id])
        return False, 0, int(oldest + window)

    _rate_limit_windows[client_id].append(now)
    return True, limit - current - 1, int(now + window)


def _log_request(client_id, method, path, status_code, ip_address):
    """Audit-log an API request."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO api_client_logs (id, client_id, method, path, status_code, ip_address, created_at)
                   VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, now())""",
                [str(client_id), method, path[:500], status_code, ip_address]
            )
    except Exception:
        pass  # Never let logging break an API response


def api_auth_required(view_func):
    """Decorator: validate Bearer token, enforce rate limits, log request."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # --- Extract token ---
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth.startswith('Bearer '):
            return JsonResponse(
                {'error': {'code': 'unauthorized',
                           'message': 'Missing or invalid Authorization header. Use: Bearer <api_key>'}},
                status=401,
            )
        token = auth[7:].strip()
        if not token:
            return JsonResponse(
                {'error': {'code': 'unauthorized', 'message': 'API key is empty.'}},
                status=401,
            )

        # --- Look up client ---
        token_hash = hash_api_key(token)
        ip = _get_client_ip(request)

        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id, name, environment_id, is_active, expires_at, rate_limit
                   FROM api_clients WHERE key_hash = %s""",
                [token_hash],
            )
            row = cursor.fetchone()

        if not row:
            return JsonResponse(
                {'error': {'code': 'unauthorized', 'message': 'Invalid API key.'}},
                status=401,
            )

        client_id, client_name, environment_id, is_active, expires_at, rate_limit = row

        # --- Active check ---
        if not is_active:
            _log_request(client_id, request.method, request.path, 403, ip)
            return JsonResponse(
                {'error': {'code': 'forbidden', 'message': 'API client is disabled.'}},
                status=403,
            )

        # --- Expiration check ---
        if expires_at and timezone.now() > expires_at:
            _log_request(client_id, request.method, request.path, 403, ip)
            return JsonResponse(
                {'error': {'code': 'forbidden', 'message': 'API key has expired.'}},
                status=403,
            )

        # --- Rate limiting ---
        limit = rate_limit or 60
        allowed, remaining, reset_at = _check_rate_limit(str(client_id), limit)
        if not allowed:
            _log_request(client_id, request.method, request.path, 429, ip)
            resp = JsonResponse(
                {'error': {'code': 'rate_limited',
                           'message': 'Rate limit exceeded. Try again later.'}},
                status=429,
            )
            resp['X-RateLimit-Limit'] = str(limit)
            resp['X-RateLimit-Remaining'] = '0'
            resp['X-RateLimit-Reset'] = str(reset_at)
            resp['Retry-After'] = str(max(1, reset_at - int(time.time())))
            return resp

        # --- Attach client context to request ---
        request.api_client = {
            'id': client_id,
            'name': client_name,
            'environment_id': environment_id,
        }

        # Update last_used_at (fire-and-forget)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE api_clients SET last_used_at = now() WHERE id = %s",
                    [str(client_id)],
                )
        except Exception:
            pass

        # --- Call the actual view ---
        response = view_func(request, *args, **kwargs)

        # --- Add rate-limit headers ---
        response['X-RateLimit-Limit'] = str(limit)
        response['X-RateLimit-Remaining'] = str(remaining)
        response['X-RateLimit-Reset'] = str(reset_at)

        # --- Audit log ---
        _log_request(client_id, request.method, request.path, response.status_code, ip)

        return response

    return wrapper
