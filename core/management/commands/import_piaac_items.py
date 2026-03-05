import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from core.models import Environment, Assessment, Item, TestScript


class Command(BaseCommand):
    help = 'Import PIAAC items from a discovery JSON file into the SCOUT database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', required=True,
            help='Path to the discovery JSON file (e.g., playwright/discovery-zzz-eng.json)',
        )
        parser.add_argument(
            '--environment', required=True,
            help='UUID of the PIAAC environment in SCOUT',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Preview changes without writing to the database',
        )

    def handle(self, *args, **options):
        file_path = options['file']
        env_id = options['environment']
        dry_run = options['dry_run']

        # Validate environment exists
        try:
            environment = Environment.objects.get(id=env_id)
        except Environment.DoesNotExist:
            raise CommandError(f'Environment with id "{env_id}" does not exist.')

        # Load discovery JSON
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'File not found: {file_path}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON in {file_path}: {e}')

        items_data = data.get('items', [])
        filters = data.get('filters_applied', {})

        if not items_data:
            self.stderr.write(self.style.WARNING('No items found in discovery file.'))
            return

        language_tag = f"{filters.get('country', 'UNK')}/{filters.get('language', 'unk')}"
        self.stdout.write(f'Environment: {environment.name} ({environment.id})')
        self.stdout.write(f'Language tag: {language_tag}')
        self.stdout.write(f'Items to import: {len(items_data)}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n--- DRY RUN (no changes will be written) ---\n'))

        # Create/update Assessment
        domain = filters.get('domain', 'LITNew')
        assessment_id = f'piaac-{domain.lower()}'
        assessment_name = f'PIAAC {domain}'
        if dry_run:
            self.stdout.write(f'  Would create/update Assessment: {assessment_id}')
        else:
            from django.db import connection as conn
            with conn.cursor() as cursor:
                cursor.execute('SELECT id FROM assessments WHERE id = %s', [assessment_id])
                if cursor.fetchone():
                    cursor.execute(
                        """UPDATE assessments SET name=%s, subject=%s, environment_id=%s,
                           description=%s, updated_at=now() WHERE id=%s""",
                        [assessment_name, domain, str(environment.id),
                         f'PIAAC {domain} domain items', assessment_id]
                    )
                    self.stdout.write(f'  Updated Assessment: {assessment_id}')
                else:
                    cursor.execute(
                        """INSERT INTO assessments (id, name, subject, environment_id, description, intro_screens, created_at, updated_at)
                           VALUES (%s, %s, %s, %s::uuid, %s, 5, now(), now())""",
                        [assessment_id, assessment_name, domain, str(environment.id),
                         f'PIAAC {domain} domain items']
                    )
                    self.stdout.write(f'  Created Assessment: {assessment_id}')

        # Import items
        created_count = 0
        updated_count = 0

        for item_data in items_data:
            item_id = item_data.get('item_id', '').strip()
            if not item_id:
                continue

            unit_name = item_data.get('unit_name', item_id)
            href = item_data.get('href', '')

            if dry_run:
                self.stdout.write(f'  Would import item: {item_id} ({unit_name})')
                continue

            try:
                item = Item.objects.get(item_id=item_id)
                # Merge language tag into existing languages list
                languages = item.languages or []
                if language_tag not in languages:
                    languages.append(language_tag)
                    item.languages = languages

                # Update metadata
                metadata = item.metadata or {}
                metadata['href'] = href
                metadata['source'] = 'piaac-discovery'
                metadata['discovered_at'] = datetime.utcnow().isoformat()
                item.metadata = metadata

                item.save()
                updated_count += 1
            except Item.DoesNotExist:
                Item.objects.create(
                    item_id=item_id,
                    title=unit_name,
                    environment=environment,
                    assessment_id=assessment_id,
                    languages=[language_tag],
                    metadata={
                        'href': href,
                        'source': 'piaac-discovery',
                        'discovered_at': datetime.utcnow().isoformat(),
                    },
                )
                created_count += 1

        if not dry_run:
            self.stdout.write(f'  Items created: {created_count}, updated: {updated_count}')

        # Register test scripts
        scripts = [
            {
                'script_path': 'tests/items/piaac-visual-baseline.spec.js',
                'description': 'PIAAC LITNew master visual baseline capture (ZZZ/eng)',
                'test_type': 'visual_regression',
                'tags': ['piaac', 'visual', 'baseline', 'LITNew'],
            },
            {
                'script_path': 'tests/items/piaac-content-validation.spec.js',
                'description': 'PIAAC LITNew AI content and vision analysis',
                'test_type': 'ai_content',
                'tags': ['piaac', 'ai', 'content', 'LITNew'],
            },
        ]

        for script_data in scripts:
            if dry_run:
                self.stdout.write(f"  Would register script: {script_data['script_path']}")
                continue

            _, created = TestScript.objects.update_or_create(
                script_path=script_data['script_path'],
                defaults={
                    'description': script_data['description'],
                    'environment': environment,
                    'assessment_id': assessment_id,
                    'test_type': script_data['test_type'],
                    'tags': script_data['tags'],
                },
            )
            action = 'Registered' if created else 'Updated'
            self.stdout.write(f"  {action} script: {script_data['script_path']}")

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry run complete. No changes were made.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nImport complete.'))
