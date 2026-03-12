from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_add_ai_config_to_test_scripts'),
    ]

    operations = [
        migrations.AddField(
            model_name='testscript',
            name='chat_conversation',
            field=models.ForeignKey(
                blank=True,
                db_column='chat_conversation_id',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='test_scripts',
                to='core.aiconversation',
            ),
        ),
        migrations.AddField(
            model_name='testscript',
            name='test_summary',
            field=models.TextField(blank=True, null=True),
        ),
    ]
