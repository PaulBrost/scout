from django.db import migrations, models


def set_db_defaults(apps, schema_editor):
    """Set database-level defaults so raw SQL INSERTs that omit these columns still work."""
    schema_editor.execute("ALTER TABLE test_scripts ALTER COLUMN notify_level SET DEFAULT 'disabled'")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_seed_ai_providers'),
    ]

    operations = [
        migrations.AddField(
            model_name='testscript',
            name='notify_emails',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='testscript',
            name='notify_level',
            field=models.TextField(default='disabled', choices=[
                ('disabled', 'Disabled'),
                ('all', 'All (on every completion)'),
                ('issues', 'Only Issues'),
            ]),
        ),
        migrations.RunPython(set_db_defaults, migrations.RunPython.noop),
    ]
