from .models import Environment, UserEnvironment


def nav_context(request):
    """Add navigation context to all templates."""
    if not request.user.is_authenticated:
        return {}

    # Get environments visible to this user
    if request.user.is_staff:
        environments = Environment.objects.all().order_by('name')
    else:
        env_ids = list(
            UserEnvironment.objects.filter(
                user=request.user
            ).values_list('environment_id', flat=True)
        )
        environments = Environment.objects.filter(id__in=env_ids).order_by('name')

    return {
        'nav_environments': environments,
        'is_admin': request.user.is_staff,
    }
