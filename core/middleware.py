import zoneinfo

from django.utils import timezone


class ImpersonationMiddleware:
    """Detect active impersonation and annotate the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_id = request.session.get('_impersonate_admin_id')
        if admin_id:
            request.is_impersonating = True
            request.impersonator_id = admin_id
        else:
            request.is_impersonating = False
            request.impersonator_id = None
        return self.get_response(request)


class UserTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                tz = request.user.settings.timezone
                timezone.activate(zoneinfo.ZoneInfo(tz))
            except Exception:
                timezone.deactivate()
        else:
            timezone.deactivate()
        return self.get_response(request)
