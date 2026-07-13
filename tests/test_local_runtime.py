from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import local_runtime
from scripts.local_runtime import (
    BACKEND_BASE_URL,
    WEB_BIND_BASE_URL,
    WEB_BASE_URL,
    DatabaseProbe,
    FounderDestination,
    LocalRuntimeError,
    RuntimeState,
    backend_command,
    build_pg_dump_command,
    collect_doctor_checks,
    create_local_backup,
    database_is_loopback,
    ensure_database,
    ensure_frontend_dependencies,
    frontend_command,
    frontend_environment,
    frontend_install_command,
    open_local_product,
    pre_migration_backup,
    read_runtime_state,
    stop_recorded_runtime,
    validate_local_settings,
    write_runtime_state,
)
from scripts.start_local import _normalized_argv


def _config(database_url: str = "postgresql+asyncpg://user:password@localhost:5432/db"):
    return SimpleNamespace(app_env="local", database_url=database_url)


def _empty_credential_proof() -> local_runtime.CredentialDecryptabilityProof:
    return local_runtime.CredentialDecryptabilityProof(0, 0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://user:password@localhost:5432/db",
        "postgresql+asyncpg://user:password@127.0.0.1:5432/db",
        "postgresql+asyncpg://user:password@[::1]:5432/db",
    ],
)
def test_database_scope_accepts_only_explicit_loopback(url: str) -> None:
    assert database_is_loopback(url) is True
    validate_local_settings(_config(url))


def test_database_scope_allows_non_endpoint_query_options() -> None:
    config = _config(
        "postgresql+asyncpg://user:password@127.0.0.1:5432/db"
        "?sslmode=disable&application_name=founderos-local"
    )

    parsed = validate_local_settings(config)

    assert parsed.host == "127.0.0.1"
    assert parsed.port == 5432
    assert parsed.database == "db"


@pytest.mark.parametrize(
    "query",
    [
        "host=db.example.test",
        "HOST=db.example.test",
        "%68ost=db.example.test",
        "host=127.0.0.1&host=db.example.test",
        "hostaddr=203.0.113.10",
        "HOSTADDR=203.0.113.10",
        "port=6543",
        "database=other",
        "dbname=other",
        "service=remote",
        "service=local&service=remote",
        "servicefile=%2Ftmp%2Fpg_service.conf",
        "%73ervicefile=%2Ftmp%2Fpg_service.conf",
    ],
)
def test_database_query_endpoint_overrides_fail_before_any_database_call(
    monkeypatch,
    tmp_path: Path,
    query: str,
) -> None:
    config = _config(f"postgresql+asyncpg://user:password@127.0.0.1:5432/db?{query}")
    database_calls: list[str] = []
    monkeypatch.setattr(
        local_runtime,
        "probe_database",
        lambda _url: database_calls.append("probe") or DatabaseProbe(reachable=True),
    )
    monkeypatch.setattr(
        local_runtime,
        "create_async_engine",
        lambda *_args, **_kwargs: (
            database_calls.append("engine")
            or pytest.fail("an endpoint override must fail before engine creation")
        ),
    )

    with pytest.raises(LocalRuntimeError, match="must not override"):
        ensure_database(tmp_path, config)

    assert database_calls == []


def test_runtime_rejects_endpoint_override_before_alembic_or_process_start(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config("postgresql+asyncpg://user:password@127.0.0.1:5432/db?%48OST=db.example.test")
    side_effects: list[str] = []
    monkeypatch.setattr(
        local_runtime,
        "recover_stale_restore_clusters",
        lambda _root: side_effects.append("restore-recovery"),
    )
    monkeypatch.setattr(
        local_runtime,
        "ensure_database",
        lambda *_args: side_effects.append("database"),
    )
    monkeypatch.setattr(
        local_runtime,
        "apply_migrations",
        lambda _root: side_effects.append("alembic"),
    )

    with pytest.raises(LocalRuntimeError, match="must not override"):
        local_runtime.supervise_local_runtime(tmp_path, config, no_open=True)

    assert side_effects == []


def test_database_scope_rejects_remote_or_non_local_runtime() -> None:
    remote = _config("postgresql+asyncpg://user:password@db.example.test:5432/db")
    with pytest.raises(LocalRuntimeError, match="non-loopback"):
        validate_local_settings(remote)
    with pytest.raises(LocalRuntimeError, match="APP_ENV"):
        validate_local_settings(
            SimpleNamespace(app_env="production", database_url=remote.database_url)
        )


@pytest.mark.parametrize(
    "field",
    ["enable_llm", "enable_write_actions", "enable_real_connectors"],
)
def test_canonical_runtime_refuses_enabled_external_capability_gates(
    field: str,
) -> None:
    config = _config()
    setattr(config, field, True)

    with pytest.raises(LocalRuntimeError, match="capability gates"):
        validate_local_settings(config)


def test_frontend_dependencies_are_installed_only_when_missing(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "package-lock.json").write_text("{}\n", encoding="utf-8")
    assert frontend_install_command(tmp_path) == ["npm", "ci"]

    next_binary = web / "node_modules/.bin/next"
    next_binary.parent.mkdir(parents=True)
    next_binary.write_text("", encoding="utf-8")
    assert frontend_install_command(tmp_path) == []


def test_existing_postgres_is_reused_before_any_docker_check(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        local_runtime,
        "probe_database",
        lambda _url: DatabaseProbe(reachable=True, has_public_tables=True),
    )

    def unexpected_docker(_root: Path) -> bool:
        raise AssertionError("Docker must not be inspected when Postgres is reachable")

    monkeypatch.setattr(local_runtime, "docker_daemon_available", unexpected_docker)
    assert ensure_database(tmp_path, _config()).reachable is True


def test_offline_database_compose_fallback_starts_postgres_only(
    monkeypatch, tmp_path: Path
) -> None:
    probes = iter(
        [
            DatabaseProbe(reachable=False),
            DatabaseProbe(reachable=True, has_public_tables=False),
        ]
    )
    monkeypatch.setattr(local_runtime, "probe_database", lambda _url: next(probes))
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)
    monkeypatch.setattr(local_runtime, "docker_daemon_available", lambda _root: True)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        local_runtime,
        "_run_checked_quiet",
        lambda command, **_kwargs: commands.append(list(command)),
    )

    probe = ensure_database(tmp_path, _config(), timeout_seconds=1)
    assert probe.reachable is True
    assert commands == [["docker", "compose", "up", "-d", "postgres"]]


def test_doctor_describes_missing_web_dependencies_without_installing(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "web").mkdir()
    (tmp_path / "web/package-lock.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(local_runtime, "command_available", lambda _command: True)
    monkeypatch.setattr(
        local_runtime,
        "probe_database",
        lambda _url: DatabaseProbe(reachable=True, has_public_tables=False),
    )
    monkeypatch.setattr(local_runtime, "database_server_major", lambda _url: 16)
    monkeypatch.setattr(local_runtime, "_postgres_tool_major", lambda _tool: 16)
    monkeypatch.setattr(
        local_runtime,
        "verify_persisted_connector_credentials",
        lambda _url, _config: _empty_credential_proof(),
    )
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)
    checks = collect_doctor_checks(tmp_path, _config())
    web_check = next(check for check in checks if check.name == "web-dependencies")
    assert web_check.status == "warn"
    assert "npm ci" in web_check.detail


def test_doctor_fails_when_required_runtime_port_is_occupied(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "web/node_modules/.bin").mkdir(parents=True)
    (tmp_path / "web/node_modules/.bin/next").write_text("", encoding="utf-8")
    monkeypatch.setattr(local_runtime, "command_available", lambda _command: True)
    monkeypatch.setattr(
        local_runtime,
        "probe_database",
        lambda _url: DatabaseProbe(reachable=True, has_public_tables=False),
    )
    monkeypatch.setattr(local_runtime, "database_server_major", lambda _url: 16)
    monkeypatch.setattr(local_runtime, "_postgres_tool_major", lambda _tool: 16)
    monkeypatch.setattr(
        local_runtime,
        "verify_persisted_connector_credentials",
        lambda _url, _config: _empty_credential_proof(),
    )
    monkeypatch.setattr(
        local_runtime,
        "tcp_port_in_use",
        lambda _host, port: port == local_runtime.BACKEND_PORT,
    )

    checks = collect_doctor_checks(tmp_path, _config())

    backend = next(check for check in checks if check.name == "backend-port")
    assert backend.status == "fail"
    assert local_runtime.print_doctor_checks(checks) is False


def test_doctor_fails_tool_major_mismatch_against_reachable_server(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(local_runtime, "command_available", lambda _command: True)
    monkeypatch.setattr(
        local_runtime,
        "probe_database",
        lambda _url: DatabaseProbe(reachable=True, has_public_tables=True),
    )
    monkeypatch.setattr(local_runtime, "database_server_major", lambda _url: 16)
    monkeypatch.setattr(
        local_runtime,
        "verify_persisted_connector_credentials",
        lambda _url, _config: _empty_credential_proof(),
    )
    monkeypatch.setattr(
        local_runtime,
        "_postgres_tool_major",
        lambda tool: 15 if tool == "pg_dump" else 16,
    )
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)

    checks = collect_doctor_checks(tmp_path, _config())

    pg_dump = next(check for check in checks if check.name == "pg_dump")
    assert pg_dump.status == "fail"
    assert "required major" in pg_dump.detail
    assert local_runtime.print_doctor_checks(checks) is False


def test_doctor_uses_postgres_16_compose_baseline_while_database_is_offline(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(local_runtime, "command_available", lambda _command: True)
    monkeypatch.setattr(
        local_runtime,
        "probe_database",
        lambda _url: DatabaseProbe(reachable=False, has_public_tables=False),
    )
    monkeypatch.setattr(local_runtime, "docker_daemon_available", lambda _root: True)
    monkeypatch.setattr(local_runtime, "_postgres_tool_major", lambda _tool: 15)
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)

    checks = collect_doctor_checks(tmp_path, _config())

    pg_restore = next(check for check in checks if check.name == "pg_restore")
    baseline = next(check for check in checks if check.name == "postgres-server-major")
    assert pg_restore.status == "fail"
    assert "PostgreSQL 16" in pg_restore.detail
    assert "PostgreSQL 16" in baseline.detail


def test_pg_dump_command_never_contains_database_credentials(tmp_path: Path) -> None:
    command = build_pg_dump_command("/usr/local/bin/pg_dump", tmp_path / "backup.dump")
    rendered = " ".join(command)
    assert "postgresql" not in rendered
    assert "password" not in rendered
    assert "--format=custom" in command


def test_credential_proof_ignores_only_explicit_test_fixtures() -> None:
    decrypted: list[str] = []
    proof = local_runtime._evaluate_credential_decryptability(
        [
            ("fixture-placeholder", None, {"connection_method": "test"}),
            (
                "encrypted-real-access",
                "encrypted-real-refresh",
                {"connection_method": "manual_provider_token"},
            ),
        ],
        decryptor=lambda value: decrypted.append(value) or "plaintext-discarded",
    )

    assert decrypted == ["encrypted-real-access", "encrypted-real-refresh"]
    assert proof.connection_count == 2
    assert proof.real_connection_count == 1
    assert proof.fixture_connection_count == 1
    assert proof.verified_field_count == 2
    assert proof.fixture_field_count == 1
    assert proof.failure_count == 0
    assert "plaintext" not in repr(proof)


def test_manual_provider_token_decrypt_failure_blocks_backup_before_receipt(
    monkeypatch, tmp_path: Path
) -> None:
    proof = local_runtime._evaluate_credential_decryptability(
        [
            (
                "undecryptable-ciphertext",
                None,
                {"connection_method": "manual_provider_token"},
            )
        ],
        decryptor=lambda _value: (_ for _ in ()).throw(ValueError("bad key")),
    )

    async def failed_proof(_url: str, _config: object):
        return proof

    monkeypatch.setattr(
        local_runtime,
        "_credential_decryptability_proof_async",
        failed_proof,
    )
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)
    monkeypatch.setattr(
        local_runtime,
        "probe_database",
        lambda _url: DatabaseProbe(reachable=True, has_public_tables=True),
    )
    monkeypatch.setattr(
        local_runtime,
        "_backup_tools",
        lambda: {"pg_ctl": "/safe/pg_ctl"},
    )
    monkeypatch.setattr(
        local_runtime, "recover_stale_restore_clusters", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        local_runtime,
        "scan_raw_storage",
        lambda *_args: pytest.fail("raw storage must not be read after key failure"),
    )

    with pytest.raises(LocalRuntimeError, match="cannot be decrypted"):
        create_local_backup(tmp_path, _config())

    assert proof.failure_count == 1
    assert not list((tmp_path / ".local/backups").rglob("receipt.json"))


def test_verified_backup_keeps_credentials_out_of_command_and_output(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    password = "test-password-must-not-be-printed"
    config = _config(f"postgresql+asyncpg://user:{password}@localhost:5432/db")
    raw = tmp_path / "raw"
    raw.mkdir()
    private_name = "sensitive-customer-name.txt"
    (raw / private_name).write_text("private body\n", encoding="utf-8")
    config.raw_storage_dir = str(raw)
    monkeypatch.setattr(
        local_runtime,
        "probe_database",
        lambda _url: DatabaseProbe(reachable=True, has_public_tables=True),
    )
    monkeypatch.setattr(
        local_runtime.shutil,
        "which",
        lambda command: (
            f"/safe/{command}"
            if command
            in {
                "pg_dump",
                "pg_restore",
                "createdb",
                "dropdb",
                "initdb",
                "pg_ctl",
                "postgres",
            }
            else None
        ),
    )
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)
    monkeypatch.setattr(
        local_runtime,
        "verify_persisted_connector_credentials",
        lambda _url, _config: _empty_credential_proof(),
    )
    monkeypatch.setattr(local_runtime, "_postgres_tool_major", lambda _binary: 16)
    monkeypatch.setattr(
        local_runtime,
        "database_snapshot",
        lambda _url: local_runtime.DatabaseSnapshot(16, ("head",), {"users": 2}),
    )
    monkeypatch.setattr(
        local_runtime,
        "_restore_and_compare_database",
        lambda **_kwargs: {
            "server_major": 16,
            "alembic_revisions": ["head"],
            "table_counts": {"users": 2},
            "table_count": 1,
            "total_rows": 2,
            "temporary_database_dropped": True,
            "restored_credential_decryptability": (_empty_credential_proof().aggregate_dict()),
        },
    )
    captured_command: list[str] = []

    def fake_dump(command, *, cwd, env=None):
        del cwd, env
        captured_command.extend(command)
        if "--file" in command:
            Path(command[-1]).write_bytes(b"custom-archive")

    monkeypatch.setattr(local_runtime, "_run_checked_quiet", fake_dump)
    monkeypatch.setattr(
        local_runtime.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="archive list\n"),
    )
    original_scan = local_runtime.scan_raw_storage
    raw_scan_count = 0

    def tracked_raw_scan(root: Path, current_config: object):
        nonlocal raw_scan_count
        raw_scan_count += 1
        return original_scan(root, current_config)

    monkeypatch.setattr(local_runtime, "scan_raw_storage", tracked_raw_scan)

    receipt = create_local_backup(tmp_path, config)
    assert receipt.is_file()
    bundle = receipt.parent
    dump = bundle / "database.dump"
    checksum = bundle / "database.dump.sha256"
    raw_archive = bundle / "raw-storage.tar.gz"
    manifest = bundle / "manifest.json"
    assert dump.is_file()
    assert checksum.is_file()
    assert raw_archive.is_file()
    assert manifest.is_file()
    assert private_name not in manifest.read_text(encoding="utf-8")
    assert len(checksum.read_text(encoding="utf-8").split()[0]) == 64
    for artifact in bundle.iterdir():
        assert artifact.stat().st_mode & 0o777 == 0o600
    assert password not in " ".join(captured_command)
    output = capsys.readouterr().out
    assert password not in output
    assert private_name not in output
    assert raw_scan_count == 2


def test_full_backup_refuses_occupied_app_ports_before_database_access(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        local_runtime,
        "tcp_port_in_use",
        lambda _host, port: port == local_runtime.WEB_PORT,
    )
    monkeypatch.setattr(
        local_runtime,
        "probe_database",
        lambda _url: pytest.fail("occupied app ports must fail before database access"),
    )

    with pytest.raises(LocalRuntimeError, match="make local-stop"):
        create_local_backup(tmp_path, _config())


def test_raw_storage_snapshot_rejects_symlinks_without_deleting_source(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "source.txt"
    source.write_text("private source\n", encoding="utf-8")
    (raw / "linked.txt").symlink_to(source)
    config = _config()
    config.raw_storage_dir = str(raw)

    with pytest.raises(LocalRuntimeError, match="symbolic link"):
        local_runtime.scan_raw_storage(tmp_path, config)

    assert source.read_text(encoding="utf-8") == "private source\n"


def test_raw_storage_private_archive_matches_sanitized_inventory(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    (raw / "nested").mkdir(parents=True)
    (raw / "one.bin").write_bytes(b"one")
    (raw / "nested/two.bin").write_bytes(b"two-two")
    config = _config()
    config.raw_storage_dir = str(raw)
    inventory = local_runtime.scan_raw_storage(tmp_path, config)
    archive = tmp_path / "raw.tar.gz"

    local_runtime._create_raw_storage_archive(archive, inventory)
    local_runtime._verify_raw_storage_archive(archive, inventory)

    assert inventory.file_count == 2
    assert inventory.directory_count == 1
    assert inventory.total_bytes == 10
    assert archive.stat().st_mode & 0o777 == 0o600


def test_raw_storage_archive_detects_same_size_content_drift(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    source = raw / "source.bin"
    source.write_bytes(b"AAAA")
    config = _config()
    config.raw_storage_dir = str(raw)
    inventory = local_runtime.scan_raw_storage(tmp_path, config)
    source.write_bytes(b"BBBB")
    archive = tmp_path / "raw.tar.gz"

    local_runtime._create_raw_storage_archive(archive, inventory)

    with pytest.raises(LocalRuntimeError, match="inventory"):
        local_runtime._verify_raw_storage_archive(archive, inventory)


def test_second_raw_storage_scan_rejects_a_new_file_after_archive_creation(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "existing.bin").write_bytes(b"existing")
    config = _config()
    config.raw_storage_dir = str(raw)
    before = local_runtime.scan_raw_storage(tmp_path, config)
    archive = tmp_path / "raw.tar.gz"

    local_runtime._create_raw_storage_archive(archive, before)
    local_runtime._verify_raw_storage_archive(archive, before)
    (raw / "arrived-during-backup.bin").write_bytes(b"late")
    after = local_runtime.scan_raw_storage(tmp_path, config)

    with pytest.raises(LocalRuntimeError, match="changed while"):
        local_runtime._compare_raw_storage_inventories(before, after)


def test_database_restore_proof_always_drops_unique_temporary_database(
    monkeypatch, tmp_path: Path
) -> None:
    parsed = local_runtime.database_url(_config().database_url)
    source = local_runtime.DatabaseSnapshot(16, ("head",), {"users": 3})
    commands: list[list[str]] = []
    command_envs: list[dict[str, str] | None] = []
    cleanup: list[Path] = []
    dropped: list[list[str]] = []
    socket_dir = tmp_path / "private-socket"
    socket_dir.mkdir(mode=0o700)

    def fake_checked(command, **kwargs):
        commands.append(list(command))
        command_envs.append(kwargs.get("env"))
        if command[0] == "/safe/initdb":
            Path(command[command.index("-D") + 1]).mkdir()

    monkeypatch.setattr(
        local_runtime,
        "_run_checked_quiet",
        fake_checked,
    )
    monkeypatch.setattr(
        local_runtime,
        "_create_private_restore_socket_dir",
        lambda _root: socket_dir,
    )
    monkeypatch.setattr(local_runtime, "database_snapshot", lambda _url: source)
    monkeypatch.setattr(
        local_runtime,
        "verify_persisted_connector_credentials",
        lambda _url, _config: _empty_credential_proof(),
    )
    monkeypatch.setattr(
        local_runtime,
        "_temporary_cluster_running",
        lambda _pg_ctl, _cluster_dir: True,
    )
    monkeypatch.setattr(
        local_runtime,
        "_stop_and_remove_temporary_cluster",
        lambda **kwargs: cleanup.append(kwargs["cluster_dir"]),
    )
    monkeypatch.setattr(
        local_runtime.subprocess,
        "run",
        lambda command, **_kwargs: (
            dropped.append(list(command)) or SimpleNamespace(returncode=0, stdout="")
        ),
    )

    proof = local_runtime._restore_and_compare_database(
        root=tmp_path,
        parsed=parsed,
        dump_path=tmp_path / "database.dump",
        source_snapshot=source,
        tools={
            "createdb": "/safe/createdb",
            "pg_restore": "/safe/pg_restore",
            "dropdb": "/safe/dropdb",
            "initdb": "/safe/initdb",
            "pg_ctl": "/safe/pg_ctl",
        },
        config=_config(),
    )

    assert [command[0] for command in commands] == [
        "/safe/initdb",
        "/safe/pg_ctl",
        "/safe/createdb",
        "/safe/pg_restore",
    ]
    assert dropped[0][0] == "/safe/dropdb"
    assert len(cleanup) == 1
    assert "--auth-local=trust" in commands[0]
    assert "--auth-host=reject" in commands[0]
    assert "--auth=trust" not in commands[0]
    server_options = commands[1][commands[1].index("-o") + 1]
    assert "listen_addresses=''" in server_options
    assert str(socket_dir) in server_options
    assert "127.0.0.1" not in server_options
    assert command_envs[2]["PGHOST"] == str(socket_dir)
    assert socket_dir.stat().st_mode & 0o777 == 0o700
    assert proof["temporary_database_dropped"] is True
    assert proof["restore_transport"] == "private_unix_socket"
    assert proof["tcp_listen"] is False
    assert proof["restored_credential_decryptability"]["verified"] is True


def test_database_restore_failure_still_drops_temporary_database(
    monkeypatch, tmp_path: Path
) -> None:
    parsed = local_runtime.database_url(_config().database_url)
    source = local_runtime.DatabaseSnapshot(16, ("head",), {"users": 3})
    calls = 0
    cleanup: list[Path] = []
    socket_dir = tmp_path / "private-socket"
    socket_dir.mkdir(mode=0o700)

    def fail_restore(command, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            Path(command[command.index("-D") + 1]).mkdir()
        if calls == 4:
            raise LocalRuntimeError("restore failed")

    monkeypatch.setattr(local_runtime, "_run_checked_quiet", fail_restore)
    monkeypatch.setattr(
        local_runtime,
        "_create_private_restore_socket_dir",
        lambda _root: socket_dir,
    )
    monkeypatch.setattr(
        local_runtime,
        "_temporary_cluster_running",
        lambda _pg_ctl, _cluster_dir: True,
    )
    monkeypatch.setattr(
        local_runtime,
        "_stop_and_remove_temporary_cluster",
        lambda **kwargs: cleanup.append(kwargs["cluster_dir"]),
    )
    monkeypatch.setattr(
        local_runtime.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=""),
    )

    with pytest.raises(LocalRuntimeError, match="restore failed"):
        local_runtime._restore_and_compare_database(
            root=tmp_path,
            parsed=parsed,
            dump_path=tmp_path / "database.dump",
            source_snapshot=source,
            tools={
                "createdb": "/safe/createdb",
                "pg_restore": "/safe/pg_restore",
                "dropdb": "/safe/dropdb",
                "initdb": "/safe/initdb",
                "pg_ctl": "/safe/pg_ctl",
            },
            config=_config(),
        )

    assert len(cleanup) == 1


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="SIGHUP is unavailable")
def test_restore_sighup_runs_cleanup_and_restores_previous_handler(
    monkeypatch, tmp_path: Path
) -> None:
    parsed = local_runtime.database_url(_config().database_url)
    source = local_runtime.DatabaseSnapshot(16, ("head",), {"users": 3})
    socket_dir = tmp_path / "private-socket"
    socket_dir.mkdir(mode=0o700)
    cleaned: list[dict[str, object]] = []
    previous_handler = signal.getsignal(signal.SIGHUP)

    def interrupt_start(command, **_kwargs):
        if command[0] == "/safe/initdb":
            Path(command[command.index("-D") + 1]).mkdir()
            return
        if command[0] == "/safe/pg_ctl":
            handler = signal.getsignal(signal.SIGHUP)
            assert callable(handler)
            handler(signal.SIGHUP, None)

    monkeypatch.setattr(local_runtime, "_run_checked_quiet", interrupt_start)
    monkeypatch.setattr(
        local_runtime,
        "_create_private_restore_socket_dir",
        lambda _root: socket_dir,
    )
    monkeypatch.setattr(
        local_runtime,
        "_temporary_cluster_running",
        lambda _pg_ctl, _cluster_dir: False,
    )
    monkeypatch.setattr(
        local_runtime,
        "_stop_and_remove_temporary_cluster",
        lambda **kwargs: cleaned.append(kwargs),
    )

    with pytest.raises(LocalRuntimeError, match="interrupted"):
        local_runtime._restore_and_compare_database(
            root=tmp_path,
            parsed=parsed,
            dump_path=tmp_path / "database.dump",
            source_snapshot=source,
            tools={
                "createdb": "/safe/createdb",
                "pg_restore": "/safe/pg_restore",
                "dropdb": "/safe/dropdb",
                "initdb": "/safe/initdb",
                "pg_ctl": "/safe/pg_ctl",
            },
            config=_config(),
        )

    assert len(cleaned) == 1
    assert cleaned[0]["socket_dir"] == socket_dir
    assert signal.getsignal(signal.SIGHUP) == previous_handler


def test_startup_recovers_non_running_stale_restore_cluster(monkeypatch, tmp_path: Path) -> None:
    partial = tmp_path / ".local/backups/founderos-stale.partial"
    cluster = partial / f".restore-cluster-{'a' * 32}"
    cluster.mkdir(parents=True)
    socket_dir = local_runtime._create_private_restore_socket_dir(tmp_path)
    marker = cluster / local_runtime.TEMP_RESTORE_SOCKET_MARKER
    marker.write_text(str(socket_dir) + "\n", encoding="utf-8")
    marker.chmod(0o600)
    monkeypatch.setattr(
        local_runtime,
        "_temporary_cluster_running",
        lambda _pg_ctl, _cluster_dir: False,
    )

    local_runtime.recover_stale_restore_clusters(
        tmp_path,
        pg_ctl="/safe/pg_ctl",
    )

    assert not cluster.exists()
    assert not socket_dir.exists()


def test_database_restore_comparison_rejects_revision_or_count_drift() -> None:
    source = local_runtime.DatabaseSnapshot(16, ("head",), {"users": 3})
    with pytest.raises(LocalRuntimeError, match="Alembic"):
        local_runtime._compare_database_snapshots(
            source,
            local_runtime.DatabaseSnapshot(16, ("old",), {"users": 3}),
        )
    with pytest.raises(LocalRuntimeError, match="aggregate"):
        local_runtime._compare_database_snapshots(
            source,
            local_runtime.DatabaseSnapshot(16, ("head",), {"users": 2}),
        )


def test_pre_migration_backup_skips_empty_database(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        local_runtime,
        "create_local_backup",
        lambda *_args, **_kwargs: pytest.fail("empty first-run DB must not be backed up"),
    )
    assert (
        pre_migration_backup(
            tmp_path,
            _config(),
            DatabaseProbe(reachable=True, has_public_tables=False),
        )
        is None
    )


def test_pre_migration_backup_skips_database_already_at_head(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(local_runtime, "database_migrations_current", lambda _root: True)
    monkeypatch.setattr(
        local_runtime,
        "create_local_backup",
        lambda *_args, **_kwargs: pytest.fail("current DB must not create restart dumps"),
    )

    assert (
        pre_migration_backup(
            tmp_path,
            _config(),
            DatabaseProbe(reachable=True, has_public_tables=True),
        )
        is None
    )


def test_pre_migration_backup_runs_when_database_is_behind(monkeypatch, tmp_path: Path) -> None:
    expected = tmp_path / "backup.dump"
    monkeypatch.setattr(local_runtime, "database_migrations_current", lambda _root: False)
    monkeypatch.setattr(
        local_runtime,
        "create_local_backup",
        lambda _root, _config: expected,
    )

    assert (
        pre_migration_backup(
            tmp_path,
            _config(),
            DatabaseProbe(reachable=True, has_public_tables=True),
        )
        == expected
    )


def test_runtime_commands_fix_ports_and_same_origin_proxy() -> None:
    assert ["--port", "8765"] == backend_command()[6:8]
    assert backend_command()[-1] == "--no-access-log"
    assert frontend_command()[-4:] == ["--hostname", "127.0.0.1", "--port", "3000"]
    assert frontend_environment()["FOUNDEROS_API_PROXY_TARGET"] == BACKEND_BASE_URL
    assert frontend_environment()["NEXT_TELEMETRY_DISABLED"] == "1"
    assert WEB_BIND_BASE_URL == "http://127.0.0.1:3000"
    assert WEB_BASE_URL == WEB_BIND_BASE_URL
    assert "localhost" not in WEB_BASE_URL


def test_frontend_environment_does_not_inherit_backend_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/safe/bin")
    sensitive_names = (
        "DATABASE_URL",
        "API_AUTH_KEY",
        "FOUNDEROS_SECRET_ENCRYPTION_KEY",
        "FOUNDEROS_GITHUB_APP_PRIVATE_KEY",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "NODE_OPTIONS",
        "NEXT_PUBLIC_UNAPPROVED_VALUE",
    )
    for name in sensitive_names:
        monkeypatch.setenv(name, "must-not-reach-node")

    env = frontend_environment()

    assert env["PATH"] == "/safe/bin"
    assert env["FOUNDEROS_API_PROXY_TARGET"] == BACKEND_BASE_URL
    assert env["NEXT_TELEMETRY_DISABLED"] == "1"
    assert all(name not in env for name in sensitive_names)


def test_frontend_dependency_install_uses_sanitized_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "web").mkdir()
    monkeypatch.setattr(
        local_runtime,
        "frontend_install_command",
        lambda _root: ["npm", "ci"],
    )
    monkeypatch.setattr(local_runtime, "command_available", lambda _name: True)
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured.update({"command": command, **kwargs})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(local_runtime.subprocess, "run", fake_run)

    ensure_frontend_dependencies(tmp_path)

    assert captured["command"] == ["npm", "ci"]
    assert captured["env"] == frontend_environment()


def test_runtime_state_round_trip_is_local_and_sanitized(tmp_path: Path) -> None:
    state = RuntimeState(
        supervisor_pid=101,
        backend_pid=102,
        frontend_pid=103,
        started_at="2026-07-14T00:00:00+00:00",
        repo_root=str(tmp_path.resolve()),
        supervisor_start_signature="Mon Jul 14 10:00:00 2026",
        backend_start_signature="Mon Jul 14 10:00:01 2026",
        frontend_start_signature="Mon Jul 14 10:00:02 2026",
    )
    write_runtime_state(tmp_path, state)
    assert read_runtime_state(tmp_path) == state
    content = (tmp_path / ".local/runtime.json").read_text(encoding="utf-8")
    assert "token" not in content.casefold()
    assert "password" not in content.casefold()


def test_runtime_identity_accepts_default_cli_only_for_same_root_and_start(
    monkeypatch, tmp_path: Path
) -> None:
    signature = "Mon Jul 14 10:00:00 2026"
    state = RuntimeState(
        101,
        102,
        103,
        "2026-07-14T00:00:00+00:00",
        str(tmp_path.resolve()),
        signature,
    )
    monkeypatch.setattr(
        local_runtime,
        "process_command",
        lambda _pid: "python scripts/start_local.py",
    )
    monkeypatch.setattr(local_runtime, "process_cwd", lambda _pid: tmp_path.resolve())
    monkeypatch.setattr(
        local_runtime,
        "process_start_signature",
        lambda _pid: signature,
    )

    assert local_runtime.runtime_process_matches(tmp_path, state) is True
    assert local_runtime.runtime_process_matches(tmp_path / "other", state) is False


def test_stale_runtime_record_never_stops_an_unrelated_process(monkeypatch, tmp_path: Path) -> None:
    write_runtime_state(
        tmp_path,
        RuntimeState(
            101,
            102,
            103,
            "2026-07-14T00:00:00+00:00",
            str(tmp_path.resolve()),
            "Mon Jul 14 10:00:00 2026",
        ),
    )
    monkeypatch.setattr(
        local_runtime,
        "runtime_process_matches",
        lambda _root, _state: False,
    )

    def unexpected_kill(_pid: int, _signal: signal.Signals) -> None:
        raise AssertionError("stale records must never signal an unrelated PID")

    monkeypatch.setattr(local_runtime.os, "kill", unexpected_kill)
    monkeypatch.setattr(local_runtime, "process_command", lambda _pid: "other process")
    assert stop_recorded_runtime(tmp_path) is False
    assert (tmp_path / ".local/runtime.json").exists()


def test_stop_signals_only_the_verified_supervisor(monkeypatch, tmp_path: Path) -> None:
    state = RuntimeState(
        201,
        202,
        203,
        "2026-07-14T00:00:00+00:00",
        str(tmp_path.resolve()),
        "Mon Jul 14 10:00:00 2026",
    )
    write_runtime_state(tmp_path, state)
    monkeypatch.setattr(
        local_runtime,
        "runtime_process_matches",
        lambda root, current: root == tmp_path and current == state,
    )
    supervisor_states = iter(["verified supervisor", None])

    def process_state(pid: int):
        return next(supervisor_states) if pid == 201 else None

    monkeypatch.setattr(local_runtime, "process_command", process_state)
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(
        local_runtime.os,
        "kill",
        lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )

    assert stop_recorded_runtime(tmp_path) is True
    assert signals == [(201, signal.SIGTERM)]
    assert not (tmp_path / ".local/runtime.json").exists()


def test_dead_supervisor_stops_only_verified_orphan_children(monkeypatch, tmp_path: Path) -> None:
    state = RuntimeState(
        301,
        302,
        303,
        "2026-07-14T00:00:00+00:00",
        str(tmp_path.resolve()),
        "supervisor-start",
        "backend-start",
        "frontend-start",
    )
    write_runtime_state(tmp_path, state)
    alive = {302: True, 303: True}

    def command(pid: int):
        if pid == 301:
            return None
        if not alive.get(pid, False):
            return None
        return "uv run uvicorn app.main:app" if pid == 302 else "npm run dev"

    monkeypatch.setattr(local_runtime, "process_command", command)
    monkeypatch.setattr(
        local_runtime,
        "process_cwd",
        lambda pid: tmp_path.resolve() if pid == 302 else (tmp_path / "web").resolve(),
    )
    monkeypatch.setattr(
        local_runtime,
        "process_start_signature",
        lambda pid: "backend-start" if pid == 302 else "frontend-start",
    )
    monkeypatch.setattr(local_runtime.os, "getpgid", lambda pid: pid)
    signaled: list[tuple[int, signal.Signals]] = []

    def kill_group(pid: int, sent_signal: signal.Signals) -> None:
        signaled.append((pid, sent_signal))
        alive[pid] = False

    monkeypatch.setattr(local_runtime.os, "killpg", kill_group)
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)

    assert stop_recorded_runtime(tmp_path, timeout_seconds=1) is True
    assert signaled == [(303, signal.SIGTERM), (302, signal.SIGTERM)]
    assert not (tmp_path / ".local/runtime.json").exists()


def test_dead_supervisor_preserves_state_for_unverified_live_child(
    monkeypatch, tmp_path: Path
) -> None:
    state = RuntimeState(
        401,
        402,
        0,
        "2026-07-14T00:00:00+00:00",
        str(tmp_path.resolve()),
        "supervisor-start",
        "recorded-backend-start",
        None,
    )
    write_runtime_state(tmp_path, state)
    monkeypatch.setattr(
        local_runtime,
        "process_command",
        lambda pid: None if pid == 401 else "uv run uvicorn app.main:app",
    )
    monkeypatch.setattr(local_runtime, "process_cwd", lambda _pid: tmp_path.resolve())
    monkeypatch.setattr(
        local_runtime,
        "process_start_signature",
        lambda _pid: "different-process-start",
    )
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)
    monkeypatch.setattr(
        local_runtime.os,
        "killpg",
        lambda *_args: pytest.fail("unverified child must not be signaled"),
    )

    assert stop_recorded_runtime(tmp_path, timeout_seconds=0.1) is False
    assert (tmp_path / ".local/runtime.json").exists()


def test_dead_supervisor_never_reports_success_while_app_port_is_live(
    monkeypatch, tmp_path: Path
) -> None:
    state = RuntimeState(
        501,
        0,
        0,
        "2026-07-14T00:00:00+00:00",
        str(tmp_path.resolve()),
        "supervisor-start",
    )
    write_runtime_state(tmp_path, state)
    monkeypatch.setattr(local_runtime, "process_command", lambda _pid: None)
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: True)

    assert stop_recorded_runtime(tmp_path, timeout_seconds=0.01) is False
    assert (tmp_path / ".local/runtime.json").exists()


def test_supervisor_orders_backup_and_migrations_before_children(
    monkeypatch, tmp_path: Path
) -> None:
    events: list[str] = []
    installed_signal_handlers: dict[signal.Signals, object] = {}
    signal_registrations: list[tuple[signal.Signals, object]] = []

    def install_signal(sent_signal, handler):
        previous = installed_signal_handlers.get(sent_signal, signal.SIG_DFL)
        installed_signal_handlers[sent_signal] = handler
        signal_registrations.append((sent_signal, handler))
        return previous

    monkeypatch.setattr(local_runtime.signal, "signal", install_signal)
    monkeypatch.setattr(local_runtime, "process_cwd", lambda _pid: tmp_path.resolve())
    monkeypatch.setattr(
        local_runtime,
        "process_start_signature",
        lambda _pid: "Mon Jul 14 10:00:00 2026",
    )
    monkeypatch.setattr(local_runtime, "tcp_port_in_use", lambda _host, _port: False)
    monkeypatch.setattr(
        local_runtime,
        "ensure_database",
        lambda _root, _config: (
            events.append("database") or DatabaseProbe(reachable=True, has_public_tables=True)
        ),
    )
    monkeypatch.setattr(
        local_runtime,
        "ensure_frontend_dependencies",
        lambda _root: events.append("dependencies"),
    )
    monkeypatch.setattr(
        local_runtime,
        "pre_migration_backup",
        lambda _root, _config, _probe: events.append("backup"),
    )
    monkeypatch.setattr(
        local_runtime,
        "apply_migrations",
        lambda _root: events.append("migrations"),
    )

    class FakeProcess:
        def __init__(self, command, **_kwargs):
            self.pid = 301 if "uvicorn" in command else 302
            self.returncode = None
            events.append("backend" if "uvicorn" in command else "frontend")

        def poll(self):
            return None

    monkeypatch.setattr(local_runtime.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(
        local_runtime,
        "_capture_child_start_signature",
        lambda _root, *, child, pid: f"{child}-{pid}",
    )
    monkeypatch.setattr(
        local_runtime,
        "wait_for_url",
        lambda url, **_kwargs: (
            events.append("backend-ready" if url.startswith(BACKEND_BASE_URL) else "frontend-ready")
            or True
        ),
    )
    monkeypatch.setattr(
        local_runtime,
        "write_runtime_state",
        lambda _root, _state: events.append("state"),
    )
    monkeypatch.setattr(local_runtime, "read_runtime_state", lambda _root: None)
    monkeypatch.setattr(
        local_runtime,
        "_terminate_child",
        lambda _child: events.append("shutdown"),
    )

    def close_terminal_after_readiness(**_kwargs):
        events.append("open")
        handler = installed_signal_handlers[signal.SIGHUP]
        assert callable(handler)
        handler(signal.SIGHUP, None)

    monkeypatch.setattr(local_runtime, "open_local_product", close_terminal_after_readiness)
    assert local_runtime.supervise_local_runtime(tmp_path, _config(), no_open=True) == 0

    assert events[:10] == [
        "database",
        "dependencies",
        "backup",
        "migrations",
        "backend",
        "state",
        "backend-ready",
        "frontend",
        "state",
        "frontend-ready",
    ]
    assert events[10] == "open"
    assert any(
        sent_signal == signal.SIGHUP and callable(handler)
        for sent_signal, handler in signal_registrations
    )


def test_no_open_mode_creates_no_invite_and_prints_no_credential(monkeypatch, capsys) -> None:
    async def unexpected_destination(_base_url: str):
        raise AssertionError("no-open mode must not create an invite")

    monkeypatch.setattr(local_runtime, "_prepare_founder_destination", unexpected_destination)

    async def empty_installation() -> bool:
        return False

    monkeypatch.setattr(
        local_runtime,
        "_has_login_capable_local_member",
        empty_installation,
    )
    open_local_product(no_open=True)
    output = capsys.readouterr().out
    assert WEB_BASE_URL in output
    assert "http://localhost:3000" not in output
    assert "#token=" not in output
    assert "create_founder_invite.py" in output


def test_no_open_existing_installation_points_only_to_login(monkeypatch, capsys) -> None:
    async def existing_installation() -> bool:
        return True

    monkeypatch.setattr(
        local_runtime,
        "_has_login_capable_local_member",
        existing_installation,
    )

    open_local_product(no_open=True)

    output = capsys.readouterr().out
    assert f"{WEB_BASE_URL}/login" in output
    assert "create_founder_invite.py" not in output


def test_automatic_invite_url_is_passed_only_to_browser(monkeypatch, capsys) -> None:
    secret_url = f"{WEB_BASE_URL}/start#token=never-print-this"

    async def fake_destination(_base_url: str) -> FounderDestination:
        return FounderDestination(url=secret_url, invite_id=SimpleNamespace())

    opened: list[str] = []
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("FOUNDEROS_LOCAL_NO_OPEN", raising=False)
    monkeypatch.setattr(local_runtime, "_prepare_founder_destination", fake_destination)
    open_local_product(no_open=False, browser_open=lambda url: opened.append(url) or True)
    assert opened == [secret_url]
    assert "never-print-this" not in capsys.readouterr().out


def test_failed_first_founder_browser_handoff_revokes_invite_in_same_event_loop(
    monkeypatch, capsys
) -> None:
    secret_url = f"{WEB_BASE_URL}/start#token=must-never-print"
    invite_id = SimpleNamespace()
    loops: list[asyncio.AbstractEventLoop] = []
    revoked: list[object] = []

    async def destination(_base_url: str) -> FounderDestination:
        loops.append(asyncio.get_running_loop())
        return FounderDestination(url=secret_url, invite_id=invite_id)

    async def revoke(current_invite_id: object) -> None:
        loops.append(asyncio.get_running_loop())
        revoked.append(current_invite_id)

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("FOUNDEROS_LOCAL_NO_OPEN", raising=False)
    monkeypatch.setattr(local_runtime, "_prepare_founder_destination", destination)
    monkeypatch.setattr(local_runtime, "_revoke_unused_local_invite", revoke)

    open_local_product(no_open=False, browser_open=lambda _url: False)

    assert revoked == [invite_id]
    assert len(loops) == 2
    assert loops[0] is loops[1]
    assert "must-never-print" not in capsys.readouterr().out


def test_failed_invite_revocation_is_not_silently_reported_as_safe(monkeypatch, capsys) -> None:
    secret = "private-database-error"

    async def destination(_base_url: str) -> FounderDestination:
        return FounderDestination(
            url=f"{WEB_BASE_URL}/start#token=must-never-print",
            invite_id=SimpleNamespace(),
        )

    async def failed_revoke(_invite_id: object) -> None:
        raise RuntimeError(secret)

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("FOUNDEROS_LOCAL_NO_OPEN", raising=False)
    monkeypatch.setattr(local_runtime, "_prepare_founder_destination", destination)
    monkeypatch.setattr(local_runtime, "_revoke_unused_local_invite", failed_revoke)

    with pytest.raises(LocalRuntimeError, match="could not be revoked"):
        open_local_product(no_open=False, browser_open=lambda _url: False)

    output = capsys.readouterr().out
    assert secret not in output
    assert "must-never-print" not in output


def test_existing_founder_browser_failure_never_suggests_a_new_invite(monkeypatch, capsys) -> None:
    async def existing_destination(_base_url: str) -> FounderDestination:
        return FounderDestination(url=f"{WEB_BASE_URL}/login", invite_id=None)

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("FOUNDEROS_LOCAL_NO_OPEN", raising=False)
    monkeypatch.setattr(
        local_runtime,
        "_prepare_founder_destination",
        existing_destination,
    )

    open_local_product(no_open=False, browser_open=lambda _url: False)

    output = capsys.readouterr().out
    assert f"{WEB_BASE_URL}/login" in output
    assert "create_founder_invite.py" not in output


def test_founder_prepare_failure_keeps_runtime_ready_and_sanitized(monkeypatch, capsys) -> None:
    secret = "database-password-must-not-escape"

    async def failed_destination(_base_url: str) -> FounderDestination:
        raise RuntimeError(secret)

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("FOUNDEROS_LOCAL_NO_OPEN", raising=False)
    monkeypatch.setattr(local_runtime, "_prepare_founder_destination", failed_destination)

    async def unknown_installation() -> bool:
        raise RuntimeError(secret)

    monkeypatch.setattr(
        local_runtime,
        "_has_login_capable_local_member",
        unknown_installation,
    )
    open_local_product(no_open=False, browser_open=lambda _url: True)
    output = capsys.readouterr().out
    assert WEB_BASE_URL in output
    assert "create_founder_invite.py" not in output
    assert secret not in output


def test_default_cli_mode_is_run_and_supports_no_open() -> None:
    assert _normalized_argv([]) == ["run"]
    assert _normalized_argv(["--no-open"]) == ["run", "--no-open"]
    assert _normalized_argv(["doctor"]) == ["doctor"]
