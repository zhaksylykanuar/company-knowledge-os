"""Safe SQLAlchemy URL conversion for synchronous Alembic migrations."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import URL, make_url


class MigrationDatabaseUrlError(RuntimeError):
    """A sanitized migration URL conversion failure."""


def _connection_components(url: URL) -> tuple[Any, ...]:
    return (
        url.username,
        url.password,
        url.host,
        url.port,
        url.database,
        url.query,
    )


def psycopg_migration_url(value: str) -> str:
    """Change only the PostgreSQL driver while preserving connection identity."""

    try:
        runtime_url = make_url(value)
    except Exception:
        raise MigrationDatabaseUrlError(
            "DATABASE_URL is not a valid PostgreSQL migration URL."
        ) from None
    if not runtime_url.drivername.startswith("postgresql"):
        raise MigrationDatabaseUrlError("DATABASE_URL must use a PostgreSQL driver for migrations.")

    migration_url = runtime_url.set(drivername="postgresql+psycopg")
    if _connection_components(migration_url) != _connection_components(runtime_url):
        raise MigrationDatabaseUrlError(
            "Alembic URL conversion changed the database connection identity."
        )
    return migration_url.render_as_string(hide_password=False)
