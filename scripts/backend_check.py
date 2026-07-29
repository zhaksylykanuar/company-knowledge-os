"""Run backend quality gates only against an explicit dedicated test database.

This entrypoint intentionally uses only the Python standard library so it can
validate the database boundary before ``uv sync`` or any application import.
It never emits configured database URLs or their credentials.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, unquote, unquote_plus, urlsplit


ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_ENV = "FOUNDEROS_TEST_DATABASE_URL"
PYTEST_APP_ENV = "test"
DEFAULT_POSTGRES_PORT = 5432
TEST_CORS_ALLOWED_ORIGINS = "http://127.0.0.1:3000"
TEST_DATABASE_MARKER = re.compile(
    r"(?:^|[_-])(?:test|tests|testing|pytest)(?:$|[_-])",
    re.IGNORECASE,
)
POSTGRES_URL_PATTERN = re.compile(r"(?i)\bpostgres(?:ql)?(?:\+[a-z0-9_.-]+)?://[^\s\"'<>]+")
ENDPOINT_QUERY_OVERRIDES = frozenset({"database", "dbname", "host", "hostaddr", "port"})
QUERY_SECRET_KEYS = frozenset({"password", "sslpassword"})
SAFE_CHILD_ENVIRONMENT_KEYS = frozenset(
    {
        "ALL_PROXY",
        "CI",
        "COLORTERM",
        "CURL_CA_BUNDLE",
        "FORCE_COLOR",
        "HOME",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_ADDRESS",
        "LC_COLLATE",
        "LC_CTYPE",
        "LC_IDENTIFICATION",
        "LC_MEASUREMENT",
        "LC_MESSAGES",
        "LC_MONETARY",
        "LC_NAME",
        "LC_NUMERIC",
        "LC_PAPER",
        "LC_TELEPHONE",
        "LC_TIME",
        "NO_COLOR",
        "NO_PROXY",
        "PATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TEMP",
        "TERM",
        "TMP",
        "TMPDIR",
        "TZ",
        "UV_CACHE_DIR",
        "UV_NATIVE_TLS",
        "UV_OFFLINE",
        "UV_PYTHON",
        "UV_PYTHON_DOWNLOADS",
        "UV_PYTHON_PREFERENCE",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)
PROXY_URL_ENVIRONMENT_KEYS = frozenset(
    {"ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"}
)
CHECK_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dependency sync", ("uv", "sync", "--frozen")),
    ("Ruff", ("uv", "run", "ruff", "check", ".")),
    ("mypy", ("uv", "run", "mypy", "app")),
    ("Alembic upgrade", ("uv", "run", "alembic", "upgrade", "head")),
    ("Alembic schema check", ("uv", "run", "alembic", "check")),
    ("pytest", ("uv", "run", "pytest", "-q")),
    (
        "tracked secret scan",
        ("bash", "scripts/check_no_secrets.sh", "--tracked"),
    ),
)


class BackendCheckError(RuntimeError):
    """A safe, secret-free backend-check configuration error."""


@dataclass(frozen=True)
class DatabaseEndpoint:
    host: str
    port: int
    database: str


def _postgres_scheme(scheme: str) -> bool:
    normalized = scheme.casefold()
    return normalized in {"postgres", "postgresql"} or normalized.startswith("postgresql+")


def _normalized_host(host: str) -> tuple[str, bool]:
    normalized = host.casefold().rstrip(".")
    if normalized == "localhost":
        return "loopback", True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized, False
    if address.is_loopback:
        return "loopback", True
    return address.compressed, False


def _database_endpoint(
    value: str,
    *,
    source: str,
    require_loopback: bool,
    require_test_marker: bool,
) -> DatabaseEndpoint:
    try:
        parsed = urlsplit(value)
        port = parsed.port or DEFAULT_POSTGRES_PORT
        host = parsed.hostname
        query_keys = {
            key.casefold() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
        }
    except (UnicodeError, ValueError) as exc:
        raise BackendCheckError(f"{source} is not a safely parseable PostgreSQL URL.") from exc

    if not _postgres_scheme(parsed.scheme):
        raise BackendCheckError(f"{source} must use PostgreSQL.")
    if parsed.fragment:
        raise BackendCheckError(f"{source} must not contain a URL fragment.")
    if query_keys & ENDPOINT_QUERY_OVERRIDES:
        raise BackendCheckError(
            f"{source} must declare host, port, and database only in the URL endpoint."
        )
    if host is None:
        raise BackendCheckError(f"{source} must declare an explicit loopback host.")

    normalized_host, is_loopback = _normalized_host(host)
    if require_loopback and not is_loopback:
        raise BackendCheckError(f"{source} must use a loopback PostgreSQL host.")

    decoded_path = unquote(parsed.path)
    if not decoded_path.startswith("/"):
        raise BackendCheckError(f"{source} must include a database name.")
    database = decoded_path[1:]
    if not database or "/" in database:
        raise BackendCheckError(f"{source} must include one explicit database name.")
    if require_test_marker and TEST_DATABASE_MARKER.search(database) is None:
        raise BackendCheckError(f"{source} database name must contain a standalone test marker.")

    return DatabaseEndpoint(
        host=normalized_host,
        port=port,
        database=database,
    )


def _canonical_test_alembic_url(value: str, *, source: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise BackendCheckError(f"{source} is not a safely parseable PostgreSQL URL.") from exc
    if parsed.scheme != "postgresql+asyncpg":
        raise BackendCheckError(
            f"{source} must use the explicit postgresql+asyncpg runtime driver."
        )

    decoded_outside_scheme = (
        unquote(parsed.netloc),
        unquote(parsed.path),
        unquote(parsed.query),
    )
    if any("+asyncpg" in component.casefold() for component in decoded_outside_scheme):
        raise BackendCheckError(f"{source} must not contain +asyncpg outside the driver scheme.")

    canonical = "postgresql+psycopg" + value[len(parsed.scheme) :]
    if value.replace("+asyncpg", "+psycopg") != canonical:
        raise BackendCheckError(f"{source} cannot be transformed into one exact Alembic URL.")
    return canonical


def _validated_test_endpoints(value: str, *, source: str) -> tuple[DatabaseEndpoint, ...]:
    runtime_endpoint = _database_endpoint(
        value,
        source=source,
        require_loopback=True,
        require_test_marker=True,
    )
    alembic_url = _canonical_test_alembic_url(value, source=source)
    alembic_endpoint = _database_endpoint(
        alembic_url,
        source=f"Alembic target derived from {source}",
        require_loopback=True,
        require_test_marker=True,
    )
    if alembic_endpoint != runtime_endpoint:
        raise BackendCheckError(
            f"Alembic target derived from {source} must match the runtime test endpoint."
        )
    return runtime_endpoint, alembic_endpoint


def _product_endpoints(value: str, *, source: str) -> tuple[DatabaseEndpoint, ...]:
    runtime_endpoint = _database_endpoint(
        value,
        source=source,
        require_loopback=False,
        require_test_marker=False,
    )
    alembic_endpoint = _database_endpoint(
        value.replace("+asyncpg", "+psycopg"),
        source=f"Alembic target derived from {source}",
        require_loopback=False,
        require_test_marker=False,
    )
    return runtime_endpoint, alembic_endpoint


def _dotenv_database_url(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise BackendCheckError(
            f"Cannot safely inspect product DATABASE_URL in {path.name}."
        ) from exc

    configured: str | None = None
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if candidate.startswith("export "):
            candidate = candidate.removeprefix("export ").lstrip()
        key, separator, raw_value = candidate.partition("=")
        if not separator or key.strip() != "DATABASE_URL":
            continue
        try:
            tokens = shlex.split(raw_value, comments=True, posix=True)
        except ValueError as exc:
            raise BackendCheckError(
                f"Cannot safely parse product DATABASE_URL in {path.name}."
            ) from exc
        if len(tokens) > 1:
            raise BackendCheckError(f"Cannot safely parse product DATABASE_URL in {path.name}.")
        configured = tokens[0].strip() if tokens else None
    return configured


def _product_database_urls(*, root: Path, environ: Mapping[str, str]) -> list[tuple[str, str]]:
    configured: list[tuple[str, str]] = []
    for filename in (".env", ".env.local"):
        value = _dotenv_database_url(root / filename)
        if value:
            configured.append((filename, value))
    ambient = environ.get("DATABASE_URL", "").strip()
    if ambient:
        configured.append(("ambient environment", ambient))
    return configured


def validated_test_database_url(
    *,
    root: Path,
    environ: Mapping[str, str],
    allow_ambient_test_target: bool = False,
) -> str:
    test_url = environ.get(TEST_DATABASE_ENV, "").strip()
    if not test_url:
        raise BackendCheckError(
            f"{TEST_DATABASE_ENV} is required and must target a dedicated test database."
        )

    test_endpoints = _validated_test_endpoints(
        test_url,
        source=TEST_DATABASE_ENV,
    )
    for source, product_url in _product_database_urls(root=root, environ=environ):
        product_endpoints = _product_endpoints(
            product_url,
            source=f"product DATABASE_URL from {source}",
        )
        if (
            allow_ambient_test_target
            and source == "ambient environment"
            and set(test_endpoints) == set(product_endpoints)
        ):
            continue
        if set(test_endpoints) & set(product_endpoints):
            raise BackendCheckError(
                f"{TEST_DATABASE_ENV} matches the product database endpoint from "
                f"{source}; use a separate dedicated test database."
            )
    return test_url


def apply_pytest_database_guard(
    *,
    root: Path = ROOT,
    environ: MutableMapping[str, str] | None = None,
) -> str:
    """Fail closed before pytest imports the application database engine.

    ``tests/conftest.py`` calls this function before importing anything from
    ``app``. The explicit test target is compared with product dotenv targets,
    then installed as the only runtime database target while provider, LLM, and
    write capabilities remain disabled.
    """

    target_environment = os.environ if environ is None else environ
    app_env = target_environment.get("APP_ENV", "").strip().casefold()
    if app_env != PYTEST_APP_ENV:
        raise BackendCheckError(
            f"pytest requires APP_ENV={PYTEST_APP_ENV} before application import."
        )

    test_url = validated_test_database_url(
        root=root,
        environ=target_environment,
        allow_ambient_test_target=True,
    )
    target_environment.update(
        {
            "APP_ENV": PYTEST_APP_ENV,
            "DATABASE_URL": test_url,
            "ENABLE_LLM": "false",
            "ENABLE_WRITE_ACTIONS": "false",
            "FOUNDEROS_DISABLE_DOTENV": "true",
            "FOUNDEROS_ENABLE_REAL_CONNECTORS": "false",
        }
    )
    return test_url


def _url_secret_fragments(value: str) -> set[str]:
    fragments = {value}
    try:
        parsed = urlsplit(value)
        query_items = parse_qsl(parsed.query, keep_blank_values=True)
    except ValueError:
        return fragments
    if parsed.password:
        fragments.add(parsed.password)
        fragments.add(unquote(parsed.password))
    for key, query_value in query_items:
        if key.casefold() in QUERY_SECRET_KEYS and query_value:
            fragments.add(query_value)
    for item in parsed.query.split("&"):
        raw_key, separator, raw_value = item.partition("=")
        if separator and unquote_plus(raw_key).casefold() in QUERY_SECRET_KEYS and raw_value:
            fragments.add(raw_value)
            fragments.add(unquote(raw_value))
            fragments.add(unquote_plus(raw_value))
    return fragments


def _sensitive_fragments(
    test_url: str,
    *,
    child_environment: Mapping[str, str],
    product_urls: tuple[str, ...],
) -> tuple[str, ...]:
    fragments = _url_secret_fragments(test_url)
    for product_url in product_urls:
        fragments.update(_url_secret_fragments(product_url))
    for key in PROXY_URL_ENVIRONMENT_KEYS:
        value = child_environment.get(key)
        if value:
            fragments.update(_url_secret_fragments(value))
    return tuple(sorted((item for item in fragments if item), key=len, reverse=True))


def _redact_fragment(output: str, fragment: str) -> str:
    if len(fragment) > 3:
        return output.replace(fragment, "[redacted]")
    standalone = re.compile(rf"(?<!\w){re.escape(fragment)}(?!\w)")
    return standalone.sub("[redacted]", output)


def _sanitized_output(output: str, *, sensitive_fragments: tuple[str, ...]) -> str:
    sanitized = output
    for fragment in sensitive_fragments:
        sanitized = _redact_fragment(sanitized, fragment)
    return POSTGRES_URL_PATTERN.sub("[redacted-postgresql-url]", sanitized)


def _reject_credentialed_proxies(environ: Mapping[str, str]) -> None:
    for key in PROXY_URL_ENVIRONMENT_KEYS:
        value = environ.get(key, "").strip()
        if not value:
            continue
        try:
            parsed = urlsplit(value)
            query_keys = {
                query_key.casefold()
                for query_key, _query_value in parse_qsl(
                    parsed.query,
                    keep_blank_values=True,
                )
            }
        except ValueError as exc:
            raise BackendCheckError(f"{key} is not a safely parseable proxy URL.") from exc
        if (
            parsed.username is not None
            or parsed.password is not None
            or "@" in unquote(value)
            or query_keys & QUERY_SECRET_KEYS
        ):
            raise BackendCheckError(f"{key} must not contain proxy credentials for backend-check.")


def _child_environment(*, environ: Mapping[str, str], test_url: str) -> dict[str, str]:
    _reject_credentialed_proxies(environ)
    child = {key: value for key, value in environ.items() if key in SAFE_CHILD_ENVIRONMENT_KEYS}
    child.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": test_url,
            "ENABLE_LLM": "false",
            "ENABLE_WRITE_ACTIONS": "false",
            "FOUNDEROS_CORS_ALLOWED_ORIGINS": TEST_CORS_ALLOWED_ORIGINS,
            "FOUNDEROS_DISABLE_DOTENV": "true",
            "FOUNDEROS_ENABLE_REAL_CONNECTORS": "false",
            TEST_DATABASE_ENV: test_url,
            "UV_NO_SYNC": "1",
        }
    )
    return child


def run_backend_check(
    *,
    root: Path = ROOT,
    environ: Mapping[str, str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    source_environment = os.environ if environ is None else environ
    test_url = validated_test_database_url(root=root, environ=source_environment)
    child_environment = _child_environment(
        environ=source_environment,
        test_url=test_url,
    )
    product_urls = tuple(
        value
        for _source, value in _product_database_urls(
            root=root,
            environ=source_environment,
        )
    )
    sensitive_fragments = _sensitive_fragments(
        test_url,
        child_environment=child_environment,
        product_urls=product_urls,
    )

    for index, (label, command) in enumerate(CHECK_COMMANDS, start=1):
        print(f"[backend-check] {index}/{len(CHECK_COMMANDS)} {label}")
        try:
            completed = runner(
                command,
                cwd=root,
                env=child_environment,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise BackendCheckError(f"Unable to start backend-check step: {label}.") from exc

        if completed.stdout:
            sys.stdout.write(
                _sanitized_output(
                    completed.stdout,
                    sensitive_fragments=sensitive_fragments,
                )
            )
        if completed.stderr:
            sys.stderr.write(
                _sanitized_output(
                    completed.stderr,
                    sensitive_fragments=sensitive_fragments,
                )
            )
        if completed.returncode != 0:
            print(
                f"ERROR: backend-check step failed: {label} (exit {completed.returncode}).",
                file=sys.stderr,
            )
            return completed.returncode if completed.returncode > 0 else 1

    print("[backend-check] all backend gates passed")
    return 0


def main() -> int:
    try:
        return run_backend_check()
    except BackendCheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
