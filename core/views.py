import base64
import hashlib
import logging
import secrets
import urllib.parse

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from decouple import config as env_config
import requests as http_requests

from .models import UserSettings, OIDCProvider

logger = logging.getLogger('scout.auth')


def _local_login_enabled():
    """Check if local login is enabled (DB setting + env override)."""
    if env_config('ALLOW_LOCAL_LOGIN', default='0') == '1':
        return True
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT value FROM ai_settings WHERE key = 'local_login_enabled'")
            row = cursor.fetchone()
            if row:
                import json
                val = row[0]
                if isinstance(val, str):
                    val = json.loads(val)
                return bool(val)
    except Exception:
        pass
    return True  # default: local login on


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('/')

    oidc_providers = list(OIDCProvider.objects.filter(enabled=True).values('id', 'name'))
    local_enabled = _local_login_enabled()

    # Auto-redirect if local login disabled and exactly one provider
    if not local_enabled and len(oidc_providers) == 1:
        return redirect(reverse('oidc_login', kwargs={'provider_id': oidc_providers[0]['id']}))

    error = None
    if request.method == 'POST' and local_enabled:
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            error = 'Invalid username or password.'

    return render(request, 'login.html', {
        'error': error,
        'oidc_providers': oidc_providers,
        'local_login_enabled': local_enabled,
    })


def logout_view(request):
    logout(request)
    return redirect('/login/')


TIMEZONE_CHOICES = [
    ('US', [
        'America/New_York',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
        'America/Anchorage',
        'Pacific/Honolulu',
    ]),
    ('Canada', [
        'America/Toronto',
        'America/Vancouver',
        'America/Edmonton',
        'America/Winnipeg',
        'America/Halifax',
        'America/St_Johns',
    ]),
    ('Europe', [
        'Europe/London',
        'Europe/Berlin',
        'Europe/Paris',
        'Europe/Rome',
        'Europe/Madrid',
        'Europe/Amsterdam',
        'Europe/Moscow',
    ]),
    ('Asia', [
        'Asia/Tokyo',
        'Asia/Shanghai',
        'Asia/Kolkata',
        'Asia/Dubai',
        'Asia/Singapore',
        'Asia/Seoul',
    ]),
    ('Pacific', [
        'Australia/Sydney',
        'Australia/Perth',
        'Pacific/Auckland',
    ]),
    ('Other', [
        'UTC',
        'America/Sao_Paulo',
        'Africa/Cairo',
        'Africa/Johannesburg',
    ]),
]


@login_required
@require_http_methods(["GET", "POST"])
def settings_view(request):
    settings_obj, _ = UserSettings.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type', '')

        if form_type == 'timezone':
            tz = request.POST.get('timezone', '').strip()
            valid = {tz_name for _, tzs in TIMEZONE_CHOICES for tz_name in tzs}
            if tz in valid:
                settings_obj.timezone = tz
                settings_obj.save()
                messages.success(request, f'Timezone updated to {tz}.')
            else:
                messages.error(request, 'Invalid timezone selected.')

        elif form_type == 'profile':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.email = email
            request.user.save()
            messages.success(request, 'Profile updated.')

        elif form_type == 'password':
            current = request.POST.get('current_password', '')
            new_pw = request.POST.get('new_password', '')
            confirm = request.POST.get('confirm_password', '')
            if not request.user.check_password(current):
                messages.error(request, 'Current password is incorrect.')
            elif len(new_pw) < 8:
                messages.error(request, 'New password must be at least 8 characters.')
            elif new_pw != confirm:
                messages.error(request, 'New passwords do not match.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password changed successfully.')

        return redirect('settings')

    return render(request, 'core/settings.html', {
        'timezone_choices': TIMEZONE_CHOICES,
        'current_timezone': settings_obj.timezone,
    })


# ── OIDC / OAuth 2.0 ──────────────────────────────────────────────

def oidc_login(request, provider_id):
    """Initiate the OIDC authorization code flow with PKCE."""
    provider = get_object_or_404(OIDCProvider, id=provider_id, enabled=True)

    state = secrets.token_urlsafe(16)

    # PKCE: generate verifier and S256 challenge
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()

    request.session['oidc_state'] = state
    request.session['oidc_provider_id'] = provider_id
    request.session['oidc_code_verifier'] = code_verifier

    redirect_uri = request.build_absolute_uri(
        reverse('oidc_callback', kwargs={'provider_id': provider_id})
    )

    params = urllib.parse.urlencode({
        'response_type': 'code',
        'client_id': provider.client_id,
        'redirect_uri': redirect_uri,
        'scope': 'openid email profile',
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    })

    return redirect(f'{provider.authorization_endpoint}?{params}')


def oidc_callback(request, provider_id):
    """Handle the OIDC authorization callback and log the user in."""
    stored_state = request.session.pop('oidc_state', None)
    stored_provider_id = request.session.pop('oidc_provider_id', None)
    code_verifier = request.session.pop('oidc_code_verifier', None)

    state = request.GET.get('state')
    code = request.GET.get('code')
    error = request.GET.get('error')

    if error:
        logger.error('OIDC callback: IdP returned error=%s desc=%s',
                     error, request.GET.get('error_description', ''))
        return redirect('login')

    if not code:
        logger.error('OIDC callback: no authorization code')
        return redirect('login')

    if not stored_state or state != stored_state:
        logger.error('OIDC callback: state mismatch')
        return redirect('login')

    if stored_provider_id != provider_id:
        logger.error('OIDC callback: provider_id mismatch')
        return redirect('login')

    provider = get_object_or_404(OIDCProvider, id=provider_id, enabled=True)

    redirect_uri = request.build_absolute_uri(
        reverse('oidc_callback', kwargs={'provider_id': provider_id})
    )

    # Exchange authorization code for tokens
    try:
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': provider.client_id,
            'client_secret': provider.client_secret,
        }
        if code_verifier:
            token_data['code_verifier'] = code_verifier
        token_resp = http_requests.post(
            provider.token_endpoint,
            data=token_data,
            headers={'Accept': 'application/json'},
            timeout=10,
        )
        if not token_resp.ok:
            logger.error('OIDC callback: token endpoint returned %s: %s',
                         token_resp.status_code, token_resp.text[:500])
            return redirect('login')
        tokens = token_resp.json()
    except Exception as exc:
        logger.error('OIDC callback: token exchange failed: %s', exc)
        return redirect('login')

    access_token = tokens.get('access_token', '')
    id_token_str = tokens.get('id_token', '')

    # Verify and decode the ID token
    claims = {}
    if id_token_str:
        try:
            claims = _verify_id_token(id_token_str, provider)
        except Exception as exc:
            logger.error('OIDC callback: ID token verification failed: %s', exc)
            return redirect('login')

    # Fetch userinfo
    userinfo = {}
    if access_token and provider.user_endpoint:
        try:
            ui_resp = http_requests.get(
                provider.user_endpoint,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10,
            )
            if ui_resp.ok:
                userinfo = ui_resp.json()
        except Exception as exc:
            logger.warning('OIDC callback: userinfo fetch failed: %s', exc)

    # Merge: userinfo takes precedence over id_token claims
    profile = {**claims, **userinfo}

    email = profile.get('email', '').strip().lower()
    sub = str(profile.get('sub', '')).strip()
    preferred_username = (
        profile.get('preferred_username', '')
        or profile.get('name', '')
        or email
    ).strip()

    if not email and not sub:
        logger.error('OIDC callback: no email or sub in profile')
        return redirect('login')

    # Check capability claims
    has_site_access = bool(profile.get('cap:site_scout', False))
    is_admin = bool(profile.get('cap:admin_scout', False))

    if not has_site_access:
        logger.warning('OIDC callback: access denied — cap:site_scout not granted (email=%s)', email)
        return render(request, 'login.html', {
            'error': 'Access denied. Your identity provider account does not have SCOUT access.',
            'oidc_providers': list(OIDCProvider.objects.filter(enabled=True).values('id', 'name')),
            'local_login_enabled': _local_login_enabled(),
        })

    # Find or create user
    user = None
    if email:
        user = User.objects.filter(email__iexact=email).first()
    if user is None and sub:
        user = User.objects.filter(username=f'oidc_{sub[:200]}').first()
    if user is None and preferred_username:
        user = User.objects.filter(username__iexact=preferred_username).first()
    if user is None:
        base_username = (preferred_username or email.split('@')[0] or f'oidc_{sub}')[:140]
        username = base_username
        i = 1
        while User.objects.filter(username=username).exists():
            username = f'{base_username}_{i}'
            i += 1
        logger.info('OIDC callback: creating user username=%s email=%s is_staff=%s',
                    username, email, is_admin)
        user = User.objects.create_user(username=username, email=email, is_staff=is_admin)
        user.set_unusable_password()
        user.save()
    else:
        # Sync admin status from IdP on every login
        if user.is_staff != is_admin:
            user.is_staff = is_admin
            user.save(update_fields=['is_staff'])

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    logger.info('OIDC callback: logged in user=%s is_staff=%s', user.username, user.is_staff)
    return redirect('/')


def _verify_id_token(id_token_str, provider):
    """Verify an OIDC ID token JWT and return the decoded claims."""
    import jwt
    from jwt import PyJWKClient

    if provider.sign_algo == 'HS256':
        return jwt.decode(
            id_token_str,
            provider.client_secret,
            algorithms=['HS256'],
            audience=provider.client_id,
        )

    # RS256 (or other asymmetric) — fetch signing key from JWKS endpoint
    jwks_client = PyJWKClient(provider.jwks_endpoint)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token_str)
    return jwt.decode(
        id_token_str,
        signing_key.key,
        algorithms=[provider.sign_algo],
        audience=provider.client_id,
    )
