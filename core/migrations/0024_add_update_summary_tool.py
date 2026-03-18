"""Add update_summary AI tool."""
from django.db import migrations


def add_tool(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM ai_tools WHERE id = 'update_summary'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO ai_tools (id, name, description, category, parameters, enabled, created_at)
                VALUES (
                    'update_summary',
                    'Update Summary',
                    'Updates the Script Summary panel with a new description of what the test does. Use this when the user asks to generate, update, or change the summary without modifying the code.',
                    'action',
                    '{"required": ["summary"]}',
                    true,
                    now()
                )
            """)


def remove_tool(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DELETE FROM ai_tools WHERE id = 'update_summary'")


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0023_alter_review_status_alter_testscript_test_type'),
    ]

    operations = [
        migrations.RunPython(add_tool, remove_tool),
    ]
