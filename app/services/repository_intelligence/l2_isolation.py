"""Fail-closed hostile-synthetic L2 isolation proof for RI-009.

The module deliberately exposes no repository path or arbitrary command input.
It compiles a fixed local C probe, executes only that probe through the approved
macOS sandbox profile, applies hard rlimits, and enables nothing unless every
containment check passes. Real-repository L2 remains disabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import math
import os
from pathlib import Path
import platform
import re
import resource
import selectors
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
_CLANG = Path("/usr/bin/clang")
_MEMORY_LIMIT_PROBE = Path("/usr/bin/true")
_READ_CHUNK_BYTES = 64 * 1024
_TERMINATE_GRACE_SECONDS = 0.5
_RECEIPT_MAX_BYTES = 16 * 1024


class RepositoryL2IsolationError(RuntimeError):
    """Sanitized RI-009 isolation failure."""


class RepositoryL2ValidationError(RepositoryL2IsolationError):
    """The L2 request or profile is outside the closed contract."""


class RepositoryL2UnavailableError(RepositoryL2IsolationError):
    """The host cannot prove the required L2 isolation boundary."""


class RepositoryL2ExecutionError(RepositoryL2IsolationError):
    """A hostile synthetic containment proof failed."""


class RepositoryL2OutputLimitError(RepositoryL2ExecutionError):
    """A check or receipt exceeded its bounded output contract."""


class RepositoryL2Profile(StrEnum):
    HOSTILE_SYNTHETIC_V1 = "hostile-synthetic-v1"


class RepositoryL2Check(StrEnum):
    BASELINE = "baseline"
    ESCAPE = "escape"
    OUTPUT = "output"
    TIMEOUT = "timeout"
    CPU = "cpu"
    FILE_SIZE = "file-size"
    FORK = "fork"
    MEMORY = "memory"


RepositoryL2Outcome = Literal[
    "isolated synthetic baseline passed",
    "filesystem socket and network escapes blocked",
    "combined output limit contained",
    "wall-time limit contained",
    "CPU exhaustion contained",
    "file and scratch limits contained",
    "process limit contained",
    "memory limit contained",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RepositoryL2CheckReceiptV1(_StrictModel):
    check: RepositoryL2Check
    status: Literal["passed", "contained"]
    outcome: RepositoryL2Outcome
    exit_code: int | None = Field(default=None, ge=0, le=255)
    signal: int | None = Field(default=None, ge=1, le=128)
    stdout_bytes: int = Field(ge=0, le=2 * 1024 * 1024)
    stderr_bytes: int = Field(ge=0, le=2 * 1024 * 1024)
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @model_validator(mode="after")
    def validate_termination(self) -> RepositoryL2CheckReceiptV1:
        if (self.exit_code is None) == (self.signal is None):
            raise ValueError("L2 receipt requires exactly one termination status")
        passed_checks = {
            RepositoryL2Check.BASELINE,
            RepositoryL2Check.ESCAPE,
        }
        expected_status = "passed" if self.check in passed_checks else "contained"
        if self.status != expected_status:
            raise ValueError("L2 receipt status does not match its check")
        allowed_outcomes: dict[RepositoryL2Check, set[str]] = {
            RepositoryL2Check.BASELINE: {"isolated synthetic baseline passed"},
            RepositoryL2Check.ESCAPE: {"filesystem socket and network escapes blocked"},
            RepositoryL2Check.OUTPUT: {"combined output limit contained"},
            RepositoryL2Check.TIMEOUT: {"wall-time limit contained"},
            RepositoryL2Check.CPU: {"CPU exhaustion contained"},
            RepositoryL2Check.FILE_SIZE: {"file and scratch limits contained"},
            RepositoryL2Check.FORK: {"process limit contained"},
            RepositoryL2Check.MEMORY: {"memory limit contained"},
        }
        if self.outcome not in allowed_outcomes[self.check]:
            raise ValueError("L2 receipt outcome does not match its check")
        if self.status == "passed" and self.exit_code != 0:
            raise ValueError("passed L2 receipt requires exit code zero")
        return self


class RepositoryL2IsolationReceiptV1(_StrictModel):
    schema_version: Literal["repository_l2_isolation_receipt.v1"]
    enabled: Literal[True]
    scope: Literal["hostile_synthetic_only"]
    real_repository_l2_enabled: Literal[False]
    backend: Literal["macos_sandbox_exec"]
    host_platform: Literal["darwin"]
    profile_id: Literal[RepositoryL2Profile.HOSTILE_SYNTHETIC_V1]
    network_policy: Literal["deny_all"]
    source_mode: Literal["read_only"]
    non_root: Literal[True]
    founder_os_access: Literal[False]
    ambient_environment_forwarded: Literal[False]
    docker_socket_mounted: Literal[False]
    memory_limit_status: Literal["enforced"]
    aggregate_disk_limit_status: Literal["enforced"]
    tests: list[RepositoryL2CheckReceiptV1] = Field(min_length=8, max_length=8)

    @classmethod
    def _required_checks(cls) -> list[RepositoryL2Check]:
        return list(RepositoryL2Check)

    def model_post_init(self, __context: object) -> None:
        checks = [item.check for item in self.tests]
        if checks != self._required_checks():
            raise ValueError("L2 receipt must contain approved checks in exact order")

    def deterministic_json(self) -> str:
        raw = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(raw.encode("utf-8")) > _RECEIPT_MAX_BYTES:
            raise RepositoryL2OutputLimitError("L2 isolation receipt exceeded its configured bound")
        return raw


class RepositoryL2IsolationStatusReceiptV1(_StrictModel):
    schema_version: Literal["repository_l2_isolation_status.v1"]
    status: Literal["verified", "disabled"]
    enabled: bool
    scope: Literal["hostile_synthetic_only"]
    real_repository_l2_enabled: Literal[False]
    backend: Literal["macos_sandbox_exec"]
    profile_id: Literal[RepositoryL2Profile.HOSTILE_SYNTHETIC_V1]
    reason_code: Literal["verified", "isolation_unavailable"]
    checks_passed: int = Field(ge=0, le=8)

    @model_validator(mode="after")
    def validate_status_shape(self) -> RepositoryL2IsolationStatusReceiptV1:
        verified = self.status == "verified"
        if (
            self.enabled != verified
            or (self.reason_code == "verified") != verified
            or self.checks_passed != (8 if verified else 0)
        ):
            raise ValueError("L2 isolation status receipt is internally inconsistent")
        return self

    def deterministic_json(self) -> str:
        raw = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(raw.encode("utf-8")) > _RECEIPT_MAX_BYTES:
            raise RepositoryL2OutputLimitError(
                "L2 isolation status receipt exceeded its configured bound"
            )
        return raw


@dataclass(frozen=True)
class RepositoryL2IsolationPolicy:
    data_path: Path
    wall_time_seconds: float = 1.5
    cpu_seconds: int = 1
    max_memory_bytes: int = 64 * 1024 * 1024
    max_file_bytes: int = 64 * 1024
    max_processes: int = 8
    max_output_bytes: int = 8 * 1024
    max_open_files: int = 32
    max_scratch_bytes: int = 256 * 1024

    def validate(self) -> None:
        if (
            isinstance(self.wall_time_seconds, bool)
            or not isinstance(self.wall_time_seconds, (int, float))
            or not math.isfinite(float(self.wall_time_seconds))
            or self.wall_time_seconds <= 0
            or self.wall_time_seconds > 30
        ):
            raise RepositoryL2ValidationError("L2 wall-time bound is outside the approved range")
        integer_bounds = (
            self.cpu_seconds,
            self.max_memory_bytes,
            self.max_file_bytes,
            self.max_processes,
            self.max_output_bytes,
            self.max_open_files,
            self.max_scratch_bytes,
        )
        if any(type(value) is not int or value <= 0 for value in integer_bounds):
            raise RepositoryL2ValidationError("L2 resource bounds must be positive")
        if self.cpu_seconds > 10:
            raise RepositoryL2ValidationError("L2 CPU bound is outside the approved range")
        if self.wall_time_seconds <= self.cpu_seconds:
            raise RepositoryL2ValidationError("L2 wall-time bound must exceed the CPU bound")
        if not 16 * 1024 * 1024 <= self.max_memory_bytes <= 512 * 1024 * 1024:
            raise RepositoryL2ValidationError("L2 memory bound is outside the approved range")
        if self.max_file_bytes > self.max_scratch_bytes:
            raise RepositoryL2ValidationError("L2 file bound cannot exceed the scratch bound")
        if self.max_processes > 32 or self.max_output_bytes > 1024 * 1024:
            raise RepositoryL2ValidationError(
                "L2 process or output bound is outside the approved range"
            )
        if self.max_open_files > 128 or self.max_scratch_bytes > 4 * 1024 * 1024:
            raise RepositoryL2ValidationError(
                "L2 file-descriptor or scratch bound is outside the approved range"
            )
        if not isinstance(self.data_path, Path):
            raise RepositoryL2ValidationError("L2 runtime data path must be a path")
        data_path = self.data_path.expanduser()
        if not data_path.is_absolute():
            raise RepositoryL2ValidationError("L2 runtime data path must be absolute")
        if data_path.is_symlink():
            raise RepositoryL2ValidationError("L2 runtime data path cannot be a symbolic link")
        if _is_within(data_path.resolve(strict=False), REPOSITORY_ROOT.resolve(strict=True)):
            raise RepositoryL2ValidationError("L2 runtime data path must stay outside FounderOS")


@dataclass(frozen=True)
class RepositoryL2IsolationRequest:
    run_id: str
    profile_id: RepositoryL2Profile = RepositoryL2Profile.HOSTILE_SYNTHETIC_V1
    synthetic_fixture: Literal[True] = True


@dataclass(frozen=True)
class _SyntheticPaths:
    root: Path
    source: Path
    scratch: Path
    protected: Path
    outside_write: Path
    protected_file: Path
    probe_source: Path
    probe_binary: Path


@dataclass(frozen=True)
class _ProcessResult:
    return_code: int | None
    signal_number: int | None
    stdout: bytes
    stderr: bytes
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool = False
    output_limited: bool = False


def verify_hostile_synthetic_l2_isolation(
    request: RepositoryL2IsolationRequest,
    *,
    policy: RepositoryL2IsolationPolicy,
) -> RepositoryL2IsolationReceiptV1:
    """Prove the closed RI-009 profile on hostile synthetic fixtures only."""

    policy.validate()
    run_id = _validate_request(request)
    _validate_host(policy)
    _require_hard_resource_support(policy)
    data_root = _prepare_private_data_root(policy.data_path)
    repository_intelligence_root = data_root / "repository-intelligence"
    _ensure_private_directory(repository_intelligence_root)
    runs_root = repository_intelligence_root / "l2-synthetic-runs"
    _ensure_private_directory(runs_root)
    run_directory = runs_root / run_id
    created_run = False
    network_listener: socket.socket | None = None
    protected_socket_listeners: tuple[socket.socket, socket.socket] | None = None
    protected_socket_root: Path | None = None
    database_socket_path: Path | None = None
    docker_socket_path: Path | None = None
    try:
        try:
            run_directory.mkdir(mode=0o700, exist_ok=False)
        except OSError as exc:
            raise RepositoryL2UnavailableError(
                "L2 synthetic run directory could not be prepared"
            ) from exc
        created_run = True
        paths = _create_synthetic_fixture(run_directory)
        _compile_probe(paths, policy=policy)
        profile = _sandbox_profile(paths)
        network_listener = _open_synthetic_network_listener()
        (
            protected_socket_listeners,
            database_socket_path,
            docker_socket_path,
            protected_socket_root,
        ) = _open_synthetic_unix_listeners(
            run_id=run_id,
        )
        network_port = int(network_listener.getsockname()[1])
        environment = _minimal_environment(
            paths,
            network_port=network_port,
            database_socket_path=database_socket_path,
            docker_socket_path=docker_socket_path,
        )
        checks = [
            _assess_synthetic_check(
                check,
                result=_run_synthetic_check(
                    check,
                    profile=profile,
                    paths=paths,
                    policy=policy,
                    environment=environment,
                ),
                paths=paths,
                policy=policy,
            )
            for check in RepositoryL2Check
        ]
        receipt = RepositoryL2IsolationReceiptV1(
            schema_version="repository_l2_isolation_receipt.v1",
            enabled=True,
            scope="hostile_synthetic_only",
            real_repository_l2_enabled=False,
            backend="macos_sandbox_exec",
            host_platform="darwin",
            profile_id=RepositoryL2Profile.HOSTILE_SYNTHETIC_V1,
            network_policy="deny_all",
            source_mode="read_only",
            non_root=True,
            founder_os_access=False,
            ambient_environment_forwarded=False,
            docker_socket_mounted=False,
            memory_limit_status="enforced",
            aggregate_disk_limit_status="enforced",
            tests=checks,
        )
        receipt.deterministic_json()
        return receipt
    finally:
        if network_listener is not None:
            network_listener.close()
        if protected_socket_listeners is not None:
            for listener in protected_socket_listeners:
                listener.close()
        cleanup_error: RepositoryL2UnavailableError | None = None
        if protected_socket_root is not None:
            try:
                _remove_socket_probe_directory(protected_socket_root)
            except RepositoryL2UnavailableError as exc:
                cleanup_error = exc
        if created_run:
            try:
                _remove_run_directory(run_directory, runs_root=runs_root)
            except RepositoryL2UnavailableError as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        if cleanup_error is not None:
            raise cleanup_error


def get_hostile_synthetic_l2_isolation_status(
    request: RepositoryL2IsolationRequest,
    *,
    policy: RepositoryL2IsolationPolicy,
) -> RepositoryL2IsolationStatusReceiptV1:
    """Return a bounded status-only receipt without exposing failure details."""

    try:
        proof = verify_hostile_synthetic_l2_isolation(request, policy=policy)
    except RepositoryL2ValidationError:
        raise
    except RepositoryL2IsolationError:
        status = RepositoryL2IsolationStatusReceiptV1(
            schema_version="repository_l2_isolation_status.v1",
            status="disabled",
            enabled=False,
            scope="hostile_synthetic_only",
            real_repository_l2_enabled=False,
            backend="macos_sandbox_exec",
            profile_id=RepositoryL2Profile.HOSTILE_SYNTHETIC_V1,
            reason_code="isolation_unavailable",
            checks_passed=0,
        )
    else:
        status = RepositoryL2IsolationStatusReceiptV1(
            schema_version="repository_l2_isolation_status.v1",
            status="verified",
            enabled=True,
            scope="hostile_synthetic_only",
            real_repository_l2_enabled=False,
            backend="macos_sandbox_exec",
            profile_id=RepositoryL2Profile.HOSTILE_SYNTHETIC_V1,
            reason_code="verified",
            checks_passed=len(proof.tests),
        )
    status.deterministic_json()
    return status


def _validate_request(request: RepositoryL2IsolationRequest) -> str:
    if request.synthetic_fixture is not True:
        raise RepositoryL2ValidationError("RI-009 accepts hostile synthetic fixtures only")
    if type(request.profile_id) is not RepositoryL2Profile:
        raise RepositoryL2ValidationError("L2 execution profile is invalid")
    if request.profile_id != RepositoryL2Profile.HOSTILE_SYNTHETIC_V1:
        raise RepositoryL2ValidationError("L2 execution profile is not approved")
    if not isinstance(request.run_id, str) or _RUN_ID_RE.fullmatch(request.run_id) is None:
        raise RepositoryL2ValidationError("L2 run id is invalid")
    return request.run_id


def _validate_host(policy: RepositoryL2IsolationPolicy) -> None:
    if platform.system().casefold() != "darwin":
        raise RepositoryL2UnavailableError("L2 isolation is unavailable on this host platform")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise RepositoryL2UnavailableError("L2 isolation refuses root execution")
    del policy
    for executable in (_SANDBOX_EXEC, _CLANG, _MEMORY_LIMIT_PROBE):
        try:
            resolved = executable.resolve(strict=True)
        except OSError as exc:
            raise RepositoryL2UnavailableError("an approved L2 host tool is unavailable") from exc
        if resolved != executable or not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise RepositoryL2UnavailableError("an approved L2 host tool is unavailable")


def _require_memory_limit_support(policy: RepositoryL2IsolationPolicy) -> None:
    try:
        completed = subprocess.run(
            [str(_MEMORY_LIMIT_PROBE)],
            env={"PATH": "/usr/bin:/bin"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            check=False,
            timeout=1.0,
            preexec_fn=lambda: _apply_memory_limit(policy.max_memory_bytes),
        )
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        raise RepositoryL2UnavailableError(
            "the approved L2 backend cannot enforce the memory bound"
        ) from exc
    if completed.returncode != 0:
        raise RepositoryL2UnavailableError(
            "the approved L2 backend cannot enforce the memory bound"
        )


def _require_hard_resource_support(policy: RepositoryL2IsolationPolicy) -> None:
    missing = 0
    for check in (
        _require_memory_limit_support,
        _require_aggregate_scratch_limit_support,
    ):
        try:
            check(policy)
        except RepositoryL2UnavailableError:
            missing += 1
    if missing:
        raise RepositoryL2UnavailableError(
            "the approved L2 backend cannot enforce all hard resource bounds"
        )


def _apply_memory_limit(max_memory_bytes: int) -> None:
    for name in ("RLIMIT_AS", "RLIMIT_DATA", "RLIMIT_RSS"):
        if not hasattr(resource, name):
            continue
        try:
            _set_limit(getattr(resource, name), max_memory_bytes)
        except (OSError, ValueError):
            continue
        return
    raise RuntimeError("L2 memory limit unavailable")


def _require_aggregate_scratch_limit_support(
    policy: RepositoryL2IsolationPolicy,
) -> None:
    del policy
    raise RepositoryL2UnavailableError(
        "the approved L2 backend cannot enforce the aggregate scratch bound"
    )


def _prepare_private_data_root(path: Path) -> Path:
    candidate = path.expanduser().absolute()
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
        if resolved_parent != candidate.parent:
            raise RepositoryL2UnavailableError(
                "L2 runtime data path failed its private external boundary"
            )
        if candidate.exists():
            metadata = candidate.lstat()
        else:
            candidate.mkdir(mode=0o700, exist_ok=False)
            metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        metadata = resolved.lstat()
    except OSError as exc:
        raise RepositoryL2UnavailableError("L2 runtime data path could not be prepared") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or resolved != candidate
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        or _is_within(resolved, REPOSITORY_ROOT.resolve(strict=True))
    ):
        raise RepositoryL2UnavailableError(
            "L2 runtime data path failed its private external boundary"
        )
    return resolved


def _ensure_private_directory(path: Path) -> None:
    try:
        if path.parent.resolve(strict=True) != path.parent:
            raise RepositoryL2UnavailableError("L2 private runtime directory failed validation")
        if path.exists():
            metadata = path.lstat()
        else:
            path.mkdir(mode=0o700, exist_ok=False)
            metadata = path.lstat()
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
    except OSError as exc:
        raise RepositoryL2UnavailableError(
            "L2 private runtime directory could not be prepared"
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or resolved != path
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise RepositoryL2UnavailableError("L2 private runtime directory failed validation")


def _create_synthetic_fixture(run_directory: Path) -> _SyntheticPaths:
    try:
        source = run_directory / "source"
        scratch = run_directory / "scratch"
        protected = run_directory / "protected"
        for directory in (source, scratch, protected):
            directory.mkdir(mode=0o700)
        paths = _SyntheticPaths(
            root=run_directory,
            source=source,
            scratch=scratch,
            protected=protected,
            outside_write=run_directory / "outside-write.txt",
            protected_file=protected / "founderos-private.env",
            probe_source=source / "hostile_probe.c",
            probe_binary=source / "hostile_probe",
        )
        (source / "input.txt").write_text("synthetic-l2-input\n", encoding="utf-8")
        paths.protected_file.write_text(
            "FOUNDEROS_SYNTHETIC_SECRET_MARKER\n",
            encoding="utf-8",
        )
        paths.probe_source.write_text(_HOSTILE_PROBE_SOURCE, encoding="utf-8")
        for path in (
            source / "input.txt",
            paths.protected_file,
            paths.probe_source,
        ):
            path.chmod(0o400)
        protected.chmod(0o500)
    except OSError as exc:
        raise RepositoryL2UnavailableError(
            "the synthetic L2 fixture could not be prepared"
        ) from exc
    return paths


def _compile_probe(paths: _SyntheticPaths, *, policy: RepositoryL2IsolationPolicy) -> None:
    result = _run_bounded_process(
        [
            str(_CLANG),
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(paths.probe_source),
            "-o",
            str(paths.probe_binary),
        ],
        cwd=paths.source,
        environment={"HOME": str(paths.scratch), "LANG": "C", "PATH": "/usr/bin:/bin"},
        policy=policy,
        apply_limits=False,
    )
    if result.return_code != 0 or result.timed_out or result.output_limited:
        raise RepositoryL2UnavailableError("the trusted L2 probe could not be built")
    try:
        metadata = paths.probe_binary.lstat()
        paths.probe_binary.chmod(0o500)
        paths.probe_source.chmod(0o400)
        paths.source.chmod(0o500)
    except OSError as exc:
        raise RepositoryL2UnavailableError("the trusted L2 probe could not be restricted") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RepositoryL2UnavailableError("the trusted L2 probe is invalid")


def _sandbox_profile(paths: _SyntheticPaths) -> str:
    source = _sandbox_quote(_canonical_macos_path(paths.source))
    scratch = _sandbox_quote(_canonical_macos_path(paths.scratch))
    probe = _sandbox_quote(_canonical_macos_path(paths.probe_binary))
    return (
        "(version 1)\n"
        "(deny default)\n"
        "(deny network*)\n"
        f'(allow process-exec (literal "{probe}"))\n'
        "(allow process-fork)\n"
        "(allow file-read* "
        '(literal "/") '
        '(subpath "/System") '
        '(subpath "/usr/lib") '
        f'(subpath "{source}"))\n'
        f'(allow file-write* (subpath "{scratch}"))\n'
    )


def _sandbox_quote(value: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise RepositoryL2UnavailableError("L2 sandbox path is invalid")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _canonical_macos_path(path: Path) -> str:
    text = str(path.resolve(strict=True))
    if text == "/tmp" or text.startswith("/tmp/"):
        return "/private" + text
    if text == "/var" or text.startswith("/var/"):
        return "/private" + text
    return text


def _open_synthetic_network_listener() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
    except OSError as exc:
        listener.close()
        raise RepositoryL2UnavailableError(
            "the synthetic L2 network probe could not be prepared"
        ) from exc
    return listener


def _open_synthetic_unix_listeners(
    *,
    run_id: str,
) -> tuple[tuple[socket.socket, socket.socket], Path, Path, Path]:
    try:
        root = Path(
            tempfile.mkdtemp(
                prefix=f"founderos-ri-l2-{run_id[:24]}-",
                dir="/private/tmp",
            )
        ).resolve(strict=True)
        root.chmod(0o700)
        metadata = root.lstat()
    except OSError as exc:
        raise RepositoryL2UnavailableError(
            "the synthetic L2 socket probe could not be prepared"
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        or root.parent != Path("/private/tmp")
    ):
        raise RepositoryL2UnavailableError("the synthetic L2 socket probe could not be prepared")
    database_path = root / "database.sock"
    docker_path = root / "docker.sock"
    listeners: list[socket.socket] = []
    try:
        for path in (database_path, docker_path):
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(path))
            listener.listen(1)
            path.chmod(0o600)
            listeners.append(listener)
        root.chmod(0o500)
    except OSError as exc:
        for listener in listeners:
            listener.close()
        _remove_socket_probe_directory(root)
        raise RepositoryL2UnavailableError(
            "the synthetic L2 socket probe could not be prepared"
        ) from exc
    return (listeners[0], listeners[1]), database_path, docker_path, root


def _minimal_environment(
    paths: _SyntheticPaths,
    *,
    network_port: int,
    database_socket_path: Path,
    docker_socket_path: Path,
) -> dict[str, str]:
    if not 1 <= network_port <= 65_535:
        raise RepositoryL2UnavailableError("the synthetic L2 network probe is invalid")
    return {
        "HOME": str(paths.scratch),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TMPDIR": str(paths.scratch),
        "RI_SOURCE": str(paths.source),
        "RI_SCRATCH": str(paths.scratch),
        "RI_PROTECTED_FILE": str(paths.protected_file),
        "RI_PROTECTED_SOCKET": str(database_socket_path),
        "RI_DOCKER_SOCKET": str(docker_socket_path),
        "RI_OUTSIDE_WRITE": str(paths.outside_write),
        "RI_FOUNDATION_ROOT": str(REPOSITORY_ROOT),
        "RI_NETWORK_PORT": str(network_port),
    }


def _run_synthetic_check(
    check: RepositoryL2Check,
    *,
    profile: str,
    paths: _SyntheticPaths,
    policy: RepositoryL2IsolationPolicy,
    environment: dict[str, str],
) -> _ProcessResult:
    check_environment = dict(environment)
    if check == RepositoryL2Check.OUTPUT:
        check_environment["RI_OUTPUT_BYTES"] = str(policy.max_output_bytes * 4)
    return _run_bounded_process(
        [
            str(_SANDBOX_EXEC),
            "-p",
            profile,
            str(paths.probe_binary),
            check.value,
        ],
        cwd=paths.source,
        environment=check_environment,
        policy=policy,
        apply_limits=True,
    )


def _run_bounded_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    policy: RepositoryL2IsolationPolicy,
    apply_limits: bool,
) -> _ProcessResult:
    deadline = time.monotonic() + policy.wall_time_seconds
    process: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    stdout = bytearray()
    stderr = bytearray()
    stdout_bytes = 0
    stderr_bytes = 0
    output_limited = False
    timed_out = False
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
            preexec_fn=(lambda: _apply_resource_limits(policy)) if apply_limits else None,
        )
        if process.stdout is None or process.stderr is None:
            raise RepositoryL2UnavailableError("L2 check streams are unavailable")
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            events = selector.select(timeout=min(remaining, 0.05))
            if not events:
                continue
            for key, _mask in events:
                descriptor = key.fileobj if isinstance(key.fileobj, int) else key.fileobj.fileno()
                chunk = os.read(descriptor, _READ_CHUNK_BYTES)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    stdout_bytes += len(chunk)
                    target = stdout
                else:
                    stderr_bytes += len(chunk)
                    target = stderr
                available = max(0, policy.max_output_bytes - len(stdout) - len(stderr))
                if available:
                    target.extend(chunk[:available])
                if stdout_bytes + stderr_bytes > policy.max_output_bytes:
                    output_limited = True
                    break
            if output_limited:
                break
        if timed_out or output_limited:
            _terminate_owned_child(process)
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_owned_child(process)
        return_code = process.returncode
        signal_number = -return_code if return_code is not None and return_code < 0 else None
        return _ProcessResult(
            return_code=return_code,
            signal_number=signal_number,
            stdout=bytes(stdout),
            stderr=bytes(stderr),
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            stdout_truncated=stdout_bytes > len(stdout),
            stderr_truncated=stderr_bytes > len(stderr),
            timed_out=timed_out,
            output_limited=output_limited,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RepositoryL2UnavailableError(
            "the isolated L2 synthetic check could not start"
        ) from exc
    finally:
        selector.close()
        if process is not None and process.poll() is None:
            _terminate_owned_child(process)
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


def _apply_resource_limits(policy: RepositoryL2IsolationPolicy) -> None:
    _set_limit(resource.RLIMIT_CPU, policy.cpu_seconds)
    _set_limit(resource.RLIMIT_FSIZE, policy.max_file_bytes)
    _set_limit(resource.RLIMIT_NOFILE, policy.max_open_files)
    if hasattr(resource, "RLIMIT_NPROC"):
        _set_limit(resource.RLIMIT_NPROC, policy.max_processes)
    _apply_memory_limit(policy.max_memory_bytes)


def _set_limit(limit: int, value: int) -> None:
    current_soft, current_hard = resource.getrlimit(limit)
    unbounded = {resource.RLIM_INFINITY, (1 << 63) - 1}
    hard = value if current_hard in unbounded else min(value, current_hard)
    resource.setrlimit(limit, (min(value, hard), hard))


def _terminate_owned_child(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (PermissionError, ProcessLookupError):
        if process.poll() is not None:
            return
        process.terminate()
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (PermissionError, ProcessLookupError):
            if process.poll() is None:
                process.kill()
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)


def _assess_synthetic_check(
    check: RepositoryL2Check,
    *,
    result: _ProcessResult,
    paths: _SyntheticPaths,
    policy: RepositoryL2IsolationPolicy,
) -> RepositoryL2CheckReceiptV1:
    stdout_text = result.stdout.decode("utf-8", errors="replace")
    stderr_text = result.stderr.decode("utf-8", errors="replace")
    combined = stdout_text + stderr_text
    forbidden = (
        "FOUNDEROS_SYNTHETIC_SECRET_MARKER",
        "FOUNDEROS_SYNTHETIC_SOCKET_MARKER",
        str(REPOSITORY_ROOT),
        str(paths.protected),
    )
    if any(marker in combined for marker in forbidden):
        raise RepositoryL2ExecutionError("L2 synthetic check exposed protected data")
    if paths.outside_write.exists() or (paths.source / "blocked-write.txt").exists():
        raise RepositoryL2ExecutionError("L2 synthetic check escaped its write boundary")

    payload = (
        _parse_probe_payload(stdout_text)
        if stdout_text.strip() and not result.output_limited
        else {}
    )
    status: Literal["passed", "contained"]
    outcome: RepositoryL2Outcome
    if check == RepositoryL2Check.BASELINE:
        _require_success(result, check)
        if (
            payload
            != {
                "artifact": "created",
                "source": "synthetic-l2-input",
                "uid": os.geteuid(),
            }
            or not (paths.scratch / "artifact.txt").is_file()
        ):
            raise RepositoryL2ExecutionError("L2 baseline proof was incomplete")
        status, outcome = "passed", "isolated synthetic baseline passed"
    elif check == RepositoryL2Check.ESCAPE:
        _require_success(result, check)
        blocked = (
            "docker_socket",
            "founderos_root",
            "network",
            "protected_file",
            "protected_socket",
            "write_outside",
            "write_source",
        )
        expected_keys = {"read_source", *blocked}
        if (
            set(payload) != expected_keys
            or payload.get("read_source") != "synthetic-l2-input"
            or any(payload.get(name) != "blocked" for name in blocked)
        ):
            raise RepositoryL2ExecutionError("L2 escape proof was incomplete")
        status, outcome = "passed", "filesystem socket and network escapes blocked"
    elif check == RepositoryL2Check.OUTPUT:
        if not result.output_limited:
            raise RepositoryL2ExecutionError("L2 output bound was not enforced")
        status, outcome = "contained", "combined output limit contained"
    elif check == RepositoryL2Check.TIMEOUT:
        if not result.timed_out:
            raise RepositoryL2ExecutionError("L2 wall-time bound was not enforced")
        status, outcome = "contained", "wall-time limit contained"
    elif check == RepositoryL2Check.CPU:
        if result.timed_out or result.signal_number not in {
            signal.SIGKILL,
            signal.SIGXCPU,
        }:
            raise RepositoryL2ExecutionError("L2 CPU bound was not enforced")
        status, outcome = "contained", "CPU exhaustion contained"
    elif check == RepositoryL2Check.FILE_SIZE:
        if result.timed_out or result.output_limited:
            raise RepositoryL2ExecutionError("L2 file-size proof failed")
        if payload and set(payload) != {"write_large"}:
            raise RepositoryL2ExecutionError("L2 file-size proof was malformed")
        file_limited = (
            payload.get("write_large") == "blocked" or result.signal_number == signal.SIGXFSZ
        )
        if not file_limited or _scratch_size(paths.scratch) > policy.max_scratch_bytes:
            raise RepositoryL2ExecutionError("L2 file or scratch bound was not enforced")
        status, outcome = "contained", "file and scratch limits contained"
    elif check == RepositoryL2Check.FORK:
        _require_success(result, check)
        spawned = payload.get("spawned")
        if (
            set(payload) != {"spawned"}
            or type(spawned) is not int
            or spawned < 0
            or spawned >= policy.max_processes
        ):
            raise RepositoryL2ExecutionError("L2 process bound was not enforced")
        status, outcome = "contained", "process limit contained"
    elif check == RepositoryL2Check.MEMORY:
        if result.timed_out or result.output_limited:
            raise RepositoryL2ExecutionError("L2 memory proof failed")
        allocated_mib = payload.get("allocated_mib")
        if (
            set(payload) == {"allocated_mib", "memory"}
            and payload.get("memory") == "blocked"
            and type(allocated_mib) is int
            and 0 <= allocated_mib < 1024
        ):
            status, outcome = "contained", "memory limit contained"
        else:
            raise RepositoryL2ExecutionError("L2 memory bound was not enforced")
    else:  # pragma: no cover
        raise RepositoryL2ExecutionError("unknown L2 synthetic check")

    return RepositoryL2CheckReceiptV1(
        check=check,
        status=status,
        outcome=outcome,
        exit_code=(
            result.return_code
            if result.return_code is not None and result.return_code >= 0
            else None
        ),
        signal=result.signal_number,
        stdout_bytes=result.stdout_bytes,
        stderr_bytes=result.stderr_bytes,
        stdout_truncated=result.stdout_truncated,
        stderr_truncated=result.stderr_truncated,
    )


def _require_success(result: _ProcessResult, check: RepositoryL2Check) -> None:
    if result.timed_out or result.output_limited or result.return_code != 0:
        raise RepositoryL2ExecutionError(f"L2 synthetic {check.value} proof failed")


def _parse_probe_payload(stdout_text: str) -> dict[str, object]:
    stripped = stdout_text.strip()
    if not stripped or len(stripped.encode("utf-8")) > 4096:
        raise RepositoryL2ExecutionError("L2 synthetic proof output was invalid")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise RepositoryL2ExecutionError("L2 synthetic proof output was invalid") from exc
    if not isinstance(payload, dict):
        raise RepositoryL2ExecutionError("L2 synthetic proof output was invalid")
    return payload


def _scratch_size(path: Path) -> int:
    total = 0
    for root, dir_names, file_names in os.walk(path, followlinks=False):
        root_path = Path(root)
        for name in (*dir_names, *file_names):
            candidate = root_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise RepositoryL2ExecutionError("L2 scratch contains a symbolic link")
            if stat.S_ISREG(metadata.st_mode):
                total += metadata.st_size
    return total


def _remove_run_directory(run_directory: Path, *, runs_root: Path) -> None:
    try:
        resolved_root = runs_root.resolve(strict=True)
        metadata = run_directory.lstat()
        resolved_run = run_directory.resolve(strict=True)
    except OSError as exc:
        raise RepositoryL2UnavailableError("L2 cleanup boundary could not be verified") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or resolved_run.parent != resolved_root
        or _RUN_ID_RE.fullmatch(resolved_run.name) is None
    ):
        raise RepositoryL2UnavailableError("L2 cleanup refused an unsafe path")
    try:
        for root, dir_names, file_names in os.walk(resolved_run, topdown=False):
            root_path = Path(root)
            for name in file_names:
                path = root_path / name
                if path.is_symlink():
                    path.unlink()
                else:
                    path.chmod(0o600)
            for name in dir_names:
                path = root_path / name
                if path.is_symlink():
                    path.unlink()
                else:
                    path.chmod(0o700)
            root_path.chmod(0o700)
        shutil.rmtree(resolved_run)
    except OSError as exc:
        raise RepositoryL2UnavailableError(
            "L2 synthetic run directory could not be removed"
        ) from exc


def _remove_socket_probe_directory(root: Path) -> None:
    try:
        metadata = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise RepositoryL2UnavailableError(
            "L2 socket probe cleanup boundary could not be verified"
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or resolved != root
        or resolved.parent != Path("/private/tmp")
        or not resolved.name.startswith("founderos-ri-l2-")
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise RepositoryL2UnavailableError("L2 socket probe cleanup refused an unsafe path")
    try:
        root.chmod(0o700)
        for child in root.iterdir():
            child.unlink()
        root.rmdir()
    except OSError as exc:
        raise RepositoryL2UnavailableError(
            "L2 socket probe directory could not be removed"
        ) from exc


def _is_within(path: Path, boundary: Path) -> bool:
    try:
        path.relative_to(boundary)
    except ValueError:
        return False
    return True


_HOSTILE_PROBE_SOURCE = r"""#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <sys/un.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static const char *env_required(const char *name) {
    const char *value = getenv(name);
    if (value == NULL) exit(64);
    return value;
}

static int blocked_read(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd >= 0) { close(fd); return 0; }
    return errno == EPERM || errno == EACCES;
}

static int blocked_write(const char *path) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd >= 0) { close(fd); return 0; }
    return errno == EPERM || errno == EACCES || errno == EFBIG;
}

static void json_state(const char *name, int blocked) {
    printf("\"%s\":\"%s\"", name, blocked ? "blocked" : "allowed");
}

int main(int argc, char **argv) {
    if (argc != 2) return 64;
    const char *mode = argv[1];
    const char *source = env_required("RI_SOURCE");
    const char *scratch = env_required("RI_SCRATCH");
    char path[4096];

    if (strcmp(mode, "baseline") == 0) {
        snprintf(path, sizeof(path), "%s/input.txt", source);
        FILE *input = fopen(path, "r");
        char value[64] = {0};
        if (input == NULL || fgets(value, sizeof(value), input) == NULL) return 70;
        fclose(input);
        value[strcspn(value, "\r\n")] = 0;
        snprintf(path, sizeof(path), "%s/artifact.txt", scratch);
        FILE *artifact = fopen(path, "w");
        if (artifact == NULL) return 71;
        fputs("synthetic-artifact\n", artifact);
        fclose(artifact);
        printf("{\"artifact\":\"created\",\"source\":\"%s\",\"uid\":%d}\n", value, geteuid());
        return 0;
    }

    if (strcmp(mode, "escape") == 0) {
        snprintf(path, sizeof(path), "%s/input.txt", source);
        FILE *input = fopen(path, "r");
        char value[64] = {0};
        if (input == NULL || fgets(value, sizeof(value), input) == NULL) return 72;
        fclose(input);
        value[strcspn(value, "\r\n")] = 0;
        printf("{\"read_source\":\"%s\",", value);
        snprintf(path, sizeof(path), "%s/blocked-write.txt", source);
        json_state("write_source", blocked_write(path)); printf(",");
        json_state("protected_file", blocked_read(env_required("RI_PROTECTED_FILE"))); printf(",");
        int socket_fd = socket(AF_UNIX, SOCK_STREAM, 0);
        int socket_blocked = socket_fd < 0 && (errno == EPERM || errno == EACCES);
        if (socket_fd >= 0) {
            struct sockaddr_un socket_address;
            memset(&socket_address, 0, sizeof(socket_address));
            socket_address.sun_family = AF_UNIX;
            const char *socket_path = env_required("RI_PROTECTED_SOCKET");
            if (strlen(socket_path) >= sizeof(socket_address.sun_path)) return 73;
            strcpy(socket_address.sun_path, socket_path);
            int connected = connect(
                socket_fd,
                (struct sockaddr *)&socket_address,
                sizeof(socket_address)
            );
            socket_blocked = connected < 0 && (errno == EPERM || errno == EACCES);
            close(socket_fd);
        }
        json_state("protected_socket", socket_blocked); printf(",");
        socket_fd = socket(AF_UNIX, SOCK_STREAM, 0);
        socket_blocked = socket_fd < 0 && (errno == EPERM || errno == EACCES);
        if (socket_fd >= 0) {
            struct sockaddr_un socket_address;
            memset(&socket_address, 0, sizeof(socket_address));
            socket_address.sun_family = AF_UNIX;
            const char *socket_path = env_required("RI_DOCKER_SOCKET");
            if (strlen(socket_path) >= sizeof(socket_address.sun_path)) return 74;
            strcpy(socket_address.sun_path, socket_path);
            int connected = connect(
                socket_fd,
                (struct sockaddr *)&socket_address,
                sizeof(socket_address)
            );
            socket_blocked = connected < 0 && (errno == EPERM || errno == EACCES);
            close(socket_fd);
        }
        json_state("docker_socket", socket_blocked); printf(",");
        json_state("write_outside", blocked_write(env_required("RI_OUTSIDE_WRITE"))); printf(",");
        json_state("founderos_root", blocked_read(env_required("RI_FOUNDATION_ROOT"))); printf(",");
        int fd = socket(AF_INET, SOCK_STREAM, 0);
        int network_blocked = fd < 0 && (errno == EPERM || errno == EACCES);
        if (fd >= 0) {
            struct sockaddr_in address;
            memset(&address, 0, sizeof(address));
            address.sin_family = AF_INET;
            address.sin_port = htons((unsigned short)atoi(env_required("RI_NETWORK_PORT")));
            address.sin_addr.s_addr = htonl(0x7f000001);
            int connected = connect(fd, (struct sockaddr *)&address, sizeof(address));
            network_blocked = connected < 0 && (errno == EPERM || errno == EACCES);
            close(fd);
        }
        json_state("network", network_blocked); printf("}\n");
        return 0;
    }

    if (strcmp(mode, "output") == 0) {
        long amount = strtol(env_required("RI_OUTPUT_BYTES"), NULL, 10);
        for (long index = 0; index < amount; index++) fputc('o', stdout);
        fflush(stdout);
        for (long index = 0; index < amount; index++) fputc('e', stderr);
        fflush(stderr);
        return 0;
    }

    if (strcmp(mode, "timeout") == 0) {
        for (;;) usleep(50000);
    }

    if (strcmp(mode, "cpu") == 0) {
        volatile unsigned long value = 0;
        for (;;) value++;
    }

    if (strcmp(mode, "file-size") == 0) {
        snprintf(path, sizeof(path), "%s/large.bin", scratch);
        int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
        int blocked = 0;
        if (fd < 0) blocked = 1;
        else {
            char bytes[4096] = {0};
            for (int index = 0; index < 1024; index++) {
                if (write(fd, bytes, sizeof(bytes)) < 0) { blocked = 1; break; }
            }
            close(fd);
        }
        printf("{\"write_large\":\"%s\"}\n", blocked ? "blocked" : "allowed");
        return 0;
    }

    if (strcmp(mode, "fork") == 0) {
        pid_t children[64];
        int spawned = 0;
        for (int index = 0; index < 64; index++) {
            pid_t child = fork();
            if (child < 0) break;
            if (child == 0) { sleep(5); _exit(0); }
            children[spawned++] = child;
        }
        for (int index = 0; index < spawned; index++) kill(children[index], SIGTERM);
        for (int index = 0; index < spawned; index++) waitpid(children[index], NULL, 0);
        printf("{\"spawned\":%d}\n", spawned);
        return 0;
    }

    if (strcmp(mode, "memory") == 0) {
        size_t block = 1024 * 1024;
        int allocated = 0;
        void *items[1024];
        while (allocated < 1024) {
            items[allocated] = malloc(block);
            if (items[allocated] == NULL) break;
            memset(items[allocated], 0x5a, block);
            allocated++;
            usleep(5000);
        }
        for (int index = 0; index < allocated; index++) free(items[index]);
        printf("{\"allocated_mib\":%d,\"memory\":\"%s\"}\n", allocated, allocated < 1024 ? "blocked" : "allowed");
        return 0;
    }

    return 64;
}
"""
