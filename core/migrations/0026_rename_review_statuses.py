"""Rename review statuses: issue→confirmed, suppressed→dismissed."""
from django.db import migrations


def forwards(apps, schema_editor):
    schema_editor.execute("UPDATE reviews SET status = 'confirmed' WHERE status = 'issue'")
    schema_editor.execute("UPDATE reviews SET status = 'dismissed' WHERE status = 'suppressed'")


def backwards(apps, schema_editor):
    schema_editor.execute("UPDATE reviews SET status = 'issue' WHERE status = 'confirmed'")
    schema_editor.execute("UPDATE reviews SET status = 'suppressed' WHERE status = 'dismissed'")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0025_feedback_model'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
