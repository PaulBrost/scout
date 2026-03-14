from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_suite_script_browser_viewport'),
    ]

    operations = [
        migrations.CreateModel(
            name='TestScriptBaseline',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('script_path', models.TextField()),
                ('name', models.TextField()),
                ('browser', models.TextField(default='chromium')),
                ('viewport', models.TextField(default='1920x1080')),
                ('file_path', models.TextField()),
                ('source_run', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='generated_baselines',
                    to='core.testrun',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'test_script_baselines',
                'ordering': ['name'],
                'unique_together': {('script_path', 'name', 'browser', 'viewport')},
            },
        ),
    ]
