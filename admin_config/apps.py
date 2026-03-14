from django.apps import AppConfig


class AdminConfigConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admin_config'

    def ready(self):
        # Register daily archive cleanup schedule with django-q2 (deferred)
        from django.db.models.signals import post_migrate
        post_migrate.connect(_ensure_cleanup_schedule, sender=self)


def _ensure_cleanup_schedule(sender, **kwargs):
    try:
        from django_q.models import Schedule
        if not Schedule.objects.filter(name='cleanup_expired_archives').exists():
            Schedule.objects.create(
                name='cleanup_expired_archives',
                func='admin_config.views._cleanup_expired_archives',
                schedule_type=Schedule.DAILY,
                repeats=-1,
            )
    except Exception:
        pass
