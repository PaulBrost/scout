"""Add can_change_password to user_settings."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0029_oidc_provider'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS can_change_password boolean NOT NULL DEFAULT true;",
            reverse_sql="ALTER TABLE user_settings DROP COLUMN IF EXISTS can_change_password;",
        ),
    ]
