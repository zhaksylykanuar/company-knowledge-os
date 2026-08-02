from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from sqlalchemy.engine import URL, make_url

from app.db.migration_url import MigrationDatabaseUrlError, psycopg_migration_url
from scripts.local_runtime import validate_local_settings

ROOT = Path(__file__).resolve().parents[1]


def _connection_components(url: URL) -> tuple[object, ...]:
    return (
        url.username,
        url.password,
        url.host,
        url.port,
        url.database,
        url.query,
    )


@pytest.mark.parametrize(
    "value",
    [
        (
            "postgresql+asyncpg://user+asyncpg:password+asyncpg@127.0.0.1:5432/"
            "database+asyncpg?marker=query+asyncpg&encoded=%2Basyncpg"
        ),
        (
            "postgresql+asyncpg://user%2Basyncpg:password%2Basyncpg@127.0.0.1:5432/"
            "database%2Basyncpg?marker=query%2Basyncpg&encoded=%252Basyncpg"
        ),
        (
            "postgresql+asyncpg://user:password@127.0.0.1:5432/database"
            "?marker=first%2Basyncpg&marker=second+asyncpg"
        ),
    ],
)
def test_migration_url_changes_only_driver_with_literal_encoded_or_duplicate_markers(
    value: str,
) -> None:
    runtime_url = make_url(value)
    migration_url = make_url(psycopg_migration_url(value))

    assert migration_url.drivername == "postgresql+psycopg"
    assert _connection_components(migration_url) == _connection_components(runtime_url)


def test_local_runtime_and_alembic_targets_have_identical_connection_identity() -> None:
    value = (
        "postgresql+asyncpg://founder:password%2Basyncpg@127.0.0.1:5432/"
        "founderos+asyncpg?sslmode=disable&application_name=runtime%2Basyncpg"
    )
    config = SimpleNamespace(app_env="local", database_url=value)

    runtime_url = validate_local_settings(config)
    migration_url = make_url(psycopg_migration_url(value))

    assert _connection_components(migration_url) == _connection_components(runtime_url)


def test_migration_url_conversion_prints_no_credentials(capsys) -> None:
    secret = "never-output-this+asyncpg"
    value = (
        f"postgresql+asyncpg://founder:{secret}@127.0.0.1:5432/"
        "founderos+asyncpg?marker=private%2Basyncpg"
    )

    psycopg_migration_url(value)

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_invalid_migration_url_error_is_sanitized() -> None:
    secret = "invalid-url-secret+asyncpg"

    with pytest.raises(MigrationDatabaseUrlError) as exc_info:
        psycopg_migration_url(secret)

    assert secret not in str(exc_info.value)


def test_alembic_env_uses_scheme_only_url_conversion() -> None:
    source = (ROOT / "migrations/env.py").read_text(encoding="utf-8")

    assert "psycopg_migration_url(settings.database_url)" in source
    assert '.replace("+asyncpg", "+psycopg")' not in source


def test_alembic_config_round_trips_percent_encoded_connection_identity() -> None:
    value = (
        "postgresql+asyncpg://user%2Bname:password%2Fvalue@127.0.0.1:5432/"
        "database%2Bname?application_name=founder%25runtime"
    )
    migration_value = psycopg_migration_url(value)
    config = Config()

    config.set_main_option("sqlalchemy.url", migration_value.replace("%", "%%"))
    recovered = config.get_main_option("sqlalchemy.url")

    assert recovered == migration_value
    assert _connection_components(make_url(recovered)) == _connection_components(
        make_url(value)
    )
