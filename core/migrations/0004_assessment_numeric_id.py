"""
Add numeric_id auto-increment column to assessments for URL-safe routing.
Replaces text PK in URLs with integer for cleaner, more reliable URLs.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_test_types_and_pipeline'),
    ]

    operations = [
        # Add the column as a serial (auto-incrementing integer) with unique constraint
        migrations.RunSQL(
            sql="""
                ALTER TABLE assessments
                ADD COLUMN numeric_id SERIAL UNIQUE NOT NULL;
            """,
            reverse_sql="""
                ALTER TABLE assessments DROP COLUMN numeric_id;
            """,
        ),
        # Register the field with Django's state so the ORM knows about it
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='assessment',
                    name='numeric_id',
                    field=models.IntegerField(unique=True, editable=False),
                ),
            ],
            database_operations=[],  # Already handled by RunSQL above
        ),
    ]
