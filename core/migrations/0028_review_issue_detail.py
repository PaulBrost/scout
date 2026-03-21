"""Add issue_detail to reviews and issue_signature to suppressions for per-issue granularity."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0027_suppression_ai_support'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE reviews ADD COLUMN IF NOT EXISTS issue_detail jsonb;
                ALTER TABLE review_suppressions ADD COLUMN IF NOT EXISTS issue_signature text;
            """,
            reverse_sql="""
                ALTER TABLE reviews DROP COLUMN IF EXISTS issue_detail;
                ALTER TABLE review_suppressions DROP COLUMN IF EXISTS issue_signature;
            """,
        ),
    ]
