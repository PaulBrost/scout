from django.contrib.auth.mixins import LoginRequiredMixin as DjangoLoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from functools import wraps
from .models import UserEnvironment


class LoginRequiredMixin(DjangoLoginRequiredMixin):
    """Redirect to login page if not authenticated."""
    login_url = '/login/'


class AdminRequiredMixin(LoginRequiredMixin):
    """Require is_staff or is_superuser (allows impersonating admins through)."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_staff and not getattr(request, 'is_impersonating', False):
            return HttpResponseForbidden("Admin access required.")
        return super().dispatch(request, *args, **kwargs)


class EnvironmentScopedMixin(LoginRequiredMixin):
    """Provides environment filtering based on user role."""

    def get_user_environment_ids(self):
        """Return list of environment IDs the user can see, or None for all."""
        if self.request.user.is_staff:
            return None  # None = all environments
        return list(
            UserEnvironment.objects.filter(
                user=self.request.user
            ).values_list('environment_id', flat=True)
        )

    def apply_env_filter(self, qs, env_field='environment_id'):
        """Apply environment filter to a queryset."""
        env_ids = self.get_user_environment_ids()
        if env_ids is None:
            return qs
        return qs.filter(**{f'{env_field}__in': env_ids})


def get_user_env_ids(user):
    """Standalone function for use in function-based views."""
    if user.is_staff:
        return None
    return list(
        UserEnvironment.objects.filter(user=user).values_list('environment_id', flat=True)
    )


def env_scope_filter(user, env_field='environment_id'):
    """Return a dict suitable for .filter(**kwargs) or None if admin."""
    env_ids = get_user_env_ids(user)
    if env_ids is None:
        return {}
    return {f'{env_field}__in': env_ids}


def get_owner_filter_id(user):
    """Return user.id for non-admins, None for admins (all access)."""
    if user.is_staff:
        return None
    return user.id


def build_user_scope_sql(user, table_alias, column='created_by_id'):
    """Return (sql_fragment, params) for WHERE clause user scoping.

    Admins: ('', [])
    Non-admins: ('AND (alias.col = %s OR alias.col IS NULL)', [user.id])
    """
    if user.is_staff:
        return ('', [])
    return (f' AND ({table_alias}.{column} = %s OR {table_alias}.{column} IS NULL)', [user.id])


def can_user_access_record(user, created_by_id):
    """True for admins, matching user_id, or NULL (system records)."""
    if user.is_staff:
        return True
    if created_by_id is None:
        return True
    return created_by_id == user.id
