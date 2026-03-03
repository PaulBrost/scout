"""
Add test type system, post-execution pipeline support, and test data sets.

Changes:
- TestRun: add environment FK (nullable), backfill from suite
- Item: add position (nullable integer)
- Assessment: add intro_screens (default=5)
- TestScript: add test_type (default='functional'), tags (JSON), backfill from category
- Baseline: add environment FK (nullable)
- AIAnalysis: add test_result FK (nullable), formalize analysis_type choices
- TestDataSet: new table
"""

from django.db import migrations, models
import django.db.models.deletion
import uuid


def backfill_test_type(apps, schema_editor):
    """Backfill test_type from category values."""
    from django.db import connection

    with connection.cursor() as cursor:
        # visual_regression
        cursor.execute("""
            UPDATE test_scripts
            SET test_type = 'visual_regression',
                tags = CASE
                    WHEN category IS NOT NULL AND category != '' THEN jsonb_build_array(category)
                    ELSE '[]'::jsonb
                END
            WHERE category IS NOT NULL
              AND (LOWER(category) LIKE '%visual%' OR LOWER(category) LIKE '%regression%')
        """)

        # ai_content
        cursor.execute("""
            UPDATE test_scripts
            SET test_type = 'ai_content',
                tags = CASE
                    WHEN category IS NOT NULL AND category != '' THEN jsonb_build_array(category)
                    ELSE '[]'::jsonb
                END
            WHERE category IS NOT NULL
              AND LOWER(category) LIKE '%content%'
              AND test_type = 'functional'
        """)

        # ai_visual
        cursor.execute("""
            UPDATE test_scripts
            SET test_type = 'ai_visual',
                tags = CASE
                    WHEN category IS NOT NULL AND category != '' THEN jsonb_build_array(category)
                    ELSE '[]'::jsonb
                END
            WHERE category IS NOT NULL
              AND (LOWER(category) LIKE '%vision%' OR LOWER(category) LIKE '%screenshot%')
              AND test_type = 'functional'
        """)

        # Remaining with category: keep functional, move category to tags
        cursor.execute("""
            UPDATE test_scripts
            SET tags = CASE
                    WHEN category IS NOT NULL AND category != '' THEN jsonb_build_array(category)
                    ELSE '[]'::jsonb
                END
            WHERE category IS NOT NULL
              AND category != ''
              AND tags = '[]'::jsonb
        """)


def backfill_run_environment(apps, schema_editor):
    """Backfill TestRun.environment_id from suite.environment_id."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE test_runs
            SET environment_id = s.environment_id
            FROM test_suites s
            WHERE test_runs.suite_id = s.id
              AND s.environment_id IS NOT NULL
              AND test_runs.environment_id IS NULL
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_add_environment_fk'),
    ]

    operations = [
        # --- Assessment: add intro_screens ---
        migrations.AddField(
            model_name='assessment',
            name='intro_screens',
            field=models.IntegerField(default=5),
        ),

        # --- Item: add position ---
        migrations.AddField(
            model_name='item',
            name='position',
            field=models.IntegerField(blank=True, null=True),
        ),

        # --- TestRun: add environment FK ---
        migrations.AddField(
            model_name='testrun',
            name='environment',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='runs',
                to='core.environment',
            ),
        ),

        # --- Baseline: add environment FK ---
        migrations.AddField(
            model_name='baseline',
            name='environment',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='baselines',
                to='core.environment',
            ),
        ),

        # --- TestScript: add test_type and tags ---
        migrations.AddField(
            model_name='testscript',
            name='test_type',
            field=models.TextField(
                choices=[
                    ('functional', 'Functional'),
                    ('visual_regression', 'Visual Regression'),
                    ('ai_content', 'AI Content Analysis'),
                    ('ai_visual', 'AI Visual Analysis'),
                ],
                default='functional',
            ),
        ),
        migrations.AddField(
            model_name='testscript',
            name='tags',
            field=models.JSONField(default=list),
        ),

        # --- AIAnalysis: add test_result FK ---
        migrations.AddField(
            model_name='aianalysis',
            name='test_result',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ai_analyses',
                to='core.testresult',
            ),
        ),

        # --- AIAnalysis: formalize analysis_type choices ---
        migrations.AlterField(
            model_name='aianalysis',
            name='analysis_type',
            field=models.TextField(choices=[
                ('text_content', 'Text Content'),
                ('visual_layout', 'Visual Layout'),
                ('screenshot_diff', 'Screenshot Diff'),
                ('screenshot', 'Screenshot'),
            ]),
        ),

        # --- TestDataSet: new model ---
        migrations.CreateModel(
            name='TestDataSet',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.TextField()),
                ('data_type', models.TextField(choices=[
                    ('credentials', 'Credentials'),
                    ('inputs', 'Test Inputs'),
                    ('items', 'Item List'),
                    ('custom', 'Custom'),
                ])),
                ('data', models.JSONField(default=list)),
                ('description', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('environment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='test_data_sets',
                    to='core.environment',
                )),
                ('assessment', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='test_data_sets',
                    to='core.assessment',
                )),
            ],
            options={
                'db_table': 'test_data_sets',
                'ordering': ['name'],
            },
        ),

        # --- Backfill data ---
        migrations.RunPython(backfill_test_type, migrations.RunPython.noop),
        migrations.RunPython(backfill_run_environment, migrations.RunPython.noop),
    ]
