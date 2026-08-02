from __future__ import annotations

import asyncio
from dataclasses import replace
import os
from pathlib import Path
import stat
import subprocess
import time
from uuid import uuid4

import pytest

import app.services.repository_intelligence.checkout as checkout_service
from app.core.config import Settings
from app.services.repository_intelligence.checkout import (
    RepositoryCheckoutCommandError,
    RepositoryCheckoutLimitError,
    RepositoryCheckoutPathError,
    RepositoryCheckoutPolicy,
    RepositoryCheckoutRequest,
    RepositoryCheckoutSHAError,
    RepositoryCheckoutTimeoutError,
    _run_bounded_process,
    materialize_repository_checkout,
)


def _git(
    repository: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["git", *arguments]
    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return completed


def _git_bytes(
    repository: Path,
    *arguments: str,
    input_bytes: bytes,
    environment: dict[str, str] | None = None,
) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        env=environment,
        input=input_bytes,
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr.decode(
        "utf-8",
        errors="replace",
    )
    return completed.stdout


def _synthetic_repository(
    path: Path,
    *,
    files: dict[str, bytes] | None = None,
    executable_paths: tuple[str, ...] = (),
) -> tuple[Path, str]:
    path.mkdir(mode=0o700, parents=True)
    _git(path, "init", "-q")
    for relative, content in (
        files
        or {
            "README.md": b"# Synthetic Repository\n",
            "src/app.py": b"print('synthetic source; never executed')\n",
        }
    ).items():
        destination = path / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.write_bytes(content)
    for relative in executable_paths:
        (path / relative).chmod(0o755)
    _git(path, "add", "--all")
    commit_environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Synthetic Fixture",
        "GIT_AUTHOR_EMAIL": "synthetic@example.test",
        "GIT_COMMITTER_NAME": "Synthetic Fixture",
        "GIT_COMMITTER_EMAIL": "synthetic@example.test",
    }
    _git(
        path,
        "commit",
        "-q",
        "-m",
        "synthetic fixture",
        environment=commit_environment,
    )
    sha = _git(path, "rev-parse", "HEAD").stdout.strip()
    assert len(sha) == 40
    return path.resolve(), sha


def _policy(
    data_path: Path,
    *,
    timeout_seconds: float = 5.0,
    max_files: int = 100,
    max_bytes: int = 1024 * 1024,
    max_file_bytes: int = 512 * 1024,
    max_command_output_bytes: int = 1024 * 1024,
    max_path_bytes: int = 512,
    max_depth: int = 32,
) -> RepositoryCheckoutPolicy:
    return RepositoryCheckoutPolicy(
        data_path=data_path,
        timeout_seconds=timeout_seconds,
        max_files=max_files,
        max_bytes=max_bytes,
        max_file_bytes=max_file_bytes,
        max_command_output_bytes=max_command_output_bytes,
        max_path_bytes=max_path_bytes,
        max_depth=max_depth,
    )


def _request(repository: Path, sha: str, *, run_id: str | None = None) -> RepositoryCheckoutRequest:
    return RepositoryCheckoutRequest(
        source_repository=repository,
        commit_sha=sha,
        run_id=run_id or f"synthetic-{uuid4().hex[:12]}",
    )


def _assert_no_runs(data_path: Path) -> None:
    worktrees = data_path / "repository-intelligence" / "worktrees"
    assert not worktrees.exists() or list(worktrees.iterdir()) == []


def test_repository_intelligence_settings_default_outside_repository_and_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Settings(_env_file=None)
    default_path = Path(config.repository_intelligence_data_path).resolve()
    repository_root = Path(checkout_service.REPOSITORY_ROOT).resolve()
    assert not default_path.is_relative_to(repository_root)

    configured = tmp_path / "ri-runtime"
    monkeypatch.setenv(
        "FOUNDEROS_REPOSITORY_INTELLIGENCE_DATA_PATH",
        str(configured),
    )
    monkeypatch.setenv(
        "FOUNDEROS_REPOSITORY_INTELLIGENCE_CHECKOUT_TIMEOUT_SECONDS",
        "12.5",
    )
    aliased = Settings(_env_file=None)
    assert Path(aliased.repository_intelligence_data_path) == configured
    assert aliased.repository_intelligence_checkout_timeout_seconds == 12.5


def test_exact_sha_materializes_read_only_and_cleans_up(tmp_path: Path) -> None:
    repository, sha = _synthetic_repository(
        tmp_path / "synthetic-source",
        files={
            "README.md": b"# Synthetic\n",
            "nested/data.txt": b"synthetic-data\n",
        },
    )
    data_path = tmp_path / "runtime-data"
    checkout_path: Path

    with materialize_repository_checkout(
        _request(repository, sha),
        policy=_policy(data_path),
    ) as checkout:
        checkout_path = checkout.path
        assert checkout.commit_sha == sha
        assert checkout.file_count == 2
        assert checkout.total_bytes == len(b"# Synthetic\nsynthetic-data\n")
        assert checkout.network_used is False
        assert checkout.target_code_executed is False
        assert checkout.files_read_only is True
        assert (checkout.path / "README.md").read_bytes() == b"# Synthetic\n"
        assert (checkout.path / "nested" / "data.txt").read_bytes() == (
            b"synthetic-data\n"
        )
        assert not (checkout.path / ".git").exists()
        assert stat.S_IMODE((checkout.path / "README.md").stat().st_mode) == 0o400
        assert stat.S_IMODE(checkout.path.stat().st_mode) == 0o500

    assert not checkout_path.exists()
    _assert_no_runs(data_path)


def test_checkout_uses_requested_historical_commit_not_current_worktree(
    tmp_path: Path,
) -> None:
    repository, first_sha = _synthetic_repository(
        tmp_path / "synthetic-source",
        files={"version.txt": b"v1\n"},
    )
    (repository / "version.txt").write_bytes(b"v2\n")
    _git(repository, "add", "version.txt")
    commit_environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Synthetic Fixture",
        "GIT_AUTHOR_EMAIL": "synthetic@example.test",
        "GIT_COMMITTER_NAME": "Synthetic Fixture",
        "GIT_COMMITTER_EMAIL": "synthetic@example.test",
    }
    _git(
        repository,
        "commit",
        "-q",
        "-m",
        "synthetic v2",
        environment=commit_environment,
    )

    with materialize_repository_checkout(
        _request(repository, first_sha),
        policy=_policy(tmp_path / "runtime-data"),
    ) as checkout:
        assert (checkout.path / "version.txt").read_bytes() == b"v1\n"


def test_checkout_never_executes_target_code_or_hooks(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    hook = (
        "#!/bin/sh\n"
        f"printf 'executed' > '{marker}'\n"
        "exit 99\n"
    ).encode()
    repository, sha = _synthetic_repository(
        tmp_path / "synthetic-source",
        files={
            "run-me.sh": hook,
            ".githooks/post-checkout": hook,
        },
        executable_paths=("run-me.sh", ".githooks/post-checkout"),
    )
    repository_config = repository / ".git" / "config"
    with repository_config.open("a", encoding="utf-8") as stream:
        stream.write("\n[core]\n\thooksPath = .githooks\n")

    with materialize_repository_checkout(
        _request(repository, sha),
        policy=_policy(tmp_path / "runtime-data"),
    ) as checkout:
        assert (checkout.path / "run-me.sh").exists()
        assert marker.exists() is False
        assert checkout.target_code_executed is False

    assert marker.exists() is False


@pytest.mark.parametrize(
    "sha",
    (
        "abc123",
        "G" * 40,
        "ABCDEF0123456789ABCDEF0123456789ABCDEF01",
    ),
)
def test_checkout_rejects_malformed_sha_before_creating_run(
    tmp_path: Path,
    sha: str,
) -> None:
    repository, _valid_sha = _synthetic_repository(tmp_path / "synthetic-source")
    data_path = tmp_path / "runtime-data"

    with pytest.raises(RepositoryCheckoutSHAError):
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=_policy(data_path),
        ):
            raise AssertionError("invalid SHA materialized")
    _assert_no_runs(data_path)


def test_checkout_rejects_missing_exact_sha_and_cleans_up(tmp_path: Path) -> None:
    repository, sha = _synthetic_repository(tmp_path / "synthetic-source")
    missing_sha = ("f" if sha[0] != "f" else "e") + sha[1:]
    data_path = tmp_path / "runtime-data"

    with pytest.raises(RepositoryCheckoutSHAError):
        with materialize_repository_checkout(
            _request(repository, missing_sha),
            policy=_policy(data_path),
        ):
            raise AssertionError("missing SHA materialized")
    _assert_no_runs(data_path)


def test_checkout_rejects_source_and_data_paths_inside_founderos(
    tmp_path: Path,
) -> None:
    repository_root = Path(checkout_service.REPOSITORY_ROOT)
    data_path = tmp_path / "runtime-data"

    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(repository_root, "0" * 40),
            policy=_policy(data_path),
        ):
            raise AssertionError("FounderOS source was accepted")

    source, sha = _synthetic_repository(tmp_path / "synthetic-source")
    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(source, sha),
            policy=_policy(repository_root / ".local" / "ri-test"),
        ):
            raise AssertionError("FounderOS-contained data path was accepted")


def test_checkout_rejects_symlinked_and_overlapping_paths(tmp_path: Path) -> None:
    repository, sha = _synthetic_repository(tmp_path / "synthetic-source")
    symlink_source = tmp_path / "source-link"
    symlink_source.symlink_to(repository, target_is_directory=True)

    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(symlink_source, sha),
            policy=_policy(tmp_path / "runtime-data"),
        ):
            raise AssertionError("symlink source was accepted")

    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=_policy(repository / "ri-runtime"),
        ):
            raise AssertionError("overlapping data path was accepted")

    real_data = tmp_path / "real-data"
    real_data.mkdir()
    symlink_data = tmp_path / "data-link"
    symlink_data.symlink_to(real_data, target_is_directory=True)
    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=_policy(symlink_data),
        ):
            raise AssertionError("symlink data path was accepted")


def test_checkout_rejects_subdirectory_and_linked_worktree_source(
    tmp_path: Path,
) -> None:
    repository, sha = _synthetic_repository(tmp_path / "synthetic-source")
    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(repository / "src", sha),
            policy=_policy(tmp_path / "runtime-a"),
        ):
            raise AssertionError("repository subdirectory was accepted")

    linked_worktree = tmp_path / "linked-worktree"
    _git(repository, "worktree", "add", "-q", "--detach", str(linked_worktree), sha)
    try:
        with pytest.raises(RepositoryCheckoutPathError):
            with materialize_repository_checkout(
                _request(linked_worktree, sha),
                policy=_policy(tmp_path / "runtime-b"),
            ):
                raise AssertionError("linked worktree was accepted")
    finally:
        _git(repository, "worktree", "remove", "--force", str(linked_worktree))


def test_checkout_rejects_git_alternates_outside_source(tmp_path: Path) -> None:
    repository, sha = _synthetic_repository(tmp_path / "synthetic-source")
    alternates = repository / ".git" / "objects" / "info" / "alternates"
    alternates.write_text(str(tmp_path / "outside-objects") + "\n", encoding="utf-8")

    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=_policy(tmp_path / "runtime-data"),
        ):
            raise AssertionError("external object boundary was accepted")


def test_checkout_rejects_external_config_includes_and_special_git_metadata(
    tmp_path: Path,
) -> None:
    include_repository, include_sha = _synthetic_repository(
        tmp_path / "include-source"
    )
    with (include_repository / ".git" / "config").open(
        "a",
        encoding="utf-8",
    ) as stream:
        stream.write("\n[include]\n\tpath = /tmp/synthetic-external-config\n")
    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(include_repository, include_sha),
            policy=_policy(tmp_path / "runtime-include"),
        ):
            raise AssertionError("external git config include was accepted")

    special_repository, special_sha = _synthetic_repository(
        tmp_path / "special-source"
    )
    os.mkfifo(special_repository / ".git" / "synthetic-fifo")
    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(special_repository, special_sha),
            policy=_policy(tmp_path / "runtime-special"),
        ):
            raise AssertionError("special git metadata entry was accepted")


@pytest.mark.parametrize(
    ("policy_overrides", "files"),
    (
        ({"max_files": 1}, {"a.txt": b"a", "b.txt": b"b"}),
        ({"max_bytes": 3}, {"large.txt": b"four"}),
        ({"max_file_bytes": 3}, {"large.txt": b"four"}),
        ({"max_command_output_bytes": 16}, {"path-name-is-long.txt": b"x"}),
        ({"max_path_bytes": 8}, {"long-name.txt": b"x"}),
        ({"max_depth": 1}, {"nested/file.txt": b"x"}),
    ),
)
def test_checkout_enforces_resource_and_output_bounds(
    tmp_path: Path,
    policy_overrides: dict[str, int],
    files: dict[str, bytes],
) -> None:
    repository, sha = _synthetic_repository(
        tmp_path / "synthetic-source",
        files=files,
    )
    data_path = tmp_path / "runtime-data"
    policy = replace(_policy(data_path), **policy_overrides)

    with pytest.raises(RepositoryCheckoutLimitError):
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=policy,
        ):
            raise AssertionError("bounded checkout was accepted")
    _assert_no_runs(data_path)


def test_checkout_rejects_symlink_and_gitlink_tree_entries(tmp_path: Path) -> None:
    symlink_repository, symlink_sha = _synthetic_repository(
        tmp_path / "symlink-source",
        files={"target.txt": b"target"},
    )
    symlink = symlink_repository / "link.txt"
    symlink.symlink_to("target.txt")
    _git(symlink_repository, "add", "link.txt")
    commit_environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Synthetic Fixture",
        "GIT_AUTHOR_EMAIL": "synthetic@example.test",
        "GIT_COMMITTER_NAME": "Synthetic Fixture",
        "GIT_COMMITTER_EMAIL": "synthetic@example.test",
    }
    _git(
        symlink_repository,
        "commit",
        "-q",
        "-m",
        "synthetic symlink",
        environment=commit_environment,
    )
    symlink_sha = _git(symlink_repository, "rev-parse", "HEAD").stdout.strip()

    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(symlink_repository, symlink_sha),
            policy=_policy(tmp_path / "runtime-symlink"),
        ):
            raise AssertionError("symlink tree entry was accepted")

    child_repository, child_sha = _synthetic_repository(tmp_path / "child-source")
    parent_repository, _parent_sha = _synthetic_repository(tmp_path / "parent-source")
    _git(
        parent_repository,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{child_sha},nested-repository",
    )
    _git(
        parent_repository,
        "commit",
        "-q",
        "-m",
        "synthetic gitlink",
        environment=commit_environment,
    )
    parent_sha = _git(parent_repository, "rev-parse", "HEAD").stdout.strip()

    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(parent_repository, parent_sha),
            policy=_policy(tmp_path / "runtime-gitlink"),
        ):
            raise AssertionError("gitlink tree entry was accepted")
    assert child_repository.exists()


def test_checkout_rejects_casefold_collisions(tmp_path: Path) -> None:
    repository, _sha = _synthetic_repository(
        tmp_path / "synthetic-source",
        files={"placeholder.txt": b"placeholder"},
    )
    first_blob = _git_bytes(
        repository,
        "hash-object",
        "-w",
        "--stdin",
        input_bytes=b"first",
    ).decode("ascii").strip()
    second_blob = _git_bytes(
        repository,
        "hash-object",
        "-w",
        "--stdin",
        input_bytes=b"second",
    ).decode("ascii").strip()
    tree_input = (
        f"100644 blob {first_blob}\tREADME.md\0"
        f"100644 blob {second_blob}\treadme.md\0"
    ).encode()
    tree_id = _git_bytes(
        repository,
        "mktree",
        "-z",
        input_bytes=tree_input,
    ).decode("ascii").strip()
    commit_environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Synthetic Fixture",
        "GIT_AUTHOR_EMAIL": "synthetic@example.test",
        "GIT_COMMITTER_NAME": "Synthetic Fixture",
        "GIT_COMMITTER_EMAIL": "synthetic@example.test",
    }
    sha = _git_bytes(
        repository,
        "commit-tree",
        tree_id,
        input_bytes=b"synthetic collision\n",
        environment=commit_environment,
    ).decode("ascii").strip()

    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=_policy(tmp_path / "runtime-data"),
        ):
            raise AssertionError("portable path collision was accepted")


def test_checkout_rejects_casefold_directory_collisions(tmp_path: Path) -> None:
    repository, _sha = _synthetic_repository(
        tmp_path / "synthetic-source",
        files={"placeholder.txt": b"placeholder"},
    )
    first_blob = _git_bytes(
        repository,
        "hash-object",
        "-w",
        "--stdin",
        input_bytes=b"first",
    ).decode("ascii").strip()
    second_blob = _git_bytes(
        repository,
        "hash-object",
        "-w",
        "--stdin",
        input_bytes=b"second",
    ).decode("ascii").strip()
    first_tree = _git_bytes(
        repository,
        "mktree",
        "-z",
        input_bytes=f"100644 blob {first_blob}\ta.txt\0".encode(),
    ).decode("ascii").strip()
    second_tree = _git_bytes(
        repository,
        "mktree",
        "-z",
        input_bytes=f"100644 blob {second_blob}\tb.txt\0".encode(),
    ).decode("ascii").strip()
    root_tree = _git_bytes(
        repository,
        "mktree",
        "-z",
        input_bytes=(
            f"040000 tree {first_tree}\tDir\0"
            f"040000 tree {second_tree}\tdir\0"
        ).encode(),
    ).decode("ascii").strip()
    commit_environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Synthetic Fixture",
        "GIT_AUTHOR_EMAIL": "synthetic@example.test",
        "GIT_COMMITTER_NAME": "Synthetic Fixture",
        "GIT_COMMITTER_EMAIL": "synthetic@example.test",
    }
    sha = _git_bytes(
        repository,
        "commit-tree",
        root_tree,
        input_bytes=b"synthetic directory collision\n",
        environment=commit_environment,
    ).decode("ascii").strip()

    with pytest.raises(RepositoryCheckoutPathError):
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=_policy(tmp_path / "runtime-data"),
        ):
            raise AssertionError("portable directory collision was accepted")


def test_checkout_cleans_up_when_consumer_raises(tmp_path: Path) -> None:
    repository, sha = _synthetic_repository(tmp_path / "synthetic-source")
    data_path = tmp_path / "runtime-data"
    checkout_path: Path | None = None

    with pytest.raises(RuntimeError, match="synthetic consumer failure"):
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=_policy(data_path),
        ) as checkout:
            checkout_path = checkout.path
            raise RuntimeError("synthetic consumer failure")

    assert checkout_path is not None and not checkout_path.exists()
    _assert_no_runs(data_path)


async def test_checkout_cleans_up_on_task_cancellation(tmp_path: Path) -> None:
    repository, sha = _synthetic_repository(tmp_path / "synthetic-source")
    data_path = tmp_path / "runtime-data"
    checkout_path: Path | None = None
    started = asyncio.Event()

    async def hold_checkout() -> None:
        nonlocal checkout_path
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=_policy(data_path),
        ) as checkout:
            checkout_path = checkout.path
            started.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(hold_checkout())
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert checkout_path is not None and not checkout_path.exists()
    _assert_no_runs(data_path)


def test_checkout_cleans_up_when_thread_is_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, sha = _synthetic_repository(tmp_path / "synthetic-source")
    data_path = tmp_path / "runtime-data"

    def cancel_after_run_directory(*_args: object, **_kwargs: object) -> bytes:
        raise asyncio.CancelledError

    monkeypatch.setattr(checkout_service, "_validate_git_repository_boundary", cancel_after_run_directory)
    with pytest.raises(asyncio.CancelledError):
        with materialize_repository_checkout(
            _request(repository, sha),
            policy=_policy(data_path),
        ):
            raise AssertionError("cancelled checkout materialized")

    _assert_no_runs(data_path)


def test_bounded_process_timeout_and_output_limit_do_not_echo_sensitive_output(
    tmp_path: Path,
) -> None:
    timeout_marker = "sensitive-timeout-value"
    with pytest.raises(RepositoryCheckoutTimeoutError) as timeout_error:
        _run_bounded_process(
            [
                "/bin/sh",
                "-c",
                f"printf '{timeout_marker}' >&2; sleep 2",
            ],
            cwd=tmp_path,
            environment={"PATH": os.defpath},
            deadline=time.monotonic() + 0.05,
            stdout_limit=16,
        )
    assert timeout_marker not in str(timeout_error.value)

    output_marker = "sensitive-output-value"
    with pytest.raises(RepositoryCheckoutLimitError) as output_error:
        _run_bounded_process(
            ["/bin/sh", "-c", f"printf '{output_marker}'"],
            cwd=tmp_path,
            environment={"PATH": os.defpath},
            deadline=time.monotonic() + 2,
            stdout_limit=4,
        )
    assert output_marker not in str(output_error.value)


def test_checkout_errors_never_include_source_path_or_sensitive_git_output(
    tmp_path: Path,
) -> None:
    repository, sha = _synthetic_repository(
        tmp_path / "private-source-name",
        files={"README.md": b"synthetic"},
    )
    private_marker = "private-source-name"
    missing_sha = ("f" if sha[0] != "f" else "e") + sha[1:]

    with pytest.raises(RepositoryCheckoutCommandError) as command_error:
        _run_bounded_process(
            ["/bin/sh", "-c", "printf 'sensitive diagnostic' >&2; exit 7"],
            cwd=repository,
            environment={"PATH": os.defpath},
            deadline=time.monotonic() + 2,
            stdout_limit=16,
        )
    assert "sensitive diagnostic" not in str(command_error.value)

    with pytest.raises(RepositoryCheckoutSHAError) as sha_error:
        with materialize_repository_checkout(
            _request(repository, missing_sha),
            policy=_policy(tmp_path / "runtime-data"),
        ):
            raise AssertionError("missing SHA materialized")
    assert private_marker not in str(sha_error.value)


def test_checkout_source_contains_no_clone_fetch_checkout_or_target_execution_path() -> None:
    source = Path(checkout_service.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "\"clone\",",
        "\"fetch\",",
        "\"checkout\",",
        "\"worktree\",",
        "shell=True",
        "os.system",
        "source_repository.read_",
        "FOUNDEROS_SECRET_ENCRYPTION_KEY",
        "DATABASE_URL",
    ):
        assert forbidden not in source
