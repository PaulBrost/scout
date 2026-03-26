import glob
import os

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Update test scripts to use SCOUT_RESULTS_DIR env var for screenshot paths.\n'
        'Replaces hardcoded "test-results/" with "${process.env.SCOUT_RESULTS_DIR || \'test-results\'}/"'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview changes without writing to disk',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        tests_dir = os.path.join(settings.PLAYWRIGHT_PROJECT_ROOT, 'tests')

        if not os.path.isdir(tests_dir):
            self.stderr.write(self.style.ERROR(f'Tests directory not found: {tests_dir}'))
            return

        old = 'test-results/'
        new = "${process.env.SCOUT_RESULTS_DIR || 'test-results'}/"

        updated = 0
        skipped = 0

        for filepath in sorted(glob.glob(os.path.join(tests_dir, '*.spec.js'))):
            with open(filepath, 'r') as f:
                content = f.read()

            if old not in content:
                skipped += 1
                continue

            new_content = content.replace(old, new)
            filename = os.path.basename(filepath)

            if dry_run:
                self.stdout.write(f'  Would update: {filename}')
            else:
                with open(filepath, 'w') as f:
                    f.write(new_content)
                self.stdout.write(f'  Updated: {filename}')

            updated += 1

        self.stdout.write(f'\n{updated} scripts {"would be " if dry_run else ""}updated, {skipped} already up to date.')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry run — no files were modified.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nDone.'))
