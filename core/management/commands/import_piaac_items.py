import json
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection as conn
from core.models import Environment, Item


class Command(BaseCommand):
    help = (
        'Import PIAAC items from discovery JSON into the SCOUT database.\n'
        'Supports single-domain files (filters_applied + items) and\n'
        'multi-domain files (domains[] from discover-piaac-domains.js).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', required=True,
            help='Path to the discovery JSON file',
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

        self.stdout.write(f'Environment: {environment.name} ({environment.id})')

        if dry_run:
            self.stdout.write(self.style.WARNING('--- DRY RUN (no changes will be written) ---\n'))

        # Detect format: multi-domain (has "domains" key) vs single-domain (has "filters_applied")
        if 'domains' in data:
            country = data.get('country', 'ZZZ')
            language = data.get('language', 'eng')
            total_created = 0
            total_updated = 0
            for domain_entry in data['domains']:
                domain = domain_entry['domain']
                items_data = domain_entry.get('items', [])
                language_tag = f'{country}/{language}'
                self.stdout.write(f'\n--- Domain: {domain} ({len(items_data)} items) ---')
                self._import_domain(environment, domain, items_data, language_tag, dry_run)
                c, u = self._import_items(environment, domain, items_data, language_tag, dry_run)
                total_created += c
                total_updated += u
            if not dry_run:
                self.stdout.write(self.style.SUCCESS(
                    f'\nImport complete. {len(data["domains"])} domains, '
                    f'{total_created} items created, {total_updated} updated.'
                ))
        else:
            filters = data.get('filters_applied', {})
            items_data = data.get('items', [])
            domain = filters.get('domain', 'LITNew')
            language_tag = f"{filters.get('country', 'UNK')}/{filters.get('language', 'unk')}"
            self.stdout.write(f'Domain: {domain} | Language tag: {language_tag} | Items: {len(items_data)}')
            self._import_domain(environment, domain, items_data, language_tag, dry_run)
            c, u = self._import_items(environment, domain, items_data, language_tag, dry_run)
            if not dry_run:
                self.stdout.write(self.style.SUCCESS(
                    f'\nImport complete. {c} items created, {u} updated.'
                ))

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry run complete. No changes were made.'))

    def _import_domain(self, environment, domain, items_data, language_tag, dry_run):
        """Create or update the Assessment record for a domain."""
        assessment_id = f'piaac-{domain.lower()}'
        assessment_name = f'PIAAC {domain}'
        if dry_run:
            self.stdout.write(f'  Would create/update Assessment: {assessment_id} ({len(items_data)} items)')
            return
        with conn.cursor() as cursor:
            cursor.execute('SELECT id FROM assessments WHERE id = %s', [assessment_id])
            if cursor.fetchone():
                cursor.execute(
                    """UPDATE assessments SET name=%s, subject=%s, environment_id=%s,
                       item_count=%s, description=%s, updated_at=now() WHERE id=%s""",
                    [assessment_name, domain, str(environment.id),
                     len(items_data), f'PIAAC {domain} domain items', assessment_id]
                )
                self.stdout.write(f'  Updated Assessment: {assessment_id}')
            else:
                cursor.execute(
                    """INSERT INTO assessments (id, name, subject, environment_id, item_count, description, intro_screens, created_at, updated_at)
                       VALUES (%s, %s, %s, %s::uuid, %s, %s, 0, now(), now())""",
                    [assessment_id, assessment_name, domain, str(environment.id),
                     len(items_data), f'PIAAC {domain} domain items']
                )
                self.stdout.write(f'  Created Assessment: {assessment_id}')

    def _import_items(self, environment, domain, items_data, language_tag, dry_run):
        """Import items for a domain. Returns (created_count, updated_count)."""
        assessment_id = f'piaac-{domain.lower()}'
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
                # Merge language tag
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
                # Update assessment link if not already set
                if not item.assessment_id:
                    item.assessment_id = assessment_id
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

        return created_count, updated_count
