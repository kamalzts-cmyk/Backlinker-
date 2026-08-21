"""Settings.database_url: hosted-Postgres providers (Neon, Render, ...)
hand back a single connection string via DATABASE_URL rather than the
separate POSTGRES_* fields this app defaults to -- see docs/DEPLOYMENT.md.
"""

from app.core.config import Settings


def test_database_url_defaults_to_the_postgres_star_fields():
    settings = Settings(
        postgres_user="u", postgres_password="p", postgres_host="h", postgres_port=1, postgres_db="d"
    )

    assert settings.database_url == "postgresql+psycopg://u:p@h:1/d"


def test_database_url_env_var_overrides_and_gets_the_psycopg_driver_scheme():
    settings = Settings(database_url_override="postgresql://u:p@ep.neon.tech/d?sslmode=require")

    assert settings.database_url == "postgresql+psycopg://u:p@ep.neon.tech/d?sslmode=require"


def test_database_url_env_var_handles_the_postgres_scheme_alias_too():
    settings = Settings(database_url_override="postgres://u:p@h/d")

    assert settings.database_url == "postgresql+psycopg://u:p@h/d"
