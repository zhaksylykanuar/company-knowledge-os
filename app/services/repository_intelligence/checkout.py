"""Synthetic-safe exact-SHA checkout materialization for Repository Intelligence.

Only trusted ``git`` object-reading commands are used. Target repository files
are never executed, no network operation exists, ambient credentials are not
forwarded, and every run directory is removed on every exit.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import signal
import stat
import subprocess
import time
import unicodedata
from typing import Any, BinaryIO

from app.core.config import settings


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_FILE_MODES = frozenset({"100644", "100755"})
_GIT_OBJECT_TYPE_BLOB = "blob"
_READ_CHUNK_BYTES = 64 * 1024
_STDERR_LIMIT_BYTES = 64 * 1024
_COMMAND_TERMINATE_SECONDS = 1.0
_LOCAL_GIT_CONFIG_MAX_BYTES = 64 * 1024


class RepositoryCheckoutError(RuntimeError):
    """Sanitized Repository Intelligence checkout failure."""


class RepositoryCheckoutPathError(RepositoryCheckoutError):
    """A configured source or runtime path crosses a safety boundary."""


class RepositoryCheckoutSHAError(RepositoryCheckoutError):
    """The requested exact commit SHA is unavailable or invalid."""


class RepositoryCheckoutLimitError(RepositoryCheckoutError):
    """The checkout exceeds a configured file, byte, path, or output bound."""


class RepositoryCheckoutTimeoutError(RepositoryCheckoutError):
    """The checkout did not complete inside its total wall-time budget."""


class RepositoryCheckoutCommandError(RepositoryCheckoutError):
    """A trusted git object-reading command failed."""


class RepositoryCheckoutCleanupError(RepositoryCheckoutError):
    """A run directory could not be removed safely."""


@dataclass(frozen=True)
class RepositoryCheckoutPolicy:
    data_path: Path
    timeout_seconds: float
    max_files: int
    max_bytes: int
    max_file_bytes: int
    max_command_output_bytes: int
    max_path_bytes: int
    max_depth: int

    @classmethod
    def from_settings(cls, config: Any = settings) -> RepositoryCheckoutPolicy:
        return cls(
            data_path=Path(str(config.repository_intelligence_data_path)),
            timeout_seconds=float(
                config.repository_intelligence_checkout_timeout_seconds
            ),
            max_files=int(config.repository_intelligence_checkout_max_files),
            max_bytes=int(config.repository_intelligence_checkout_max_bytes),
            max_file_bytes=int(
                config.repository_intelligence_checkout_max_file_bytes
            ),
            max_command_output_bytes=int(
                config.repository_intelligence_checkout_max_command_output_bytes
            ),
            max_path_bytes=int(
                config.repository_intelligence_checkout_max_path_bytes
            ),
            max_depth=int(config.repository_intelligence_checkout_max_depth),
        )

    def validate(self) -> None:
        if self.timeout_seconds <= 0:
            raise RepositoryCheckoutLimitError("checkout timeout must be positive")
        integer_bounds = (
            self.max_files,
            self.max_bytes,
            self.max_file_bytes,
            self.max_command_output_bytes,
            self.max_path_bytes,
            self.max_depth,
        )
        if any(value <= 0 for value in integer_bounds):
            raise RepositoryCheckoutLimitError(
                "checkout resource bounds must be positive"
            )
        if self.max_file_bytes > self.max_bytes:
            raise RepositoryCheckoutLimitError(
                "checkout file bound cannot exceed total byte bound"
            )


@dataclass(frozen=True)
class RepositoryCheckoutRequest:
    source_repository: Path
    commit_sha: str
    run_id: str


@dataclass(frozen=True)
class MaterializedRepositoryCheckout:
    path: Path
    commit_sha: str
    file_count: int
    total_bytes: int
    network_used: bool = False
    target_code_executed: bool = False
    files_read_only: bool = True


@dataclass(frozen=True)
class _TreeEntry:
    path: str
    object_id: str
    size: int


@contextmanager
def materialize_repository_checkout(
    request: RepositoryCheckoutRequest,
    *,
    policy: RepositoryCheckoutPolicy | None = None,
    repository_root: Path = REPOSITORY_ROOT,
) -> Iterator[MaterializedRepositoryCheckout]:
    """Materialize one exact commit into an external ephemeral directory."""

    selected_policy = policy or RepositoryCheckoutPolicy.from_settings()
    selected_policy.validate()
    deadline = time.monotonic() + selected_policy.timeout_seconds
    commit_sha = _validated_commit_sha(request.commit_sha)
    run_id = _validated_run_id(request.run_id)
    source = _validated_source_repository(
        request.source_repository,
        repository_root=repository_root,
        policy=selected_policy,
        deadline=deadline,
    )
    data_root = _validated_data_root(
        selected_policy.data_path,
        repository_root=repository_root,
        source_repository=source,
    )
    worktrees_root = data_root / "repository-intelligence" / "worktrees"
    _ensure_private_directory(worktrees_root)
    source_resolved = source.resolve(strict=True)
    worktrees_resolved = worktrees_root.resolve(strict=True)
    if _is_within(source_resolved, worktrees_resolved) or _is_within(
        worktrees_resolved,
        source_resolved,
    ):
        raise RepositoryCheckoutPathError(
            "checkout source and runtime worktree boundaries cannot overlap"
        )

    run_directory = worktrees_root / run_id
    created_run = False
    try:
        run_directory.mkdir(mode=0o700, exist_ok=False)
        created_run = True
        run_directory.chmod(0o700)
        checkout_path = run_directory / "checkout"
        checkout_path.mkdir(mode=0o700)
        environment = _safe_git_environment(run_directory)
        git_executable = _git_executable()
        _validate_git_repository_boundary(
            git_executable=git_executable,
            source=source,
            environment=environment,
            deadline=deadline,
        )

        resolved_sha = _resolve_exact_commit(
            git_executable=git_executable,
            source=source,
            commit_sha=commit_sha,
            environment=environment,
            deadline=deadline,
        )
        tree_output = _run_git_bounded(
            git_executable=git_executable,
            arguments=(
                "ls-tree",
                "-r",
                "-z",
                "--long",
                "--full-tree",
                resolved_sha,
            ),
            cwd=source,
            environment=environment,
            deadline=deadline,
            stdout_limit=selected_policy.max_command_output_bytes,
        )
        entries = _parse_tree_entries(tree_output, policy=selected_policy)
        _materialize_entries(
            git_executable=git_executable,
            source=source,
            checkout_path=checkout_path,
            entries=entries,
            environment=environment,
            deadline=deadline,
        )
        _freeze_checkout(checkout_path)
        materialized = MaterializedRepositoryCheckout(
            path=checkout_path,
            commit_sha=resolved_sha,
            file_count=len(entries),
            total_bytes=sum(entry.size for entry in entries),
        )
        yield materialized
    except FileExistsError as exc:
        raise RepositoryCheckoutPathError(
            "checkout run directory already exists"
        ) from exc
    finally:
        if created_run:
            _remove_run_directory(
                run_directory,
                worktrees_root=worktrees_root,
            )


def _validated_commit_sha(value: str) -> str:
    if not isinstance(value, str) or _SHA1_RE.fullmatch(value) is None:
        raise RepositoryCheckoutSHAError(
            "checkout requires one full lowercase SHA-1 commit"
        )
    return value


def _validated_run_id(value: str) -> str:
    if not isinstance(value, str) or _RUN_ID_RE.fullmatch(value) is None:
        raise RepositoryCheckoutPathError("checkout run id is invalid")
    return value


def _validated_source_repository(
    path: Path,
    *,
    repository_root: Path,
    policy: RepositoryCheckoutPolicy,
    deadline: float,
) -> Path:
    _require_time_remaining(deadline)
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise RepositoryCheckoutPathError(
            "checkout source cannot be a symbolic link"
        )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise RepositoryCheckoutPathError(
            "checkout source repository is unavailable"
        ) from exc
    if not resolved.is_dir():
        raise RepositoryCheckoutPathError(
            "checkout source repository must be a directory"
        )
    _validate_local_git_layout(
        resolved,
        policy=policy,
        deadline=deadline,
    )
    root = repository_root.resolve(strict=True)
    if _is_within(resolved, root):
        raise RepositoryCheckoutPathError(
            "checkout source must stay outside the FounderOS repository"
        )
    return resolved


def _validate_local_git_layout(
    source: Path,
    *,
    policy: RepositoryCheckoutPolicy,
    deadline: float,
) -> None:
    _require_time_remaining(deadline)
    git_directory = source / ".git"
    try:
        git_metadata = git_directory.lstat()
    except OSError as exc:
        raise RepositoryCheckoutPathError(
            "checkout source must be a standalone non-bare git repository"
        ) from exc
    if stat.S_ISLNK(git_metadata.st_mode) or not stat.S_ISDIR(
        git_metadata.st_mode
    ):
        raise RepositoryCheckoutPathError(
            "checkout source must be a standalone non-bare git repository"
        )

    config_path = git_directory / "config"
    try:
        config_metadata = config_path.lstat()
        if (
            stat.S_ISLNK(config_metadata.st_mode)
            or not stat.S_ISREG(config_metadata.st_mode)
            or config_metadata.st_size > _LOCAL_GIT_CONFIG_MAX_BYTES
        ):
            raise RepositoryCheckoutPathError(
                "checkout source git configuration is unsafe"
            )
        config_text = config_path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise RepositoryCheckoutPathError(
            "checkout source git configuration is unsafe"
        ) from exc
    except OSError as exc:
        raise RepositoryCheckoutPathError(
            "checkout source git configuration is unavailable"
        ) from exc
    for line in config_text.splitlines():
        normalized = line.strip().casefold().replace(" ", "")
        if normalized.startswith("[include"):
            raise RepositoryCheckoutPathError(
                "checkout source git configuration includes an external file"
            )

    metadata_entries = 0
    metadata_entry_limit = max(
        4096,
        min(1_000_000, policy.max_files * 64),
    )
    for root, dir_names, file_names in os.walk(git_directory, followlinks=False):
        _require_time_remaining(deadline)
        root_path = Path(root)
        for name in (*dir_names, *file_names):
            _require_time_remaining(deadline)
            metadata_entries += 1
            if metadata_entries > metadata_entry_limit:
                raise RepositoryCheckoutLimitError(
                    "checkout git metadata exceeds the bounded entry limit"
                )
            candidate = root_path / name
            try:
                candidate_mode = candidate.lstat().st_mode
                if stat.S_ISLNK(candidate_mode) or not (
                    stat.S_ISDIR(candidate_mode) or stat.S_ISREG(candidate_mode)
                ):
                    raise RepositoryCheckoutPathError(
                        "checkout git metadata contains an unsafe entry"
                    )
            except OSError as exc:
                raise RepositoryCheckoutPathError(
                    "checkout git metadata could not be inspected"
                ) from exc


def _validated_data_root(
    path: Path,
    *,
    repository_root: Path,
    source_repository: Path,
) -> Path:
    candidate = path.expanduser()
    if candidate.exists() and candidate.is_symlink():
        raise RepositoryCheckoutPathError(
            "checkout data path cannot be a symbolic link"
        )
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise RepositoryCheckoutPathError(
            "checkout data path could not be resolved"
        ) from exc
    if resolved == Path(resolved.anchor):
        raise RepositoryCheckoutPathError(
            "checkout data path cannot be a filesystem root"
        )
    root = repository_root.resolve(strict=True)
    if _is_within(resolved, root):
        raise RepositoryCheckoutPathError(
            "checkout data path must stay outside the FounderOS repository"
        )
    source = source_repository.resolve(strict=True)
    if _is_within(resolved, source) or _is_within(source, resolved):
        raise RepositoryCheckoutPathError(
            "checkout source and runtime data paths cannot overlap"
        )
    _ensure_private_directory(resolved)
    if resolved.is_symlink() or _is_within(resolved.resolve(strict=True), root):
        raise RepositoryCheckoutPathError(
            "checkout data path failed the external-path boundary"
        )
    return resolved


def _ensure_private_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)
        metadata = path.lstat()
    except OSError as exc:
        raise RepositoryCheckoutPathError(
            "checkout runtime directory could not be prepared"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RepositoryCheckoutPathError(
            "checkout runtime directory is not a private directory"
        )
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise RepositoryCheckoutPathError(
            "checkout runtime directory permissions are not private"
        )
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise RepositoryCheckoutPathError(
            "checkout runtime directory ownership is invalid"
        )


def _is_within(path: Path, boundary: Path) -> bool:
    try:
        path.relative_to(boundary)
    except ValueError:
        return False
    return True


def _git_executable() -> str:
    executable = shutil.which("git", path=os.defpath)
    if executable is None:
        raise RepositoryCheckoutCommandError("git is unavailable")
    return str(Path(executable).resolve(strict=True))


def _safe_git_environment(run_directory: Path) -> dict[str, str]:
    home = run_directory / "home"
    home.mkdir(mode=0o700)
    home.chmod(0o700)
    return {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_ALLOW_PROTOCOL": "",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_PROTOCOL_FROM_USER": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
    }


def _validate_git_repository_boundary(
    *,
    git_executable: str,
    source: Path,
    environment: dict[str, str],
    deadline: float,
) -> None:
    inside_worktree = _git_text(
        git_executable=git_executable,
        arguments=("rev-parse", "--is-inside-work-tree"),
        cwd=source,
        environment=environment,
        deadline=deadline,
        stdout_limit=16,
    )
    bare_repository = _git_text(
        git_executable=git_executable,
        arguments=("rev-parse", "--is-bare-repository"),
        cwd=source,
        environment=environment,
        deadline=deadline,
        stdout_limit=16,
    )
    if inside_worktree == "true":
        top_level = _git_path(
            git_executable=git_executable,
            arguments=("rev-parse", "--show-toplevel"),
            cwd=source,
            environment=environment,
            deadline=deadline,
        )
        if top_level != source:
            raise RepositoryCheckoutPathError(
                "checkout source must be the exact git repository root"
            )
    elif bare_repository != "true":
        raise RepositoryCheckoutPathError(
            "checkout source is not an exact git repository root"
        )

    git_directory = _git_path(
        git_executable=git_executable,
        arguments=("rev-parse", "--absolute-git-dir"),
        cwd=source,
        environment=environment,
        deadline=deadline,
    )
    common_directory = _git_path(
        git_executable=git_executable,
        arguments=("rev-parse", "--git-common-dir"),
        cwd=source,
        environment=environment,
        deadline=deadline,
    )
    for metadata_path in (git_directory, common_directory):
        if not _is_within(metadata_path, source):
            raise RepositoryCheckoutPathError(
                "checkout git metadata must stay inside the source boundary"
            )
    for relative in (
        Path("objects/info/alternates"),
        Path("objects/info/http-alternates"),
    ):
        candidate = common_directory / relative
        if candidate.exists() or candidate.is_symlink():
            raise RepositoryCheckoutPathError(
                "checkout source uses an external git object boundary"
            )


def _git_text(
    *,
    git_executable: str,
    arguments: Sequence[str],
    cwd: Path,
    environment: dict[str, str],
    deadline: float,
    stdout_limit: int,
) -> str:
    output = _run_git_bounded(
        git_executable=git_executable,
        arguments=arguments,
        cwd=cwd,
        environment=environment,
        deadline=deadline,
        stdout_limit=stdout_limit,
    )
    try:
        value = output.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RepositoryCheckoutCommandError(
            "trusted git metadata output was invalid"
        ) from exc
    if (
        not value
        or "\n" in value
        or "\r" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RepositoryCheckoutCommandError(
            "trusted git metadata output was invalid"
        )
    return value


def _git_path(
    *,
    git_executable: str,
    arguments: Sequence[str],
    cwd: Path,
    environment: dict[str, str],
    deadline: float,
) -> Path:
    value = _git_text(
        git_executable=git_executable,
        arguments=arguments,
        cwd=cwd,
        environment=environment,
        deadline=deadline,
        stdout_limit=4096,
    )
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise RepositoryCheckoutPathError(
            "checkout git metadata path is unavailable"
        ) from exc
    return resolved


def _resolve_exact_commit(
    *,
    git_executable: str,
    source: Path,
    commit_sha: str,
    environment: dict[str, str],
    deadline: float,
) -> str:
    try:
        output = _run_git_bounded(
            git_executable=git_executable,
            arguments=(
                "rev-parse",
                "--verify",
                f"{commit_sha}^{{commit}}",
            ),
            cwd=source,
            environment=environment,
            deadline=deadline,
            stdout_limit=128,
        )
    except RepositoryCheckoutCommandError as exc:
        raise RepositoryCheckoutSHAError(
            "checkout commit is unavailable in the source repository"
        ) from exc
    try:
        resolved = output.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise RepositoryCheckoutSHAError(
            "checkout commit identity is invalid"
        ) from exc
    if resolved != commit_sha:
        raise RepositoryCheckoutSHAError(
            "checkout commit did not resolve to the requested exact SHA"
        )
    return resolved


def _parse_tree_entries(
    output: bytes,
    *,
    policy: RepositoryCheckoutPolicy,
) -> list[_TreeEntry]:
    entries: list[_TreeEntry] = []
    file_paths: dict[str, str] = {}
    directory_paths: dict[str, str] = {}
    total_bytes = 0
    for raw_record in output.split(b"\0"):
        if not raw_record:
            continue
        header, separator, raw_path = raw_record.partition(b"\t")
        if not separator:
            raise RepositoryCheckoutCommandError(
                "git tree output failed strict validation"
            )
        fields = header.split()
        if len(fields) != 4:
            raise RepositoryCheckoutCommandError(
                "git tree output failed strict validation"
            )
        raw_mode, raw_type, raw_object_id, raw_size = fields
        try:
            mode = raw_mode.decode("ascii")
            object_type = raw_type.decode("ascii")
            object_id = raw_object_id.decode("ascii")
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RepositoryCheckoutCommandError(
                "git tree output failed strict validation"
            ) from exc
        if object_type != _GIT_OBJECT_TYPE_BLOB or mode not in _ALLOWED_FILE_MODES:
            raise RepositoryCheckoutPathError(
                "checkout tree contains an unsupported link or object type"
            )
        try:
            size = int(raw_size.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RepositoryCheckoutCommandError(
                "git tree output failed strict validation"
            ) from exc
        if _SHA1_RE.fullmatch(object_id) is None or size < 0:
            raise RepositoryCheckoutCommandError(
                "git tree output contains an invalid object"
            )
        normalized_path, key, prefixes = _validated_tree_path(
            path,
            policy=policy,
        )
        if key in file_paths or key in directory_paths:
            raise RepositoryCheckoutPathError(
                "checkout tree contains a portable path collision"
            )
        for prefix_key, original_prefix in prefixes:
            if prefix_key in file_paths:
                raise RepositoryCheckoutPathError(
                    "checkout tree contains a file-directory collision"
                )
            existing_prefix = directory_paths.get(prefix_key)
            if existing_prefix is not None and existing_prefix != original_prefix:
                raise RepositoryCheckoutPathError(
                    "checkout tree contains a portable directory collision"
                )
        file_paths[key] = normalized_path
        for prefix_key, original_prefix in prefixes:
            directory_paths.setdefault(prefix_key, original_prefix)
        if size > policy.max_file_bytes:
            raise RepositoryCheckoutLimitError(
                "checkout file exceeds the configured byte bound"
            )
        total_bytes += size
        if total_bytes > policy.max_bytes:
            raise RepositoryCheckoutLimitError(
                "checkout exceeds the configured total byte bound"
            )
        entries.append(
            _TreeEntry(
                path=normalized_path,
                object_id=object_id,
                size=size,
            )
        )
        if len(entries) > policy.max_files:
            raise RepositoryCheckoutLimitError(
                "checkout exceeds the configured file-count bound"
            )
    return entries


def _validated_tree_path(
    value: str,
    *,
    policy: RepositoryCheckoutPolicy,
) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RepositoryCheckoutPathError("checkout tree contains an unsafe path")
    if len(value.encode("utf-8")) > policy.max_path_bytes:
        raise RepositoryCheckoutLimitError(
            "checkout path exceeds the configured byte bound"
        )
    parsed = PurePosixPath(value)
    parts = parsed.parts
    if not parts or any(
        part in {"", ".", ".."} or part.casefold() == ".git" for part in parts
    ):
        raise RepositoryCheckoutPathError("checkout tree contains an unsafe path")
    if len(parts) > policy.max_depth:
        raise RepositoryCheckoutLimitError(
            "checkout path exceeds the configured depth bound"
        )
    normalized = "/".join(parts)
    normalized_parts = tuple(
        unicodedata.normalize("NFC", part).casefold() for part in parts
    )
    key = "/".join(normalized_parts)
    prefixes = tuple(
        (
            "/".join(normalized_parts[:index]),
            "/".join(parts[:index]),
        )
        for index in range(1, len(normalized_parts))
    )
    return normalized, key, prefixes


def _materialize_entries(
    *,
    git_executable: str,
    source: Path,
    checkout_path: Path,
    entries: Sequence[_TreeEntry],
    environment: dict[str, str],
    deadline: float,
) -> None:
    for entry in entries:
        destination = checkout_path.joinpath(*PurePosixPath(entry.path).parts)
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _run_git_bounded(
            git_executable=git_executable,
            arguments=(
                "cat-file",
                "blob",
                entry.object_id,
            ),
            cwd=source,
            environment=environment,
            deadline=deadline,
            stdout_limit=entry.size,
            stdout_path=destination,
        )
        try:
            actual_size = destination.stat().st_size
        except OSError as exc:
            raise RepositoryCheckoutCommandError(
                "checkout file could not be verified"
            ) from exc
        if actual_size != entry.size:
            raise RepositoryCheckoutCommandError(
                "checkout file size did not match the git object"
            )


def _run_git_bounded(
    *,
    git_executable: str,
    arguments: Sequence[str],
    cwd: Path,
    environment: dict[str, str],
    deadline: float,
    stdout_limit: int,
    stdout_path: Path | None = None,
) -> bytes:
    command = [
        git_executable,
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.file.allow=never",
        *arguments,
    ]
    return _run_bounded_process(
        command,
        cwd=cwd,
        environment=environment,
        deadline=deadline,
        stdout_limit=stdout_limit,
        stdout_path=stdout_path,
    )


def _require_time_remaining(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise RepositoryCheckoutTimeoutError(
            "checkout exceeded the configured timeout"
        )


def _run_bounded_process(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    deadline: float,
    stdout_limit: int,
    stdout_path: Path | None = None,
) -> bytes:
    _require_time_remaining(deadline)
    output_stream: BinaryIO | None = None
    process: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    stdout_buffer = bytearray()
    stdout_count = 0
    stderr_count = 0
    try:
        if stdout_path is not None:
            output_stream = stdout_path.open("xb")
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        if process.stdout is None or process.stderr is None:
            raise RepositoryCheckoutCommandError(
                "checkout command streams are unavailable"
            )
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RepositoryCheckoutTimeoutError(
                    "checkout exceeded the configured timeout"
                )
            events = selector.select(timeout=min(remaining, 0.1))
            if not events:
                continue
            for key, _mask in events:
                descriptor = (
                    key.fileobj
                    if isinstance(key.fileobj, int)
                    else key.fileobj.fileno()
                )
                chunk = os.read(descriptor, _READ_CHUNK_BYTES)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    stdout_count += len(chunk)
                    if stdout_count > stdout_limit:
                        raise RepositoryCheckoutLimitError(
                            "checkout command output exceeded its configured bound"
                        )
                    if output_stream is not None:
                        output_stream.write(chunk)
                    else:
                        stdout_buffer.extend(chunk)
                else:
                    stderr_count += len(chunk)
                    if stderr_count > _STDERR_LIMIT_BYTES:
                        raise RepositoryCheckoutLimitError(
                            "checkout command diagnostics exceeded their configured bound"
                        )
        remaining = max(0.01, deadline - time.monotonic())
        return_code = process.wait(timeout=remaining)
        if output_stream is not None:
            output_stream.flush()
            os.fsync(output_stream.fileno())
        if return_code != 0:
            raise RepositoryCheckoutCommandError(
                "trusted git object-reading command failed"
            )
        return bytes(stdout_buffer)
    except subprocess.TimeoutExpired as exc:
        raise RepositoryCheckoutTimeoutError(
            "checkout exceeded the configured timeout"
        ) from exc
    except OSError as exc:
        raise RepositoryCheckoutCommandError(
            "trusted git object-reading command could not start"
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
        if output_stream is not None:
            output_stream.close()


def _terminate_owned_child(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (PermissionError, ProcessLookupError):
        if process.poll() is not None:
            return
        process.terminate()
    try:
        process.wait(timeout=_COMMAND_TERMINATE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (PermissionError, ProcessLookupError):
            if process.poll() is None:
                process.kill()
        process.wait(timeout=_COMMAND_TERMINATE_SECONDS)


def _freeze_checkout(checkout_path: Path) -> None:
    files: list[Path] = []
    directories: list[Path] = []
    for root, dir_names, file_names in os.walk(checkout_path):
        root_path = Path(root)
        directories.append(root_path)
        for name in dir_names:
            directories.append(root_path / name)
        for name in file_names:
            files.append(root_path / name)
    try:
        for path in files:
            path.chmod(0o400)
        for path in sorted(set(directories), key=lambda item: len(item.parts), reverse=True):
            path.chmod(0o500)
    except OSError as exc:
        raise RepositoryCheckoutPathError(
            "checkout permissions could not be restricted"
        ) from exc


def _remove_run_directory(
    run_directory: Path,
    *,
    worktrees_root: Path,
) -> None:
    try:
        resolved_root = worktrees_root.resolve(strict=True)
        run_metadata = run_directory.lstat()
        resolved_run = run_directory.resolve(strict=True)
    except OSError as exc:
        raise RepositoryCheckoutCleanupError(
            "checkout cleanup boundary could not be verified"
        ) from exc
    if (
        stat.S_ISLNK(run_metadata.st_mode)
        or not stat.S_ISDIR(run_metadata.st_mode)
        or resolved_run != run_directory
        or resolved_run.parent != resolved_root
        or not _RUN_ID_RE.fullmatch(resolved_run.name)
    ):
        raise RepositoryCheckoutCleanupError(
            "checkout cleanup refused an unsafe path"
        )
    try:
        for root, dir_names, file_names in os.walk(resolved_run, topdown=False):
            root_path = Path(root)
            for name in file_names:
                _prepare_cleanup_entry(root_path / name, expect_directory=False)
            for name in dir_names:
                _prepare_cleanup_entry(root_path / name, expect_directory=True)
            root_path.chmod(0o700)
        shutil.rmtree(resolved_run)
    except OSError as exc:
        raise RepositoryCheckoutCleanupError(
            "checkout run directory could not be removed"
        ) from exc


def _prepare_cleanup_entry(path: Path, *, expect_directory: bool) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        path.unlink()
        return
    if expect_directory:
        if not stat.S_ISDIR(metadata.st_mode):
            path.unlink()
            return
        path.chmod(0o700)
        return
    if stat.S_ISDIR(metadata.st_mode):
        path.chmod(0o700)
        return
    path.chmod(0o600)
