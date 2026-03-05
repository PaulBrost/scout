from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from .models import UserSettings


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('/')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            error = 'Invalid username or password.'

    return render(request, 'login.html', {'error': error})


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
        tz = request.POST.get('timezone', '').strip()
        # Validate against our list
        valid = {tz_name for _, tzs in TIMEZONE_CHOICES for tz_name in tzs}
        if tz in valid:
            settings_obj.timezone = tz
            settings_obj.save()
            messages.success(request, f'Timezone updated to {tz}.')
        else:
            messages.error(request, 'Invalid timezone selected.')
        return redirect('settings')

    return render(request, 'core/settings.html', {
        'timezone_choices': TIMEZONE_CHOICES,
        'current_timezone': settings_obj.timezone,
    })
