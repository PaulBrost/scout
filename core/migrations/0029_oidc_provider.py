"""Create OIDCProvider model for OIDC/OAuth2 authentication."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0028_review_issue_detail'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS oidc_providers (
                    id serial PRIMARY KEY,
                    name varchar(100) NOT NULL,
                    client_id varchar(255) NOT NULL,
                    client_secret varchar(500) NOT NULL,
                    authorization_endpoint varchar(500) NOT NULL,
                    token_endpoint varchar(500) NOT NULL,
                    user_endpoint varchar(500) NOT NULL,
                    jwks_endpoint varchar(500) NOT NULL DEFAULT '',
                    sign_algo varchar(10) NOT NULL DEFAULT 'RS256',
                    enabled boolean NOT NULL DEFAULT true,
                    logout_url varchar(500) NOT NULL DEFAULT ''
                );
            """,
            reverse_sql="DROP TABLE IF EXISTS oidc_providers;",
        ),
    ]
