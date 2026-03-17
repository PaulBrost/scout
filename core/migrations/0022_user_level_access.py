"""Add created_by FK to TestScript, TestRun, TestSuite, TestDataSet for user-level access control."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_suite_created_by(apps, schema_editor):
    """Convert test_suites.created_by text username → created_by_id integer FK."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            UPDATE test_suites
            SET created_by_id = u.id
            FROM auth_user u
            WHERE test_suites.created_by_legacy = u.username
              AND test_suites.created_by_legacy IS NOT NULL
              AND test_suites.created_by_legacy != ''
        """)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0021_testscript_notifications'),
    ]

    operations = [
        # --- TestScript: add created_by_id ---
        migrations.AddField(
            model_name='testscript',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True,
                db_column='created_by_id',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_scripts',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # --- TestRun: add created_by_id ---
        migrations.AddField(
            model_name='testrun',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True,
                db_column='created_by_id',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_runs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # --- TestDataSet: add created_by_id ---
        migrations.AddField(
            model_name='testdataset',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True,
                db_column='created_by_id',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_datasets',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # --- TestSuite: convert created_by text → FK ---
        # Step 1: Rename existing text column
        migrations.RenameField(
            model_name='testsuite',
            old_name='created_by',
            new_name='created_by_legacy',
        ),

        # Step 2: Add new FK column
        migrations.AddField(
            model_name='testsuite',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True,
                db_column='created_by_id',
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_suites',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # Step 3: Migrate data from username text → user FK
        migrations.RunPython(migrate_suite_created_by, migrations.RunPython.noop),

        # Step 4: Drop legacy column
        migrations.RemoveField(
            model_name='testsuite',
            name='created_by_legacy',
        ),
    ]
