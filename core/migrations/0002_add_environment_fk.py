"""
Add environment FK to Item and TestScript models.

Three-step migration:
1. Add nullable environment_id column to both tables
2. Backfill: derive from assessment.environment_id or fall back to default environment
3. Make the column NOT NULL
"""

from django.db import migrations, models
import django.db.models.deletion


def backfill_environment(apps, schema_editor):
    """Backfill environment_id from assessment relationships or default environment."""
    from django.db import connection

    with connection.cursor() as cursor:
        # Backfill items: set environment_id from assessment.environment_id
        cursor.execute("""
            UPDATE items
            SET environment_id = a.environment_id
            FROM assessments a
            WHERE items.assessment_id = a.id
              AND a.environment_id IS NOT NULL
              AND items.environment_id IS NULL
        """)

        # Backfill test_scripts: set from assessment.environment_id
        cursor.execute("""
            UPDATE test_scripts
            SET environment_id = a.environment_id
            FROM assessments a
            WHERE test_scripts.assessment_id = a.id
              AND a.environment_id IS NOT NULL
              AND test_scripts.environment_id IS NULL
        """)

        # Backfill test_scripts: try item -> assessment -> environment chain
        cursor.execute("""
            UPDATE test_scripts
            SET environment_id = a.environment_id
            FROM items i
            JOIN assessments a ON i.assessment_id = a.id
            WHERE test_scripts.item_id = i.item_id
              AND a.environment_id IS NOT NULL
              AND test_scripts.environment_id IS NULL
        """)

        # Check for remaining orphans
        cursor.execute("SELECT COUNT(*) FROM items WHERE environment_id IS NULL")
        orphan_items = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM test_scripts WHERE environment_id IS NULL")
        orphan_scripts = cursor.fetchone()[0]

        if orphan_items > 0 or orphan_scripts > 0:
            # Get default environment
            cursor.execute("SELECT id FROM environments WHERE is_default = true LIMIT 1")
            row = cursor.fetchone()
            if not row:
                # Fall back to first environment
                cursor.execute("SELECT id FROM environments ORDER BY created_at LIMIT 1")
                row = cursor.fetchone()

            if not row:
                if orphan_items > 0 or orphan_scripts > 0:
                    raise RuntimeError(
                        f"Cannot backfill environment_id: {orphan_items} items and "
                        f"{orphan_scripts} scripts have no environment, and no environments "
                        f"exist in the database. Create at least one environment first."
                    )
            else:
                default_env_id = row[0]
                if orphan_items > 0:
                    cursor.execute(
                        "UPDATE items SET environment_id = %s WHERE environment_id IS NULL",
                        [default_env_id]
                    )
                if orphan_scripts > 0:
                    cursor.execute(
                        "UPDATE test_scripts SET environment_id = %s WHERE environment_id IS NULL",
                        [default_env_id]
                    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        # Step 1: Add nullable columns
        migrations.AddField(
            model_name='item',
            name='environment',
            field=models.ForeignKey(
                db_column='environment_id',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='items',
                to='core.environment',
            ),
        ),
        migrations.AddField(
            model_name='testscript',
            name='environment',
            field=models.ForeignKey(
                db_column='environment_id',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='test_scripts',
                to='core.environment',
            ),
        ),

        # Step 2: Backfill
        migrations.RunPython(backfill_environment, migrations.RunPython.noop),

        # Step 3: Make NOT NULL
        migrations.AlterField(
            model_name='item',
            name='environment',
            field=models.ForeignKey(
                db_column='environment_id',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='items',
                to='core.environment',
            ),
        ),
        migrations.AlterField(
            model_name='testscript',
            name='environment',
            field=models.ForeignKey(
                db_column='environment_id',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='test_scripts',
                to='core.environment',
            ),
        ),
    ]
