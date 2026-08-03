from __future__ import annotations

import os
from pathlib import Path
import platform
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.repository_intelligence.l2_isolation as l2
from app.services.repository_intelligence.l2_isolation import (
    RepositoryL2IsolationPolicy,
    RepositoryL2IsolationRequest,
    RepositoryL2UnavailableError,
    RepositoryL2ValidationError,
    verify_hostile_synthetic_l2_isolation,
)


def _policy(data_path: Path, **overrides: object) -> RepositoryL2IsolationPolicy:
    values: dict[str, object] = {
        "data_path": data_path,
        "wall_time_seconds": 1.5,
        "cpu_seconds": 1,
        "max_memory_bytes": 48 * 1024 * 1024,
        "max_file_bytes": 32 * 1024,
        "max_processes": 6,
        "max_output_bytes": 4096,
        "max_open_files": 24,
        "max_scratch_bytes": 128 * 1024,
    }
    values.update(overrides)
    return RepositoryL2IsolationPolicy(**values)  # type: ignore[arg-type]


def _request(run_id: str | None = None) -> RepositoryL2IsolationRequest:
    return RepositoryL2IsolationRequest(run_id=run_id or f"synthetic-l2-{uuid4().hex[:12]}")


def _assert_no_runs(data_path: Path) -> None:
    runs = data_path / "repository-intelligence" / "l2-synthetic-runs"
    assert not runs.exists() or list(runs.iterdir()) == []


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS sandbox proof")
def test_hostile_synthetic_profile_fails_closed_without_memory_enforcement(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "ri-l2-data"
    ambient_marker = "ambient-secret-that-must-never-be-forwarded"
    os.environ["FOUNDEROS_L2_AMBIENT_SENTINEL"] = ambient_marker
    try:
        with pytest.raises(RepositoryL2UnavailableError) as caught:
            verify_hostile_synthetic_l2_isolation(
                _request(),
                policy=_policy(data_path),
            )
    finally:
        os.environ.pop("FOUNDEROS_L2_AMBIENT_SENTINEL", None)

    assert str(caught.value) == ("the approved L2 backend cannot enforce all hard resource bounds")
    assert ambient_marker not in str(caught.value)
    assert "FOUNDEROS_SYNTHETIC_SECRET_MARKER" not in str(caught.value)
    assert str(l2.REPOSITORY_ROOT) not in str(caught.value)
    _assert_no_runs(data_path)


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS sandbox proof")
def test_candidate_profile_contains_nonmemory_hostile_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy(tmp_path / "data")
    run = tmp_path / "candidate-run"
    run.mkdir()
    paths = l2._create_synthetic_fixture(run)

    def apply_nonmemory_limits(selected: RepositoryL2IsolationPolicy) -> None:
        l2._set_limit(l2.resource.RLIMIT_CPU, selected.cpu_seconds)
        l2._set_limit(l2.resource.RLIMIT_FSIZE, selected.max_file_bytes)
        l2._set_limit(l2.resource.RLIMIT_NOFILE, selected.max_open_files)
        if hasattr(l2.resource, "RLIMIT_NPROC"):
            l2._set_limit(l2.resource.RLIMIT_NPROC, selected.max_processes)

    monkeypatch.setattr(l2, "_apply_resource_limits", apply_nonmemory_limits)
    network_listener = None
    socket_listeners = None
    socket_root = None
    try:
        l2._compile_probe(paths, policy=policy)
        profile = l2._sandbox_profile(paths)
        network_listener = l2._open_synthetic_network_listener()
        (
            socket_listeners,
            database_socket_path,
            docker_socket_path,
            socket_root,
        ) = l2._open_synthetic_unix_listeners(run_id="candidate-profile")
        environment = l2._minimal_environment(
            paths,
            network_port=int(network_listener.getsockname()[1]),
            database_socket_path=database_socket_path,
            docker_socket_path=docker_socket_path,
        )
        checks = tuple(check for check in l2.RepositoryL2Check if check != "memory")
        receipts = [
            l2._assess_synthetic_check(
                check,
                result=l2._run_synthetic_check(
                    check,
                    profile=profile,
                    paths=paths,
                    policy=policy,
                    environment=environment,
                ),
                paths=paths,
                policy=policy,
            )
            for check in checks
        ]
    finally:
        if network_listener is not None:
            network_listener.close()
        if socket_listeners is not None:
            for listener in socket_listeners:
                listener.close()
        if socket_root is not None:
            l2._remove_socket_probe_directory(socket_root)
        l2._remove_run_directory(run, runs_root=tmp_path)

    assert [receipt.check for receipt in receipts] == list(checks)
    assert {receipt.status for receipt in receipts} == {"passed", "contained"}


def test_l2_request_is_closed_to_synthetic_fixture_and_profile(tmp_path: Path) -> None:
    with pytest.raises(RepositoryL2ValidationError):
        verify_hostile_synthetic_l2_isolation(
            RepositoryL2IsolationRequest(
                run_id="real-repository",
                synthetic_fixture=False,  # type: ignore[arg-type]
            ),
            policy=_policy(tmp_path / "data"),
        )

    with pytest.raises(RepositoryL2ValidationError):
        verify_hostile_synthetic_l2_isolation(
            _request("../escape"),
            policy=_policy(tmp_path / "data"),
        )


def test_l2_policy_rejects_unsafe_or_unbounded_configuration(tmp_path: Path) -> None:
    repository_root = l2.REPOSITORY_ROOT
    invalid_policies = (
        _policy(repository_root / ".local" / "ri-l2"),
        _policy(tmp_path / "data", wall_time_seconds=31),
        _policy(tmp_path / "data", max_memory_bytes=1024),
        _policy(tmp_path / "data", max_file_bytes=256 * 1024),
        _policy(tmp_path / "data", max_processes=64),
        _policy(tmp_path / "data", max_output_bytes=2 * 1024 * 1024),
        _policy(tmp_path / "data", max_scratch_bytes=8 * 1024 * 1024),
        _policy(Path("relative-data")),
    )
    for policy in invalid_policies:
        with pytest.raises(RepositoryL2ValidationError):
            policy.validate()


def test_l2_fails_closed_when_host_or_backend_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(l2.platform, "system", lambda: "Linux")
    with pytest.raises(RepositoryL2UnavailableError):
        verify_hostile_synthetic_l2_isolation(
            _request(),
            policy=_policy(tmp_path / "data"),
        )

    monkeypatch.setattr(l2.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(l2, "_SANDBOX_EXEC", tmp_path / "missing-sandbox")
    with pytest.raises(RepositoryL2UnavailableError):
        verify_hostile_synthetic_l2_isolation(
            _request(),
            policy=_policy(tmp_path / "data-two"),
        )


def test_l2_fails_closed_without_aggregate_scratch_enforcement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(l2, "_require_memory_limit_support", lambda _policy: None)

    with pytest.raises(RepositoryL2UnavailableError) as caught:
        l2._require_hard_resource_support(_policy(tmp_path / "data"))

    assert str(caught.value) == ("the approved L2 backend cannot enforce all hard resource bounds")


def test_l2_status_receipt_is_sanitized_and_disabled(tmp_path: Path) -> None:
    status = l2.get_hostile_synthetic_l2_isolation_status(
        _request("status-disabled"),
        policy=_policy(tmp_path / "data"),
    )

    assert status.status == "disabled"
    assert status.enabled is False
    assert status.real_repository_l2_enabled is False
    assert status.reason_code == "isolation_unavailable"
    assert status.checks_passed == 0
    material = status.deterministic_json()
    assert str(tmp_path) not in material
    assert "RLIMIT" not in material
    assert "FOUNDEROS_SYNTHETIC_SECRET_MARKER" not in material


def test_l2_status_receipt_reports_verified_only_after_complete_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        l2,
        "verify_hostile_synthetic_l2_isolation",
        lambda _request, *, policy: SimpleNamespace(tests=[object()] * 8),
    )

    status = l2.get_hostile_synthetic_l2_isolation_status(
        _request("status-verified"),
        policy=_policy(tmp_path / "data"),
    )

    assert status.status == "verified"
    assert status.enabled is True
    assert status.reason_code == "verified"
    assert status.checks_passed == 8
    assert status.real_repository_l2_enabled is False


def test_sandbox_profile_is_default_deny_and_has_no_network_allow(
    tmp_path: Path,
) -> None:
    run = tmp_path / "fixture"
    run.mkdir()
    paths = l2._create_synthetic_fixture(run)
    paths.probe_binary.write_bytes(b"synthetic-probe")
    paths.probe_binary.chmod(0o500)
    profile = l2._sandbox_profile(paths)

    assert "(deny default)" in profile
    assert "(deny network*)" in profile
    assert "allow network" not in profile
    assert (
        f'(allow process-exec (literal "{l2._canonical_macos_path(paths.probe_binary)}"))'
        in profile
    )
    assert "process-exec*" not in profile
    assert "process-fork" in profile
    assert str(l2.REPOSITORY_ROOT) not in profile
    assert str(paths.protected) not in profile
    assert str(paths.scratch) in profile or f"/private{paths.scratch}" in profile


def test_receipt_model_rejects_unknown_fields_and_real_repository_enablement() -> None:
    payload = {
        "schema_version": "repository_l2_isolation_receipt.v1",
        "enabled": True,
        "scope": "hostile_synthetic_only",
        "real_repository_l2_enabled": True,
        "backend": "macos_sandbox_exec",
        "host_platform": "darwin",
        "profile_id": "hostile-synthetic-v1",
        "network_policy": "deny_all",
        "source_mode": "read_only",
        "non_root": True,
        "founder_os_access": False,
        "ambient_environment_forwarded": False,
        "docker_socket_mounted": False,
        "memory_limit_status": "enforced",
        "aggregate_disk_limit_status": "enforced",
        "tests": [],
        "command": ["pytest"],
    }
    with pytest.raises(Exception):
        l2.RepositoryL2IsolationReceiptV1.model_validate(payload)
