from django.db import migrations, models


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
    ]
