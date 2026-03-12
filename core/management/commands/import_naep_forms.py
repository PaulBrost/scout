import json
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from core.models import Environment


class Command(BaseCommand):
    help = (
        'Import NAEP assessment forms from a discovery JSON file.\n'
        'Creates an Assessment for each form in the #TheTest dropdown\n'
        'and registers form keys in the Playwright helper config.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', required=True,
            help='Path to the discovery JSON from discover-naep-forms.js',
        )
        parser.add_argument(
            '--environment', required=True,
            help='UUID of the NAEP environment in SCOUT',
        )
        parser.add_argument(
            '--prefix', default='',
            help='Prefix for assessment IDs (e.g., "gates-" produces "gates-form1")',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview changes without writing to the database',
        )

    def handle(self, *args, **options):
        file_path = options['file']
        env_id = options['environment']
        prefix = options['prefix']
        dry_run = options['dry_run']

        try:
            environment = Environment.objects.get(id=env_id)
        except Environment.DoesNotExist:
            raise CommandError(f'Environment with id "{env_id}" does not exist.')

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'File not found: {file_path}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON in {file_path}: {e}')

        forms = data.get('forms', [])
        if not forms:
            self.stderr.write(self.style.WARNING('No forms found in discovery file.'))
            return

        self.stdout.write(f'Environment: {environment.name} ({environment.id})')
        self.stdout.write(f'URL: {data.get("url", "?")}')
        self.stdout.write(f'Forms found: {len(forms)}')
        if prefix:
            self.stdout.write(f'ID prefix: {prefix}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n--- DRY RUN ---\n'))

        created = 0
        updated = 0
        form_keys = {}  # for Playwright helper config

        for form in forms:
            value = form['value']
            label = form['label']

            # Generate a slug from the label for the assessment ID
            slug = self._make_slug(label, prefix)
            form_key = slug
            display_name = label

            # Try to extract subject/grade from the label
            subject = self._guess_subject(label, value)
            grade = self._guess_grade(label, value)

            form_keys[form_key] = value

            if dry_run:
                self.stdout.write(f'  {form_key}: {display_name}')
                self.stdout.write(f'    value: {value}')
                self.stdout.write(f'    subject: {subject}, grade: {grade}')
                continue

            with connection.cursor() as cursor:
                cursor.execute('SELECT id FROM assessments WHERE id = %s', [slug])
                if cursor.fetchone():
                    cursor.execute(
                        """UPDATE assessments SET name=%s, subject=%s, grade=%s,
                           form_value=%s, environment_id=%s, updated_at=now()
                           WHERE id=%s""",
                        [display_name, subject, grade, value,
                         str(environment.id), slug]
                    )
                    self.stdout.write(f'  Updated: {slug} — {display_name}')
                    updated += 1
                else:
                    cursor.execute(
                        """INSERT INTO assessments
                           (id, name, subject, grade, form_value, environment_id,
                            intro_screens, created_at, updated_at)
                           VALUES (%s, %s, %s, %s, %s, %s::uuid, 5, now(), now())""",
                        [slug, display_name, subject, grade, value,
                         str(environment.id)]
                    )
                    self.stdout.write(f'  Created: {slug} — {display_name}')
                    created += 1

        if not dry_run:
            self.stdout.write(f'\nAssessments created: {created}, updated: {updated}')

        # Print form keys for adding to items.js TEST_FORMS
        self.stdout.write(self.style.SUCCESS('\n--- Form keys for playwright/src/helpers/items.js ---'))
        for key, val in form_keys.items():
            self.stdout.write(f"  '{key}': '{val}',")

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry run complete. No changes were made.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nImport complete.'))

    def _make_slug(self, label, prefix):
        """Convert a form label into a URL-safe assessment ID."""
        # Clean up the label
        slug = label.lower().strip()
        # Remove common filler words and XML references
        slug = re.sub(r'\.(xml|prefs)\b', '', slug)
        slug = re.sub(r'[/|\\]', '-', slug)
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug.strip())
        slug = re.sub(r'-+', '-', slug).strip('-')
        # Truncate to reasonable length
        if len(slug) > 60:
            slug = slug[:60].rstrip('-')
        if prefix:
            slug = f'{prefix}{slug}'
        return slug

    def _guess_subject(self, label, value):
        """Try to extract a subject from the form label/value."""
        lower = (label + ' ' + value).lower()
        if 'math' in lower or 'cra' in lower:
            return 'Mathematics'
        if 'read' in lower or 'lit' in lower:
            return 'Reading'
        if 'science' in lower or 'sci' in lower:
            return 'Science'
        if 'writing' in lower:
            return 'Writing'
        return 'General'

    def _guess_grade(self, label, value):
        """Try to extract a grade from the form label/value."""
        lower = (label + ' ' + value).lower()
        m = re.search(r'(\d+)\s*(?:th|st|nd|rd)?\s*grade', lower)
        if m:
            return f'Grade {m.group(1)}'
        m = re.search(r'grade\s*(\d+)', lower)
        if m:
            return f'Grade {m.group(1)}'
        if '4th' in lower:
            return 'Grade 4'
        if '8th' in lower:
            return 'Grade 8'
        return None
