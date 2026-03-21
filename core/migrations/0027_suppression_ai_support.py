"""Add AI analysis support to review suppressions."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_rename_review_statuses'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE review_suppressions
                    ADD COLUMN IF NOT EXISTS rule_type text NOT NULL DEFAULT 'screenshot',
                    ADD COLUMN IF NOT EXISTS analysis_type text,
                    ADD COLUMN IF NOT EXISTS item_id text;
                ALTER TABLE review_suppressions
                    ALTER COLUMN screenshot_name DROP NOT NULL;
            """,
            reverse_sql="""
                ALTER TABLE review_suppressions
                    DROP COLUMN IF EXISTS rule_type,
                    DROP COLUMN IF EXISTS analysis_type,
                    DROP COLUMN IF EXISTS item_id;
                ALTER TABLE review_suppressions
                    ALTER COLUMN screenshot_name SET NOT NULL;
            """,
        ),
    ]
