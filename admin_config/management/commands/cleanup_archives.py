from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Delete expired test script archives and their associated run history.'

    def handle(self, *args, **options):
        from admin_config.views import _cleanup_expired_archives
        deleted = _cleanup_expired_archives()
        self.stdout.write(self.style.SUCCESS(f'Cleaned up {deleted} expired archive(s).'))
