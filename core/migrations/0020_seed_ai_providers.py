"""Data migration: seed ai_providers from env vars and set feature provider IDs."""
import uuid
from django.db import migrations
from django.conf import settings


def seed_providers(apps, schema_editor):
    """Create an AIProvider from current env-var config and assign to all features."""
    db_alias = schema_editor.connection.alias
    AIProvider = apps.get_model('core', 'AIProvider')
    AISetting = apps.get_model('core', 'AISetting')

    ai_provider = getattr(settings, 'AI_PROVIDER', 'mock')
    provider_id = None

    if ai_provider == 'azure':
        provider_id = uuid.uuid4()
        AIProvider.objects.using(db_alias).create(
            id=provider_id,
            name='Azure OpenAI (migrated)',
            provider_type='azure_openai',
            api_key=getattr(settings, 'AZURE_API_KEY', ''),
            base_url=getattr(settings, 'AZURE_ENDPOINT', ''),
            deployment_id=getattr(settings, 'AZURE_TEXT_DEPLOYMENT', 'gpt-4o'),
            api_version=getattr(settings, 'AZURE_API_VERSION', '2024-02-01'),
            enabled=True,
        )
    elif ai_provider == 'ollama':
        provider_id = uuid.uuid4()
        host = getattr(settings, 'OLLAMA_HOST', 'localhost:11434')
        model = getattr(settings, 'OLLAMA_TEXT_MODEL', 'qwen2.5:14b')
        AIProvider.objects.using(db_alias).create(
            id=provider_id,
            name='Ollama (migrated)',
            provider_type='openai_compat',
            base_url=f'http://{host}/v1/',
            model=model,
            enabled=True,
        )

    if provider_id:
        pid_str = str(provider_id)
        for feature in ('builder', 'text', 'vision'):
            AISetting.objects.using(db_alias).update_or_create(
                key=f'{feature}_provider_id',
                defaults={'value': pid_str},
            )

    # Clean up old per-feature provider settings
    AISetting.objects.using(db_alias).filter(
        key__in=[
            'text_provider_type', 'text_provider_config',
            'vision_provider_type', 'vision_provider_config',
        ]
    ).delete()


def reverse_seed(apps, schema_editor):
    """Remove seeded providers and feature assignments."""
    db_alias = schema_editor.connection.alias
    AIProvider = apps.get_model('core', 'AIProvider')
    AISetting = apps.get_model('core', 'AISetting')
    AIProvider.objects.using(db_alias).filter(name__endswith='(migrated)').delete()
    AISetting.objects.using(db_alias).filter(
        key__in=['builder_provider_id', 'text_provider_id', 'vision_provider_id']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_aiprovider'),
    ]

    operations = [
        migrations.RunPython(seed_providers, reverse_seed),
    ]
