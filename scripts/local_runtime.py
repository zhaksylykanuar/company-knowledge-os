"""Safe local FounderOS runtime orchestration.

The module intentionally keeps every local operation bounded to loopback
infrastructure. It can reuse an already-running Postgres, start the repository
Compose services only when the configured local database is unavailable, take
credential-safe logical backups, supervise the backend/frontend process pair,
and expose read-only doctor/smoke commands.

No command in this module prints environment values, database URLs, passwords,
API keys, invite tokens, or response bodies.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

LOCAL_APP_ENVS = frozenset({"local", "dev", "development", "test"})
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DATABASE_ENDPOINT_QUERY_KEYS = frozenset(
    {
        "host",
        "hostaddr",
        "port",
        "database",
        "dbname",
        "service",
        "servicefile",
    }
)

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8765
WEB_HOST = "127.0.0.1"
WEB_PORT = 3000
BACKEND_BASE_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
WEB_BIND_BASE_URL = f"http://{WEB_HOST}:{WEB_PORT}"
# Browser, session-cookie, and one-time invite traffic must use the exact IPv4
# loopback address owned by the Next.js listener. ``localhost`` may resolve to
# an independently occupied IPv6 listener and must not receive bearer fragments.
WEB_BASE_URL = WEB_BIND_BASE_URL

RUNTIME_STATE_RELATIVE = Path(".local/runtime.json")
BACKUP_DIR_RELATIVE = Path(".local/backups")
BACKUP_SUFFIX = ".dump"
BACKUP_FORMAT_VERSION = 2
COMPOSE_POSTGRES_MAJOR = 16
TEMP_RESTORE_DB_PREFIX = "founderos_restore_verify_"
TEMP_RESTORE_DB_RE = re.compile(r"^founderos_restore_verify_[0-9a-f]{32}$")
TEMP_RESTORE_CLUSTER_RE = re.compile(r"^\.restore-cluster-[0-9a-f]{32}$")
TEMP_RESTORE_SOCKET_MARKER = ".founderos-socket-dir"
FRONTEND_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "COLORTERM",
        "CI",
        "NO_COLOR",
        "FORCE_COLOR",
        "NODE_EXTRA_CA_CERTS",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
)


class LocalRuntimeError(RuntimeError):
    """A sanitized local-runtime failure safe to show to an operator."""


class TemporaryRestoreCleanupError(LocalRuntimeError):
    """A restore verifier is still running or could not be proven removed."""


@dataclass(frozen=True)
class DatabaseProbe:
    reachable: bool
    has_public_tables: bool = False


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class RuntimeState:
    supervisor_pid: int
    backend_pid: int
    frontend_pid: int
    started_at: str
    repo_root: str
    supervisor_start_signature: str
    backend_start_signature: str | None = None
    frontend_start_signature: str | None = None


@dataclass(frozen=True)
class FounderDestination:
    url: str
    invite_id: UUID | None


@dataclass(frozen=True)
class DatabaseSnapshot:
    server_major: int
    alembic_revisions: tuple[str, ...]
    table_counts: dict[str, int]


@dataclass(frozen=True)
class CredentialDecryptabilityProof:
    connection_count: int
    real_connection_count: int
    fixture_connection_count: int
    encrypted_field_count: int
    verified_field_count: int
    fixture_field_count: int
    failure_count: int

    def aggregate_dict(self) -> dict[str, int | bool]:
        return {
            "connection_count": self.connection_count,
            "real_connection_count": self.real_connection_count,
            "fixture_connection_count": self.fixture_connection_count,
            "encrypted_field_count": self.encrypted_field_count,
            "verified_field_count": self.verified_field_count,
            "fixture_field_count": self.fixture_field_count,
            "failure_count": self.failure_count,
            "verified": self.failure_count == 0,
        }


@dataclass(frozen=True)
class RawStorageEntry:
    source_path: Path
    archive_name: str
    kind: str
    size: int
    sha256: str | None = None


@dataclass(frozen=True)
class RawStorageInventory:
    source_state: str
    entries: tuple[RawStorageEntry, ...]
    file_count: int
    directory_count: int
    total_bytes: int
    inventory_sha256: str


def _is_loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    normalized = host.strip().strip("[]").casefold()
    if normalized in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def database_url(value: str) -> URL:
    try:
        parsed = make_url(value)
    except Exception as exc:  # SQLAlchemy errors can contain the rejected URL.
        raise LocalRuntimeError("DATABASE_URL is not a valid database URL.") from exc
    if not parsed.drivername.startswith("postgresql"):
        raise LocalRuntimeError("Local FounderOS requires a PostgreSQL DATABASE_URL.")
    query_keys = {str(key).strip().casefold() for key in parsed.query}
    if query_keys & DATABASE_ENDPOINT_QUERY_KEYS:
        raise LocalRuntimeError(
            "DATABASE_URL query parameters must not override the PostgreSQL "
            "endpoint, database, or service in canonical local mode."
        )
    return parsed


def database_is_loopback(value: str) -> bool:
    return _is_loopback_host(database_url(value).host)


def validate_local_settings(config: Any) -> URL:
    app_env = str(config.app_env).strip().casefold()
    if app_env not in LOCAL_APP_ENVS:
        raise LocalRuntimeError(
            "Local runtime refused to start because APP_ENV is not local/dev/test."
        )
    parsed = database_url(str(config.database_url))
    if not _is_loopback_host(parsed.host):
        raise LocalRuntimeError(
            "Local runtime refused to access a non-loopback PostgreSQL database."
        )
    enabled_gates = [
        name
        for name, enabled in (
            ("ENABLE_LLM", bool(getattr(config, "enable_llm", False))),
            (
                "ENABLE_WRITE_ACTIONS",
                bool(getattr(config, "enable_write_actions", False)),
            ),
            (
                "FOUNDEROS_ENABLE_REAL_CONNECTORS",
                bool(getattr(config, "enable_real_connectors", False)),
            ),
        )
        if enabled
    ]
    if enabled_gates:
        raise LocalRuntimeError(
            "Canonical local startup requires external capability gates to be "
            "disabled; use a separately approved bounded runbook. Enabled names: "
            + ", ".join(enabled_gates)
        )
    return parsed


async def _probe_database_async(value: str) -> DatabaseProbe:
    engine = None
    try:
        engine = create_async_engine(value, pool_pre_ping=True)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            has_tables = bool(
                await connection.scalar(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                              AND table_type = 'BASE TABLE'
                        )
                        """
                    )
                )
            )
        return DatabaseProbe(reachable=True, has_public_tables=has_tables)
    except Exception:
        return DatabaseProbe(reachable=False)
    finally:
        if engine is not None:
            await engine.dispose()


def probe_database(value: str) -> DatabaseProbe:
    return asyncio.run(_probe_database_async(value))


async def _database_server_major_async(value: str) -> int:
    engine = create_async_engine(value, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            version_number = int(await connection.scalar(text("SHOW server_version_num")) or 0)
        major = version_number // 10000
        if major <= 0:
            raise LocalRuntimeError("The PostgreSQL server major version could not be verified.")
        return major
    except LocalRuntimeError:
        raise
    except Exception as exc:
        raise LocalRuntimeError(
            "The PostgreSQL server major version could not be verified."
        ) from exc
    finally:
        await engine.dispose()


def database_server_major(value: str) -> int:
    return asyncio.run(_database_server_major_async(value))


def _evaluate_credential_decryptability(
    rows: Sequence[tuple[str | None, str | None, Any]],
    *,
    decryptor: Callable[[str], str],
) -> CredentialDecryptabilityProof:
    connection_count = 0
    real_connection_count = 0
    fixture_connection_count = 0
    encrypted_field_count = 0
    verified_field_count = 0
    fixture_field_count = 0
    failure_count = 0

    for access_token, refresh_token, metadata in rows:
        encrypted_values = tuple(
            value for value in (access_token, refresh_token) if value is not None
        )
        if not encrypted_values:
            continue
        connection_count += 1
        encrypted_field_count += len(encrypted_values)
        connection_method = (
            metadata.get("connection_method") if isinstance(metadata, dict) else None
        )
        if connection_method == "test":
            fixture_connection_count += 1
            fixture_field_count += len(encrypted_values)
            continue

        real_connection_count += 1
        for value in encrypted_values:
            try:
                plaintext = decryptor(value)
                if not plaintext:
                    raise ValueError("empty decrypted secret")
                verified_field_count += 1
                del plaintext
            except Exception:
                failure_count += 1

    return CredentialDecryptabilityProof(
        connection_count=connection_count,
        real_connection_count=real_connection_count,
        fixture_connection_count=fixture_connection_count,
        encrypted_field_count=encrypted_field_count,
        verified_field_count=verified_field_count,
        fixture_field_count=fixture_field_count,
        failure_count=failure_count,
    )


async def _credential_decryptability_proof_async(
    value: str,
    config: Any,
) -> CredentialDecryptabilityProof:
    from app.services.secret_encryption import decrypt_secret

    engine = create_async_engine(value, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            table_exists = await connection.scalar(
                text("SELECT to_regclass('public.integration_connections')")
            )
            if table_exists is None:
                rows: list[tuple[str | None, str | None, Any]] = []
            else:
                result = await connection.execute(
                    text(
                        """
                        SELECT encrypted_access_token, encrypted_refresh_token, metadata
                        FROM integration_connections
                        WHERE encrypted_access_token IS NOT NULL
                           OR encrypted_refresh_token IS NOT NULL
                        """
                    )
                )
                rows = [(row[0], row[1], row[2]) for row in result]
    except Exception as exc:
        raise LocalRuntimeError(
            "Encrypted connector credential readiness could not be verified."
        ) from exc
    finally:
        await engine.dispose()

    return _evaluate_credential_decryptability(
        rows,
        decryptor=lambda encrypted: decrypt_secret(encrypted, config=config),
    )


def verify_persisted_connector_credentials(
    value: str,
    config: Any,
) -> CredentialDecryptabilityProof:
    proof = asyncio.run(_credential_decryptability_proof_async(value, config))
    if proof.failure_count:
        raise LocalRuntimeError(
            "Persisted encrypted connector credentials cannot be decrypted with the "
            "current local key. No verified backup receipt was created."
        )
    return proof


def tcp_port_in_use(host: str, port: int) -> bool:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, socktype, proto, _canonical_name, sockaddr in addresses:
        with socket.socket(family, socktype, proto) as sock:
            sock.settimeout(0.35)
            if sock.connect_ex(sockaddr) == 0:
                return True
    return False


def command_available(command: str) -> bool:
    return shutil.which(command) is not None


def process_inspection_available() -> bool:
    if not command_available("ps"):
        return False
    return (Path("/proc") / str(os.getpid()) / "cwd").exists() or command_available("lsof")


def docker_daemon_available(root: Path) -> bool:
    if not command_available("docker"):
        return False
    completed = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def frontend_dependencies_present(root: Path) -> bool:
    return (root / "web/node_modules/.bin/next").is_file()


def frontend_install_command(root: Path) -> list[str]:
    if frontend_dependencies_present(root):
        return []
    if (root / "web/package-lock.json").is_file():
        return ["npm", "ci"]
    return ["npm", "install"]


def _postgres_port(parsed: URL) -> int:
    return int(parsed.port or 5432)


def collect_doctor_checks(root: Path, config: Any) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    for command in ("uv", "node", "npm"):
        available = command_available(command)
        checks.append(
            DoctorCheck(
                name=command,
                status="ok" if available else "fail",
                detail="available" if available else "not installed",
            )
        )

    process_inspection = process_inspection_available()
    checks.append(
        DoctorCheck(
            name="process-inspection",
            status="ok" if process_inspection else "fail",
            detail=(
                "safe runtime ownership checks available"
                if process_inspection
                else "ps plus /proc or lsof is required for safe shutdown"
            ),
        )
    )

    try:
        parsed = validate_local_settings(config)
    except LocalRuntimeError as exc:
        checks.append(DoctorCheck("runtime-scope", "fail", str(exc)))
        return checks

    checks.append(
        DoctorCheck(
            "runtime-scope",
            "ok",
            "loopback PostgreSQL; external capability gates disabled",
        )
    )
    probe = probe_database(str(config.database_url))
    required_postgres_major: int | None = COMPOSE_POSTGRES_MAJOR
    if probe.reachable:
        checks.append(DoctorCheck("postgres", "ok", "configured local database is reachable"))
        try:
            required_postgres_major = database_server_major(str(config.database_url))
        except LocalRuntimeError as exc:
            required_postgres_major = None
            checks.append(DoctorCheck("postgres-server-major", "fail", str(exc)))
        else:
            checks.append(
                DoctorCheck(
                    "postgres-server-major",
                    "ok",
                    f"reachable server major is PostgreSQL {required_postgres_major}",
                )
            )
        try:
            credential_proof = verify_persisted_connector_credentials(
                str(config.database_url), config
            )
        except LocalRuntimeError:
            checks.append(
                DoctorCheck(
                    "credential-decryptability",
                    "fail",
                    "real persisted encrypted connector credentials failed verification",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "credential-decryptability",
                    "ok",
                    "aggregate credential proof: "
                    f"{credential_proof.verified_field_count} real fields verified; "
                    f"{credential_proof.fixture_field_count} test fixture fields ignored",
                )
            )
    else:
        port_busy = tcp_port_in_use(parsed.host or BACKEND_HOST, _postgres_port(parsed))
        if port_busy:
            checks.append(
                DoctorCheck(
                    "postgres",
                    "fail",
                    "configured database is unreachable but its local port is occupied",
                )
            )
        elif docker_daemon_available(root):
            checks.append(
                DoctorCheck(
                    "postgres",
                    "warn",
                    "database is offline; Compose fallback is available for make local",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "postgres",
                    "fail",
                    "database is offline and Docker Compose is unavailable",
                )
            )
        checks.append(
            DoctorCheck(
                "postgres-server-major",
                "warn",
                f"database offline; Compose baseline is PostgreSQL {COMPOSE_POSTGRES_MAJOR}",
            )
        )

    for command in (
        "pg_dump",
        "pg_restore",
        "createdb",
        "dropdb",
        "initdb",
        "pg_ctl",
        "postgres",
    ):
        available = command_available(command)
        if not available:
            status = "fail" if probe.has_public_tables else "warn"
            detail = "required for a full verified database backup"
        else:
            try:
                tool_major = _postgres_tool_major(command)
            except LocalRuntimeError:
                status = "fail"
                detail = "version could not be verified"
            else:
                matches = (
                    required_postgres_major is not None and tool_major == required_postgres_major
                )
                status = "ok" if matches else "fail"
                if required_postgres_major is None:
                    detail = f"PostgreSQL {tool_major}; server major comparison unavailable"
                elif matches:
                    detail = f"PostgreSQL {tool_major}; matches required major"
                else:
                    detail = (
                        f"PostgreSQL {tool_major}; required major is "
                        f"PostgreSQL {required_postgres_major}"
                    )
        checks.append(DoctorCheck(command, status, detail))

    install = frontend_install_command(root)
    checks.append(
        DoctorCheck(
            "web-dependencies",
            "ok" if not install else "warn",
            "already installed" if not install else f"make local will run {' '.join(install)}",
        )
    )

    for name, host, port in (
        ("backend-port", BACKEND_HOST, BACKEND_PORT),
        ("web-port", WEB_HOST, WEB_PORT),
    ):
        busy = tcp_port_in_use(host, port)
        checks.append(
            DoctorCheck(
                name,
                "fail" if busy else "ok",
                f"{port} is already in use" if busy else f"{port} is free",
            )
        )
    return checks


def print_doctor_checks(checks: Sequence[DoctorCheck]) -> bool:
    print("FounderOS local doctor")
    for check in checks:
        print(f"  [{check.status.upper()}] {check.name}: {check.detail}")
    return not any(check.status == "fail" for check in checks)


def _run_checked_quiet(
    command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None
) -> None:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        executable = Path(command[0]).name if command else "command"
        raise LocalRuntimeError(f"{executable} failed with exit code {completed.returncode}.")


def ensure_database(root: Path, config: Any, *, timeout_seconds: float = 60.0) -> DatabaseProbe:
    parsed = validate_local_settings(config)
    probe = probe_database(str(config.database_url))
    if probe.reachable:
        print("Local Postgres: reusing the configured running database.")
        return probe

    host = parsed.host or BACKEND_HOST
    port = _postgres_port(parsed)
    if tcp_port_in_use(host, port):
        raise LocalRuntimeError(
            "PostgreSQL is unreachable, but its configured loopback port is occupied. "
            "FounderOS will not replace or stop that process."
        )
    if not docker_daemon_available(root):
        raise LocalRuntimeError(
            "PostgreSQL is offline and Docker Compose is unavailable. Start Docker Desktop "
            "or a compatible local PostgreSQL server, then retry."
        )

    print("Local Postgres: starting the repository Compose database.")
    _run_checked_quiet(["docker", "compose", "up", "-d", "postgres"], cwd=root)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        probe = probe_database(str(config.database_url))
        if probe.reachable:
            print("Local Postgres: ready.")
            return probe
        time.sleep(0.5)
    raise LocalRuntimeError("Local PostgreSQL did not become ready before the timeout.")


def ensure_frontend_dependencies(root: Path) -> None:
    command = frontend_install_command(root)
    if not command:
        print("Web dependencies: already installed.")
        return
    if not command_available("npm"):
        raise LocalRuntimeError("npm is required to install the web dependencies.")
    print(f"Web dependencies: running {' '.join(command)} from the lockfile.")
    completed = subprocess.run(
        command,
        cwd=root / "web",
        check=False,
        env=frontend_environment(),
    )
    if completed.returncode != 0:
        raise LocalRuntimeError(
            f"Web dependency installation failed with exit code {completed.returncode}."
        )


def _pg_environment(parsed: URL, *, database: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    query_host = parsed.query.get("host")
    query_port = parsed.query.get("port")
    values = {
        "PGHOST": parsed.host or (str(query_host) if query_host else ""),
        "PGPORT": str(parsed.port or query_port or 5432),
        "PGUSER": parsed.username or "",
        "PGPASSWORD": parsed.password or "",
        "PGDATABASE": database if database is not None else (parsed.database or ""),
    }
    for key, value in values.items():
        if value:
            env[key] = value
        else:
            env.pop(key, None)
    sslmode = parsed.query.get("sslmode")
    if sslmode:
        env["PGSSLMODE"] = str(sslmode)
    return env


def build_pg_dump_command(binary: str, output_path: Path) -> list[str]:
    return [
        binary,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--file",
        str(output_path),
    ]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_stream(stream: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _sha256_raw_file(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalRuntimeError("Raw storage file changed type during inventory.")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return _sha256_stream(stream)
    finally:
        os.close(descriptor)


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _write_checksum(path: Path) -> tuple[Path, str]:
    digest = _sha256_file(path)
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    checksum_path.chmod(0o600)
    return checksum_path, digest


def _verify_checksum(path: Path, checksum_path: Path) -> str:
    try:
        parts = checksum_path.read_text(encoding="utf-8").strip().split()
    except OSError as exc:
        raise LocalRuntimeError("Backup checksum could not be read.") from exc
    if len(parts) != 2 or parts[1] != path.name or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
        raise LocalRuntimeError("Backup checksum file is invalid.")
    actual = _sha256_file(path)
    if not hmac.compare_digest(parts[0], actual):
        raise LocalRuntimeError("Backup checksum verification failed.")
    return actual


def _backup_tools() -> dict[str, str]:
    tools: dict[str, str] = {}
    required = ("pg_dump", "pg_restore", "createdb", "dropdb", "initdb", "pg_ctl", "postgres")
    for name in required:
        binary = shutil.which(name)
        if binary is None:
            raise LocalRuntimeError(
                "A matching local PostgreSQL toolchain is required for a full backup proof."
            )
        tools[name] = binary
    return tools


def _postgres_tool_major(binary: str) -> int:
    completed = subprocess.run(
        [binary, "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise LocalRuntimeError("A PostgreSQL backup tool version could not be verified.")
    match = re.search(r"\b(\d+)(?:\.\d+)*\b", completed.stdout)
    if match is None:
        raise LocalRuntimeError("A PostgreSQL backup tool version could not be parsed.")
    return int(match.group(1))


def _database_url_for(parsed: URL, database: str) -> str:
    return parsed.set(database=database).render_as_string(hide_password=False)


async def _database_snapshot_async(value: str) -> DatabaseSnapshot:
    engine = create_async_engine(value, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            version_number = int(await connection.scalar(text("SHOW server_version_num")) or 0)
            server_major = version_number // 10000
            table_names = list(
                await connection.scalars(
                    text(
                        """
                        SELECT tablename
                        FROM pg_catalog.pg_tables
                        WHERE schemaname = 'public'
                        ORDER BY tablename
                        """
                    )
                )
            )
            table_counts: dict[str, int] = {}
            preparer = connection.dialect.identifier_preparer
            for table_name in table_names:
                name = str(table_name)
                quoted = preparer.quote_identifier(name)
                table_counts[name] = int(
                    await connection.scalar(text(f"SELECT count(*) FROM {quoted}")) or 0
                )
            revisions: tuple[str, ...] = ()
            if "alembic_version" in table_counts:
                revisions = tuple(
                    sorted(
                        str(value)
                        for value in await connection.scalars(
                            text("SELECT version_num FROM alembic_version")
                        )
                    )
                )
            return DatabaseSnapshot(
                server_major=server_major,
                alembic_revisions=revisions,
                table_counts=table_counts,
            )
    except Exception as exc:
        raise LocalRuntimeError("Database backup proof could not read aggregate state.") from exc
    finally:
        await engine.dispose()


def database_snapshot(value: str) -> DatabaseSnapshot:
    return asyncio.run(_database_snapshot_async(value))


def _compare_database_snapshots(source: DatabaseSnapshot, restored: DatabaseSnapshot) -> None:
    if source.server_major != restored.server_major:
        raise LocalRuntimeError("Restored database server major does not match the local source.")
    if source.alembic_revisions != restored.alembic_revisions:
        raise LocalRuntimeError("Restored database Alembic revision does not match the source.")
    if source.table_counts != restored.table_counts:
        raise LocalRuntimeError("Restored database aggregate table counts do not match the source.")


def _reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((BACKEND_HOST, 0))
        return int(listener.getsockname()[1])


def _restore_socket_prefix(root: Path) -> str:
    root_digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"fos-restore-{root_digest}-"


def _create_private_restore_socket_dir(root: Path) -> Path:
    path = Path(
        tempfile.mkdtemp(
            prefix=_restore_socket_prefix(root),
            dir=tempfile.gettempdir(),
        )
    )
    path.chmod(0o700)
    return path


def _validated_restore_socket_dir(root: Path, value: str) -> Path:
    path = Path(value)
    temporary_root = Path(tempfile.gettempdir()).resolve()
    try:
        metadata = path.lstat()
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise TemporaryRestoreCleanupError(
            "Temporary restore socket directory could not be verified."
        ) from exc
    if (
        parent != temporary_root
        or not path.name.startswith(_restore_socket_prefix(root))
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
    ):
        raise TemporaryRestoreCleanupError(
            "Temporary restore socket directory ownership could not be verified."
        )
    return path


def _temporary_cluster_running(pg_ctl: str, cluster_dir: Path) -> bool:
    completed = subprocess.run(
        [pg_ctl, "-D", str(cluster_dir), "status"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def _stop_and_remove_temporary_cluster(
    *,
    root: Path,
    cluster_dir: Path,
    pg_ctl: str,
    socket_dir: Path | None = None,
) -> None:
    if _temporary_cluster_running(pg_ctl, cluster_dir):
        stopped = subprocess.run(
            [pg_ctl, "-D", str(cluster_dir), "-m", "fast", "-w", "stop"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if stopped.returncode != 0:
            subprocess.run(
                [pg_ctl, "-D", str(cluster_dir), "-m", "immediate", "-w", "stop"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
    if _temporary_cluster_running(pg_ctl, cluster_dir):
        raise TemporaryRestoreCleanupError(
            "Temporary restore PostgreSQL could not be stopped safely."
        )
    if cluster_dir.exists():
        try:
            shutil.rmtree(cluster_dir)
        except OSError as exc:
            raise TemporaryRestoreCleanupError(
                "Temporary restore PostgreSQL files could not be removed."
            ) from exc
    if cluster_dir.exists():
        raise TemporaryRestoreCleanupError(
            "Temporary restore PostgreSQL files could not be removed."
        )
    if socket_dir is not None and socket_dir.exists():
        verified_socket_dir = _validated_restore_socket_dir(root, str(socket_dir))
        try:
            shutil.rmtree(verified_socket_dir)
        except OSError as exc:
            raise TemporaryRestoreCleanupError(
                "Temporary restore PostgreSQL socket files could not be removed."
            ) from exc
    if socket_dir is not None and socket_dir.exists():
        raise TemporaryRestoreCleanupError(
            "Temporary restore PostgreSQL socket files could not be removed."
        )


def recover_stale_restore_clusters(root: Path, *, pg_ctl: str | None = None) -> None:
    backup_root = root / BACKUP_DIR_RELATIVE
    if not backup_root.exists():
        return
    clusters = sorted(
        path
        for partial in backup_root.glob("founderos-*.partial")
        if partial.is_dir() and not partial.is_symlink()
        for path in partial.iterdir()
        if TEMP_RESTORE_CLUSTER_RE.fullmatch(path.name)
    )
    if not clusters:
        return
    binary = pg_ctl or shutil.which("pg_ctl")
    if binary is None:
        raise TemporaryRestoreCleanupError(
            "A stale temporary restore was found, but pg_ctl is unavailable."
        )
    for cluster_dir in clusters:
        if cluster_dir.is_symlink() or not cluster_dir.is_dir():
            raise TemporaryRestoreCleanupError(
                "A stale temporary restore directory could not be verified."
            )
        if _temporary_cluster_running(binary, cluster_dir):
            raise TemporaryRestoreCleanupError(
                "A temporary restore PostgreSQL is still running; startup refused "
                "to treat it as stale."
            )
        marker = cluster_dir / TEMP_RESTORE_SOCKET_MARKER
        socket_dir: Path | None = None
        if marker.exists():
            if marker.is_symlink() or not marker.is_file():
                raise TemporaryRestoreCleanupError(
                    "A stale temporary restore socket marker could not be verified."
                )
            try:
                marker_value = marker.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise TemporaryRestoreCleanupError(
                    "A stale temporary restore socket marker could not be read."
                ) from exc
            socket_dir = _validated_restore_socket_dir(root, marker_value)
        _stop_and_remove_temporary_cluster(
            root=root,
            cluster_dir=cluster_dir,
            pg_ctl=binary,
            socket_dir=socket_dir,
        )


def _temporary_restore_signals() -> tuple[signal.Signals, ...]:
    values = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        values.append(signal.SIGHUP)
    return tuple(values)


def _install_restore_signal_handlers() -> dict[signal.Signals, Any]:
    previous: dict[signal.Signals, Any] = {}

    def interrupted(_signum: int, _frame: Any) -> None:
        raise LocalRuntimeError(
            "Local backup was interrupted; temporary restore cleanup was required."
        )

    try:
        for current_signal in _temporary_restore_signals():
            previous[current_signal] = signal.signal(current_signal, interrupted)
    except ValueError:
        for current_signal, handler in previous.items():
            signal.signal(current_signal, handler)
        return {}
    return previous


def _set_restore_cleanup_signal_policy(
    previous: dict[signal.Signals, Any],
    handler: Any,
) -> None:
    for current_signal in previous:
        signal.signal(current_signal, handler)


def _restore_and_compare_database(
    *,
    root: Path,
    parsed: URL,
    dump_path: Path,
    source_snapshot: DatabaseSnapshot,
    tools: dict[str, str],
    config: Any,
) -> dict[str, Any]:
    database_name = f"{TEMP_RESTORE_DB_PREFIX}{uuid4().hex}"
    if TEMP_RESTORE_DB_RE.fullmatch(database_name) is None:
        raise LocalRuntimeError("Temporary restore database name validation failed.")
    cluster_dir = dump_path.parent / f".restore-cluster-{uuid4().hex}"
    cluster_log = dump_path.parent / f".restore-postgres-{uuid4().hex}.log"
    socket_dir = _create_private_restore_socket_dir(root)
    restore_user = "founderos_verify"
    temporary_url = URL.create(
        drivername=parsed.drivername,
        username=restore_user,
        database=database_name,
        query={"host": str(socket_dir)},
    )
    database_created = False
    restored_snapshot: DatabaseSnapshot | None = None
    restored_credential_proof: CredentialDecryptabilityProof | None = None
    previous_signal_handlers = _install_restore_signal_handlers()
    try:
        _run_checked_quiet(
            [
                tools["initdb"],
                "-D",
                str(cluster_dir),
                "--auth-local=trust",
                "--auth-host=reject",
                "--no-locale",
                "--encoding=UTF8",
                f"--username={restore_user}",
                "--no-sync",
            ],
            cwd=root,
        )
        socket_marker = cluster_dir / TEMP_RESTORE_SOCKET_MARKER
        socket_marker.write_text(str(socket_dir) + "\n", encoding="utf-8")
        socket_marker.chmod(0o600)
        server_options = f"-c listen_addresses='' -c unix_socket_directories='{socket_dir}' -F"
        _run_checked_quiet(
            [
                tools["pg_ctl"],
                "-D",
                str(cluster_dir),
                "-l",
                str(cluster_log),
                "-o",
                server_options,
                "-w",
                "start",
            ],
            cwd=root,
        )
        _run_checked_quiet(
            [tools["createdb"], "--maintenance-db=postgres", database_name],
            cwd=root,
            env=_pg_environment(temporary_url, database="postgres"),
        )
        database_created = True
        _run_checked_quiet(
            [
                tools["pg_restore"],
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                database_name,
                str(dump_path),
            ],
            cwd=root,
            env=_pg_environment(temporary_url, database=database_name),
        )
        restored_snapshot = database_snapshot(temporary_url.render_as_string(hide_password=False))
        _compare_database_snapshots(source_snapshot, restored_snapshot)
        restored_credential_proof = verify_persisted_connector_credentials(
            temporary_url.render_as_string(hide_password=False),
            config,
        )
    finally:
        signal_received_during_cleanup = False

        def defer_interruption(_signum: int, _frame: Any) -> None:
            nonlocal signal_received_during_cleanup
            signal_received_during_cleanup = True

        _set_restore_cleanup_signal_policy(
            previous_signal_handlers,
            defer_interruption,
        )
        try:
            if database_created and _temporary_cluster_running(tools["pg_ctl"], cluster_dir):
                subprocess.run(
                    [
                        tools["dropdb"],
                        "--if-exists",
                        "--force",
                        "--maintenance-db=postgres",
                        database_name,
                    ],
                    cwd=root,
                    env=_pg_environment(temporary_url, database="postgres"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
            _stop_and_remove_temporary_cluster(
                root=root,
                cluster_dir=cluster_dir,
                pg_ctl=tools["pg_ctl"],
                socket_dir=socket_dir,
            )
            cluster_log.unlink(missing_ok=True)
        finally:
            for current_signal, handler in previous_signal_handlers.items():
                signal.signal(current_signal, handler)
        if signal_received_during_cleanup:
            raise LocalRuntimeError("Local backup was interrupted after temporary restore cleanup.")
    if restored_snapshot is None or restored_credential_proof is None:
        raise LocalRuntimeError("Temporary database restore proof did not complete.")
    return {
        "server_major": source_snapshot.server_major,
        "alembic_revisions": list(source_snapshot.alembic_revisions),
        "table_counts": dict(sorted(source_snapshot.table_counts.items())),
        "table_count": len(source_snapshot.table_counts),
        "total_rows": sum(source_snapshot.table_counts.values()),
        "temporary_database_dropped": True,
        "restore_transport": "private_unix_socket",
        "tcp_listen": False,
        "restored_credential_decryptability": (restored_credential_proof.aggregate_dict()),
    }


def _raw_inventory_digest(entries: Sequence[RawStorageEntry]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: (item.archive_name, item.kind)):
        digest.update(entry.archive_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(entry.kind.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(entry.size).encode("ascii"))
        digest.update(b"\0")
        digest.update((entry.sha256 or "-").encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _configured_raw_storage_path(root: Path, config: Any) -> Path:
    configured = Path(str(getattr(config, "raw_storage_dir", "./raw_storage"))).expanduser()
    return configured if configured.is_absolute() else root / configured


def scan_raw_storage(root: Path, config: Any) -> RawStorageInventory:
    source = _configured_raw_storage_path(root, config)
    if source.is_symlink():
        raise LocalRuntimeError("Raw storage snapshot refused a symbolic link.")
    if not source.exists():
        return RawStorageInventory("missing", (), 0, 0, 0, _raw_inventory_digest(()))
    if not source.is_dir():
        raise LocalRuntimeError("Configured raw storage is not a directory.")
    resolved_source = source.resolve(strict=True)
    resolved_backup = (root / BACKUP_DIR_RELATIVE).resolve(strict=False)
    if resolved_backup == resolved_source or resolved_backup.is_relative_to(resolved_source):
        raise LocalRuntimeError("Raw storage cannot contain the local backup directory.")

    entries: list[RawStorageEntry] = []
    for directory, directory_names, file_names in os.walk(source, followlinks=False):
        current = Path(directory)
        directory_names.sort()
        file_names.sort()
        for name in directory_names:
            path = current / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise LocalRuntimeError("Raw storage snapshot refused a symbolic link.")
            if not stat.S_ISDIR(metadata.st_mode):
                raise LocalRuntimeError("Raw storage contains an unsupported directory entry.")
            relative = path.relative_to(source).as_posix()
            entries.append(RawStorageEntry(path, relative, "directory", 0))
        for name in file_names:
            path = current / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise LocalRuntimeError("Raw storage snapshot refused a symbolic link.")
            if not stat.S_ISREG(metadata.st_mode):
                raise LocalRuntimeError("Raw storage contains an unsupported file entry.")
            relative = path.relative_to(source).as_posix()
            entries.append(
                RawStorageEntry(
                    path,
                    relative,
                    "file",
                    metadata.st_size,
                    _sha256_raw_file(path),
                )
            )
    frozen = tuple(entries)
    return RawStorageInventory(
        source_state="present",
        entries=frozen,
        file_count=sum(entry.kind == "file" for entry in frozen),
        directory_count=sum(entry.kind == "directory" for entry in frozen),
        total_bytes=sum(entry.size for entry in frozen if entry.kind == "file"),
        inventory_sha256=_raw_inventory_digest(frozen),
    )


def _create_raw_storage_archive(path: Path, inventory: RawStorageInventory) -> None:
    with tarfile.open(path, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        for entry in inventory.entries:
            metadata = entry.source_path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise LocalRuntimeError("Raw storage changed to a symbolic link during backup.")
            expected_regular = entry.kind == "file" and stat.S_ISREG(metadata.st_mode)
            expected_directory = entry.kind == "directory" and stat.S_ISDIR(metadata.st_mode)
            if not (expected_regular or expected_directory):
                raise LocalRuntimeError("Raw storage changed type during backup.")
            archive.add(
                entry.source_path,
                arcname=f"raw_storage/{entry.archive_name}",
                recursive=False,
            )
    path.chmod(0o600)


def _verify_raw_storage_archive(path: Path, expected: RawStorageInventory) -> None:
    entries: list[RawStorageEntry] = []
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive.getmembers():
                parts = Path(member.name).parts
                if (
                    member.name.startswith("/")
                    or ".." in parts
                    or len(parts) < 2
                    or parts[0] != "raw_storage"
                    or member.issym()
                    or member.islnk()
                ):
                    raise LocalRuntimeError("Raw storage archive contains an unsafe entry.")
                relative = Path(*parts[1:]).as_posix()
                if member.isfile():
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise LocalRuntimeError(
                            "Raw storage archive file content could not be verified."
                        )
                    with extracted:
                        content_digest = _sha256_stream(extracted)
                    entries.append(
                        RawStorageEntry(
                            Path(),
                            relative,
                            "file",
                            member.size,
                            content_digest,
                        )
                    )
                elif member.isdir():
                    entries.append(RawStorageEntry(Path(), relative, "directory", 0))
                else:
                    raise LocalRuntimeError("Raw storage archive contains an unsupported entry.")
    except (OSError, tarfile.TarError) as exc:
        raise LocalRuntimeError("Raw storage archive could not be verified.") from exc
    actual = RawStorageInventory(
        source_state=expected.source_state,
        entries=tuple(entries),
        file_count=sum(entry.kind == "file" for entry in entries),
        directory_count=sum(entry.kind == "directory" for entry in entries),
        total_bytes=sum(entry.size for entry in entries if entry.kind == "file"),
        inventory_sha256=_raw_inventory_digest(entries),
    )
    if (
        actual.file_count != expected.file_count
        or actual.directory_count != expected.directory_count
        or actual.total_bytes != expected.total_bytes
        or actual.inventory_sha256 != expected.inventory_sha256
    ):
        raise LocalRuntimeError("Raw storage archive inventory does not match the source snapshot.")


def _compare_raw_storage_inventories(
    before: RawStorageInventory,
    after: RawStorageInventory,
) -> None:
    if (
        before.source_state != after.source_state
        or before.file_count != after.file_count
        or before.directory_count != after.directory_count
        or before.total_bytes != after.total_bytes
        or before.inventory_sha256 != after.inventory_sha256
    ):
        raise LocalRuntimeError(
            "Raw storage changed while the backup was being created; no verified "
            "receipt was created."
        )


def _assert_backup_ports_free() -> None:
    occupied = [
        str(port)
        for host, port in ((BACKEND_HOST, BACKEND_PORT), (WEB_HOST, WEB_PORT))
        if tcp_port_in_use(host, port)
    ]
    if occupied:
        raise LocalRuntimeError(
            "Full local backup requires FounderOS app ports to be free. Run make local-stop first."
        )


def create_local_backup(root: Path, config: Any) -> Path:
    _assert_backup_ports_free()
    parsed = validate_local_settings(config)
    if not _is_loopback_host(parsed.host):
        raise LocalRuntimeError("Local backup refused a non-loopback database.")
    probe = probe_database(str(config.database_url))
    if not probe.reachable:
        raise LocalRuntimeError("Local backup requires a reachable loopback PostgreSQL database.")
    tools = _backup_tools()
    backup_root = root / BACKUP_DIR_RELATIVE
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_root.chmod(0o700)
    recover_stale_restore_clusters(root, pg_ctl=tools["pg_ctl"])
    credential_proof = verify_persisted_connector_credentials(str(config.database_url), config)
    raw_inventory = scan_raw_storage(root, config)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    bundle_name = f"founderos-{timestamp}-{uuid4().hex[:8]}"
    partial_bundle = backup_root / f"{bundle_name}.partial"
    final_bundle = backup_root / bundle_name
    partial_bundle.mkdir(mode=0o700)

    dump_path = partial_bundle / "database.dump"
    raw_archive_path = partial_bundle / "raw-storage.tar.gz"
    manifest_path = partial_bundle / "manifest.json"
    receipt_path = partial_bundle / "receipt.json"
    try:
        _run_checked_quiet(
            build_pg_dump_command(tools["pg_dump"], dump_path),
            cwd=root,
            env=_pg_environment(parsed),
        )
        dump_path.chmod(0o600)
        listing = subprocess.run(
            [tools["pg_restore"], "--list", str(dump_path)],
            cwd=root,
            env=_pg_environment(parsed),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if listing.returncode != 0 or not listing.stdout.strip():
            raise LocalRuntimeError("pg_restore could not verify the database archive.")

        source_snapshot = database_snapshot(str(config.database_url))
        for tool_name in tools:
            if _postgres_tool_major(tools[tool_name]) != source_snapshot.server_major:
                raise LocalRuntimeError(
                    "PostgreSQL backup tools must match the local server major version."
                )
        database_proof = _restore_and_compare_database(
            root=root,
            parsed=parsed,
            dump_path=dump_path,
            source_snapshot=source_snapshot,
            tools=tools,
            config=config,
        )
        dump_checksum_path, dump_digest = _write_checksum(dump_path)
        _verify_checksum(dump_path, dump_checksum_path)

        _create_raw_storage_archive(raw_archive_path, raw_inventory)
        _verify_raw_storage_archive(raw_archive_path, raw_inventory)
        final_raw_inventory = scan_raw_storage(root, config)
        _compare_raw_storage_inventories(raw_inventory, final_raw_inventory)
        raw_checksum_path, raw_digest = _write_checksum(raw_archive_path)
        _verify_checksum(raw_archive_path, raw_checksum_path)

        manifest = {
            "bundle_format_version": BACKUP_FORMAT_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": {
                **database_proof,
                "artifact": dump_path.name,
                "bytes": dump_path.stat().st_size,
                "sha256": dump_digest,
            },
            "credential_decryptability": credential_proof.aggregate_dict(),
            "raw_storage": {
                "artifact": raw_archive_path.name,
                "bytes": raw_archive_path.stat().st_size,
                "sha256": raw_digest,
                "source_state": raw_inventory.source_state,
                "file_count": raw_inventory.file_count,
                "directory_count": raw_inventory.directory_count,
                "total_bytes": raw_inventory.total_bytes,
                "inventory_sha256": raw_inventory.inventory_sha256,
                "symlinks_allowed": False,
            },
        }
        _write_private_json(manifest_path, manifest)
        manifest_checksum_path, manifest_digest = _write_checksum(manifest_path)
        _verify_checksum(manifest_path, manifest_checksum_path)
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise LocalRuntimeError("Backup manifest verification failed.")

        receipt = {
            "bundle_format_version": BACKUP_FORMAT_VERSION,
            "status": "verified",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "manifest": manifest_path.name,
            "manifest_sha256": manifest_digest,
            "database_restore_verified": True,
            "credential_decryptability_verified": True,
            "backup_credential_decryptability_verified": bool(
                database_proof["restored_credential_decryptability"]["verified"]
            ),
            "encrypted_credential_fields_verified": database_proof[
                "restored_credential_decryptability"
            ]["verified_field_count"],
            "test_fixture_credential_fields_ignored": database_proof[
                "restored_credential_decryptability"
            ]["fixture_field_count"],
            "temporary_database_dropped": True,
            "raw_storage_archive_verified": True,
            "checksums_verified": True,
        }
        _write_private_json(receipt_path, receipt)
        if json.loads(receipt_path.read_text(encoding="utf-8")) != receipt:
            raise LocalRuntimeError("Backup receipt verification failed.")
        partial_bundle.replace(final_bundle)
    except Exception as exc:
        if not isinstance(exc, TemporaryRestoreCleanupError):
            if partial_bundle.exists():
                shutil.rmtree(partial_bundle)
            if final_bundle.exists():
                shutil.rmtree(final_bundle)
        raise

    final_receipt = final_bundle / receipt_path.name
    print(
        "Full local backup verified: "
        f"{final_bundle.relative_to(root)} "
        f"(database tables {database_proof['table_count']}, raw files {raw_inventory.file_count})."
    )
    return final_receipt


def database_migrations_current(root: Path) -> bool:
    """Return whether Alembic reports every code head applied, without output."""

    completed = subprocess.run(
        ["uv", "run", "alembic", "current", "--check-heads"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def pre_migration_backup(root: Path, config: Any, probe: DatabaseProbe) -> Path | None:
    if not probe.has_public_tables:
        print("Pre-migration backup: skipped for an empty first-run database.")
        return None
    if database_migrations_current(root):
        print("Pre-migration backup: skipped because the database is already at code head.")
        return None
    print("Pre-migration backup: pending or unknown revision detected.")
    return create_local_backup(root, config)


def apply_migrations(root: Path) -> None:
    print("Database migrations: applying Alembic head before application start.")
    completed = subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=root, check=False)
    if completed.returncode != 0:
        raise LocalRuntimeError(f"Alembic migration failed with exit code {completed.returncode}.")


def backend_command() -> list[str]:
    return [
        "uv",
        "run",
        "uvicorn",
        "app.main:app",
        "--host",
        BACKEND_HOST,
        "--port",
        str(BACKEND_PORT),
        "--no-access-log",
    ]


def frontend_command() -> list[str]:
    return [
        "npm",
        "run",
        "dev",
        "--",
        "--hostname",
        WEB_HOST,
        "--port",
        str(WEB_PORT),
    ]


def frontend_environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in FRONTEND_ENV_ALLOWLIST}
    env["FOUNDEROS_API_PROXY_TARGET"] = BACKEND_BASE_URL
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    return env


def runtime_state_path(root: Path) -> Path:
    return root / RUNTIME_STATE_RELATIVE


def write_runtime_state(root: Path, state: RuntimeState) -> None:
    path = runtime_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(state), sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def read_runtime_state(root: Path) -> RuntimeState | None:
    path = runtime_state_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeState(
            supervisor_pid=int(payload["supervisor_pid"]),
            backend_pid=int(payload["backend_pid"]),
            frontend_pid=int(payload["frontend_pid"]),
            started_at=str(payload["started_at"]),
            repo_root=str(payload["repo_root"]),
            supervisor_start_signature=str(payload["supervisor_start_signature"]),
            backend_start_signature=(
                str(payload["backend_start_signature"])
                if payload.get("backend_start_signature")
                else None
            ),
            frontend_start_signature=(
                str(payload["frontend_start_signature"])
                if payload.get("frontend_start_signature")
                else None
            ),
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def process_command(pid: int) -> str | None:
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    command = completed.stdout.strip()
    return command if completed.returncode == 0 and command else None


def process_start_signature(pid: int) -> str | None:
    completed = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def process_matches(pid: int, marker: str) -> bool:
    command = process_command(pid)
    return command is not None and marker in command


def process_cwd(pid: int) -> Path | None:
    proc_cwd = Path("/proc") / str(pid) / "cwd"
    try:
        if proc_cwd.exists():
            return proc_cwd.resolve(strict=True)
    except OSError:
        return None
    if not command_available("lsof"):
        return None
    completed = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        if line.startswith("n") and len(line) > 1:
            try:
                return Path(line[1:]).resolve(strict=True)
            except OSError:
                return None
    return None


def runtime_process_matches(root: Path, state: RuntimeState) -> bool:
    resolved_root = root.resolve()
    if state.repo_root != str(resolved_root):
        return False
    if not process_matches(state.supervisor_pid, "scripts/start_local.py"):
        return False
    if process_cwd(state.supervisor_pid) != resolved_root:
        return False
    return process_start_signature(state.supervisor_pid) == state.supervisor_start_signature


def runtime_child_matches(root: Path, state: RuntimeState, child: str) -> bool:
    if child == "backend":
        pid = state.backend_pid
        signature = state.backend_start_signature
        expected_cwd = root.resolve()
        markers = ("uvicorn", "app.main:app")
    elif child == "frontend":
        pid = state.frontend_pid
        signature = state.frontend_start_signature
        expected_cwd = (root / "web").resolve()
        markers = ("npm", "run", "dev")
    else:
        raise ValueError("unknown local runtime child")
    if pid <= 0 or not signature:
        return False
    command = process_command(pid)
    if command is None or not all(marker in command for marker in markers):
        return False
    return process_cwd(pid) == expected_cwd and process_start_signature(pid) == signature


def _capture_child_start_signature(
    root: Path,
    *,
    child: str,
    pid: int,
    timeout_seconds: float = 3.0,
) -> str:
    expected_cwd = root.resolve() if child == "backend" else (root / "web").resolve()
    markers = ("uvicorn", "app.main:app") if child == "backend" else ("npm", "run", "dev")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        command = process_command(pid)
        signature = process_start_signature(pid)
        if (
            command is not None
            and all(marker in command for marker in markers)
            and process_cwd(pid) == expected_cwd
            and signature
        ):
            return signature
        time.sleep(0.05)
    raise LocalRuntimeError(
        f"The {child} process identity could not be captured for safe shutdown."
    )


def _runtime_ports_busy() -> bool:
    return any(
        tcp_port_in_use(host, port)
        for host, port in ((BACKEND_HOST, BACKEND_PORT), (WEB_HOST, WEB_PORT))
    )


def _recorded_children_alive(state: RuntimeState) -> list[str]:
    return [
        child
        for child, pid in (
            ("backend", state.backend_pid),
            ("frontend", state.frontend_pid),
        )
        if pid > 0 and process_command(pid) is not None
    ]


def _runtime_is_quiescent(state: RuntimeState) -> bool:
    return not _recorded_children_alive(state) and not _runtime_ports_busy()


def _signal_verified_orphan_group(state: RuntimeState, child: str) -> bool:
    pid = state.backend_pid if child == "backend" else state.frontend_pid
    try:
        if os.getpgid(pid) != pid:
            return False
        os.killpg(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return process_command(pid) is None
    return True


def _reconcile_dead_supervisor(
    root: Path,
    state: RuntimeState,
    *,
    timeout_seconds: float,
) -> bool:
    state_path = runtime_state_path(root)
    alive_children = _recorded_children_alive(state)
    if alive_children:
        if any(not runtime_child_matches(root, state, child) for child in alive_children):
            print(
                "FounderOS found live orphan candidates but refused to signal them "
                "because child ownership could not be verified. The runtime record "
                "was preserved."
            )
            return False
        if any(
            not _signal_verified_orphan_group(state, child) for child in reversed(alive_children)
        ):
            print(
                "FounderOS could not safely signal a verified orphan process group; "
                "the runtime record was preserved."
            )
            return False

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _runtime_is_quiescent(state):
            state_path.unlink(missing_ok=True)
            print("FounderOS cleaned up a stale local runtime safely.")
            return True
        time.sleep(0.2)
    print(
        "FounderOS local runtime still has live children or occupied ports; the "
        "runtime record was preserved for inspection."
    )
    return False


def stop_recorded_runtime(root: Path, *, timeout_seconds: float = 12.0) -> bool:
    state_path = runtime_state_path(root)
    state = read_runtime_state(root)
    if state is None:
        if state_path.exists():
            print(
                "FounderOS refused to remove an invalid runtime record because "
                "process ownership cannot be verified."
            )
            return False
        if _runtime_ports_busy():
            print(
                "FounderOS is not recorded as running, but local app ports are "
                "occupied; no process was signaled."
            )
            return False
        print("FounderOS local runtime is not recorded as running.")
        return True
    if process_command(state.supervisor_pid) is None:
        return _reconcile_dead_supervisor(
            root,
            state,
            timeout_seconds=timeout_seconds,
        )
    if not runtime_process_matches(root, state):
        print(
            "FounderOS refused to stop an unverified live process; the runtime "
            "record was preserved for manual inspection."
        )
        return False

    os.kill(state.supervisor_pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process_command(state.supervisor_pid) is None:
            stopped = _reconcile_dead_supervisor(
                root,
                state,
                timeout_seconds=max(0.2, deadline - time.monotonic()),
            )
            if stopped:
                print("FounderOS local runtime stopped gracefully.")
            return stopped
        time.sleep(0.2)
    print("FounderOS local runtime did not stop before the timeout; no force-kill was sent.")
    return False


def _url_status(url: str, *, timeout: float = 2.0) -> int | None:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (OSError, urllib.error.URLError):
        return None


def wait_for_url(
    url: str,
    *,
    timeout_seconds: float,
    children: Sequence[subprocess.Popen[Any]] = (),
    stop_requested: Callable[[], bool] | None = None,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if stop_requested is not None and stop_requested():
            return False
        if any(child.poll() is not None for child in children):
            return False
        if _url_status(url) == 200:
            return True
        time.sleep(0.25)
    return False


def local_smoke() -> bool:
    checks = (
        ("backend-health", f"{BACKEND_BASE_URL}/health"),
        ("web-proxy-health", f"{WEB_BIND_BASE_URL}/health"),
    )
    success = True
    print("FounderOS local smoke")
    for name, url in checks:
        status = _url_status(url)
        ok = status == 200
        success = success and ok
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: HTTP {status or 'unreachable'}")
    return success


async def _prepare_founder_destination(base_url: str) -> FounderDestination:
    from app.db.base import AsyncSessionLocal
    from app.services.founder_enrollment_service import create_founder_invite
    from scripts.create_founder_invite import _invite_url

    if await _has_login_capable_local_member():
        return FounderDestination(url=f"{base_url}/login", invite_id=None)
    async with AsyncSessionLocal() as session:
        created = await create_founder_invite(session)
        await session.commit()
        return FounderDestination(
            url=_invite_url(base_url, created.raw_token),
            invite_id=created.row.id,
        )


async def _has_login_capable_local_member() -> bool:
    from app.db.base import AsyncSessionLocal
    from app.db.identity_models import (
        USER_STATUS_ACTIVE,
        WORKSPACE_STATUS_ACTIVE,
        Membership,
        User,
        Workspace,
    )

    async with AsyncSessionLocal() as session:
        return bool(
            await session.scalar(
                select(func.count())
                .select_from(User)
                .join(Membership, Membership.user_id == User.id)
                .join(Workspace, Workspace.id == Membership.workspace_id)
                .where(
                    User.status == USER_STATUS_ACTIVE,
                    User.password_hash.is_not(None),
                    Workspace.status == WORKSPACE_STATUS_ACTIVE,
                )
            )
        )


async def _revoke_unused_local_invite(invite_id: UUID) -> None:
    from app.db.base import AsyncSessionLocal
    from app.services.founder_enrollment_service import revoke_founder_invite

    async with AsyncSessionLocal() as session:
        await revoke_founder_invite(session, invite_id=invite_id)
        await session.commit()


def safe_founder_instruction() -> None:
    print("Founder setup was not opened automatically. Run this safe command:")
    print(
        "  UV_NO_SYNC=1 uv run python scripts/create_founder_invite.py "
        f"--base-url {WEB_BASE_URL} --ttl-hours 72"
    )
    print("Then open the one-time URL printed only in your local terminal.")


def _print_local_destination_fallback(has_login: bool | None) -> None:
    if has_login is True:
        print(f"Open the existing founder login: {WEB_BASE_URL}/login")
    elif has_login is False:
        safe_founder_instruction()
    else:
        print(f"Open {WEB_BASE_URL}/login for an existing founder.")
        print("For an empty installation, use the documented founder invite fallback.")


async def _open_local_product_async(
    *,
    no_open: bool,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> None:
    if no_open or os.environ.get("CI") or os.environ.get("FOUNDEROS_LOCAL_NO_OPEN"):
        print(f"FounderOS is ready: {WEB_BASE_URL}")
        try:
            has_login = await _has_login_capable_local_member()
        except Exception:
            has_login = None
        _print_local_destination_fallback(has_login)
        return

    try:
        destination = await _prepare_founder_destination(WEB_BASE_URL)
    except Exception:
        print(f"FounderOS is ready: {WEB_BASE_URL}")
        try:
            has_login = await _has_login_capable_local_member()
        except Exception:
            has_login = None
        _print_local_destination_fallback(has_login)
        return
    try:
        opened = bool(browser_open(destination.url))
    except Exception:
        opened = False
    if opened:
        if destination.invite_id is None:
            print(f"FounderOS login opened: {WEB_BASE_URL}/login")
        else:
            print("One-time founder onboarding opened securely in the browser.")
        return

    if destination.invite_id is not None:
        try:
            await _revoke_unused_local_invite(destination.invite_id)
        except Exception as exc:
            raise LocalRuntimeError(
                "The unused founder invite could not be revoked; automatic founder "
                "handoff stopped without printing the bearer credential."
            ) from exc
    print(f"FounderOS is ready: {WEB_BASE_URL}")
    _print_local_destination_fallback(destination.invite_id is None)


def open_local_product(
    *,
    no_open: bool,
    browser_open: Callable[[str], bool] = webbrowser.open,
) -> None:
    asyncio.run(
        _open_local_product_async(
            no_open=no_open,
            browser_open=browser_open,
        )
    )


def _terminate_child(process: subprocess.Popen[Any], *, timeout_seconds: float = 8.0) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=2)


def run_backend_only(root: Path, config: Any) -> int:
    """Run the migration-safe backend fallback without supervising Next.js."""

    validate_local_settings(config)
    recover_stale_restore_clusters(root)
    if tcp_port_in_use(BACKEND_HOST, BACKEND_PORT):
        raise LocalRuntimeError(
            f"Local backend port {BACKEND_PORT} is already in use. FounderOS did not stop it."
        )
    database_probe = ensure_database(root, config)
    pre_migration_backup(root, config, database_probe)
    apply_migrations(root)
    print("Backend: starting on 127.0.0.1:8765. Press Ctrl+C to stop it safely.")
    completed = subprocess.run(backend_command(), cwd=root, check=False)
    return int(completed.returncode)


def supervise_local_runtime(root: Path, config: Any, *, no_open: bool) -> int:
    validate_local_settings(config)
    recover_stale_restore_clusters(root)
    supervisor_signature = process_start_signature(os.getpid())
    if process_cwd(os.getpid()) != root.resolve() or supervisor_signature is None:
        raise LocalRuntimeError(
            "Local process ownership cannot be verified; ps plus /proc or lsof "
            "is required for safe shutdown."
        )
    if runtime_state_path(root).exists():
        state = read_runtime_state(root)
        if state is None:
            raise LocalRuntimeError(
                "The local runtime record is invalid and was preserved because "
                "process ownership cannot be verified."
            )
        if process_command(state.supervisor_pid) is None:
            if not _reconcile_dead_supervisor(root, state, timeout_seconds=8.0):
                raise LocalRuntimeError("A stale local runtime could not be cleaned up safely.")
        elif runtime_process_matches(root, state):
            raise LocalRuntimeError(
                "FounderOS local runtime is already running. Use make local-stop first."
            )
        else:
            raise LocalRuntimeError(
                "A live process is referenced by the local runtime record but ownership "
                "cannot be verified; inspect it before removing the record."
            )
    for host, port, label in (
        (BACKEND_HOST, BACKEND_PORT, "backend"),
        (WEB_HOST, WEB_PORT, "web"),
    ):
        if tcp_port_in_use(host, port):
            raise LocalRuntimeError(
                f"Local {label} port {port} is already in use. FounderOS did not stop it."
            )

    database_probe = ensure_database(root, config)
    ensure_frontend_dependencies(root)
    pre_migration_backup(root, config, database_probe)
    apply_migrations(root)

    shutdown_requested = False

    def request_shutdown(_signum: int, _frame: Any) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True

    previous_sigint = signal.signal(signal.SIGINT, request_shutdown)
    previous_sigterm = signal.signal(signal.SIGTERM, request_shutdown)
    previous_sighup = (
        signal.signal(signal.SIGHUP, request_shutdown) if hasattr(signal, "SIGHUP") else None
    )
    children: list[subprocess.Popen[Any]] = []
    try:
        print("Backend: starting on 127.0.0.1:8765.")
        backend = subprocess.Popen(backend_command(), cwd=root, start_new_session=True)
        children.append(backend)
        backend_signature = _capture_child_start_signature(
            root,
            child="backend",
            pid=backend.pid,
        )
        write_runtime_state(
            root,
            RuntimeState(
                supervisor_pid=os.getpid(),
                backend_pid=backend.pid,
                frontend_pid=0,
                started_at=datetime.now(timezone.utc).isoformat(),
                repo_root=str(root.resolve()),
                supervisor_start_signature=supervisor_signature,
                backend_start_signature=backend_signature,
            ),
        )
        if not wait_for_url(
            f"{BACKEND_BASE_URL}/health",
            timeout_seconds=60,
            children=children,
            stop_requested=lambda: shutdown_requested,
        ):
            if shutdown_requested:
                return 0
            raise LocalRuntimeError("Backend did not become healthy before the timeout.")

        print("Web: starting on 127.0.0.1:3000 with the backend proxy configured.")
        frontend = subprocess.Popen(
            frontend_command(),
            cwd=root / "web",
            env=frontend_environment(),
            start_new_session=True,
        )
        children.append(frontend)
        frontend_signature = _capture_child_start_signature(
            root,
            child="frontend",
            pid=frontend.pid,
        )
        write_runtime_state(
            root,
            RuntimeState(
                supervisor_pid=os.getpid(),
                backend_pid=backend.pid,
                frontend_pid=frontend.pid,
                started_at=datetime.now(timezone.utc).isoformat(),
                repo_root=str(root.resolve()),
                supervisor_start_signature=supervisor_signature,
                backend_start_signature=backend_signature,
                frontend_start_signature=frontend_signature,
            ),
        )
        if not wait_for_url(
            f"{WEB_BIND_BASE_URL}/health",
            timeout_seconds=90,
            children=children,
            stop_requested=lambda: shutdown_requested,
        ):
            if shutdown_requested:
                return 0
            raise LocalRuntimeError("Web proxy did not become healthy before the timeout.")

        print("FounderOS local runtime is healthy (backend + same-origin web proxy).")
        open_local_product(no_open=no_open)
        print("Press Ctrl+C to stop FounderOS safely.")
        while not shutdown_requested:
            failed = next((child for child in children if child.poll() is not None), None)
            if failed is not None:
                raise LocalRuntimeError(
                    f"A supervised local process exited with code {failed.returncode}."
                )
            time.sleep(0.25)
        return 0
    finally:
        for child in reversed(children):
            _terminate_child(child)
        state = read_runtime_state(root)
        if state is None:
            runtime_state_path(root).unlink(missing_ok=True)
        elif state.supervisor_pid == os.getpid() and _runtime_is_quiescent(state):
            runtime_state_path(root).unlink(missing_ok=True)
        elif state.supervisor_pid == os.getpid():
            print(
                "FounderOS preserved the runtime record because child processes or "
                "local app ports are still active."
            )
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        if hasattr(signal, "SIGHUP") and previous_sighup is not None:
            signal.signal(signal.SIGHUP, previous_sighup)
        if children:
            print("FounderOS local runtime stopped.")
