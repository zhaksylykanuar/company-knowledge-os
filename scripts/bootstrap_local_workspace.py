#!/usr/bin/env python
"""Bootstrap FounderOS local runtime workspace under ``.local/``.

The script creates gitignored local runtime directories, updates `.env.local`
through a managed block without deleting user secrets, and safely copies an
older Obsidian vault into the project-local vault when one is configured.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VAULT_NAME = "FounderOS Knowledge Vault"
MANAGED_START = "# --- FounderOS local workspace: managed by bootstrap_local_workspace.py ---"
MANAGED_END = "# --- end FounderOS local workspace ---"
LOCAL_DEV_KEY = "local-dev-key"
LOCAL_DIRS = (
    ".local",
    ".local/obsidian",
    f".local/obsidian/{VAULT_NAME}",
    ".local/data",
    ".local/logs",
    ".local/tmp",
    ".local/exports",
    ".local/cache",
    ".local/backups",
)
SENSITIVE_KEY_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CLIENT_SECRET)", re.IGNORECASE)


@dataclass(frozen=True)
class BootstrapPaths:
    repo_root: Path
    workspace_path: Path
    obsidian_root: Path
    vault_path: Path
    env_local_path: Path
    migration_log_path: Path


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def local_paths(repo_root: Path) -> BootstrapPaths:
    root = repo_root.resolve()
    workspace = root / ".local"
    vault = workspace / "obsidian" / VAULT_NAME
    return BootstrapPaths(
        repo_root=root,
        workspace_path=workspace,
        obsidian_root=workspace / "obsidian",
        vault_path=vault,
        env_local_path=root / ".env.local",
        migration_log_path=workspace / "migration-log.json",
    )


def parse_env_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        values[key] = value.strip().strip('"').strip("'")
    return values


def _merge_csv(existing: str | None, additions: list[str]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for value in [*(existing or "").split(","), *additions]:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return ",".join(out)


def managed_env_values(existing: dict[str, str], paths: BootstrapPaths) -> dict[str, str]:
    dev_key = existing.get("FOUNDEROS_DEV_API_KEY") or LOCAL_DEV_KEY
    api_keys = _merge_csv(existing.get("FOUNDEROS_API_KEYS"), [LOCAL_DEV_KEY, dev_key])
    return {
        "APP_ENV": "local",
        "FOUNDEROS_API_BASE_URL": "http://127.0.0.1:8765",
        "FOUNDEROS_DEV_API_KEY": dev_key,
        "FOUNDEROS_API_KEYS": api_keys,
        "FOUNDEROS_ENABLE_BROWSER_DEV_CONFIG": "true",
        "FOUNDEROS_LOCAL_WORKSPACE_PATH": str(paths.workspace_path),
        "FOUNDEROS_ENABLE_OBSIDIAN_BRIDGE": "true",
        "FOUNDEROS_OBSIDIAN_VAULT_NAME": VAULT_NAME,
        "FOUNDEROS_OBSIDIAN_VAULT_PATH": str(paths.vault_path),
        "FOUNDEROS_OBSIDIAN_SYNC_MODE": "manual",
    }


def render_managed_block(values: dict[str, str]) -> str:
    lines = [MANAGED_START]
    lines.extend(f"{key}={value}" for key, value in values.items())
    lines.append(MANAGED_END)
    return "\n".join(lines)


def strip_managed_block(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == MANAGED_START:
            skipping = True
            continue
        if skipping and line.strip() == MANAGED_END:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "\n".join(out).rstrip()


def update_env_local_text(existing_text: str, values: dict[str, str]) -> str:
    base = strip_managed_block(existing_text)
    block = render_managed_block(values)
    return (f"{base}\n\n{block}\n" if base else f"{block}\n")


def _mask_value(key: str, value: str) -> str:
    return "***redacted***" if SENSITIVE_KEY_RE.search(key) else value


def redacted_env_updates(values: dict[str, str]) -> dict[str, str]:
    return {key: _mask_value(key, value) for key, value in values.items()}


def _path_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _contains_files(path: Path) -> bool:
    return path.exists() and path.is_dir() and any(item.is_file() for item in path.rglob("*"))


def _conflict_path(dest: Path, timestamp: str) -> Path:
    suffix = dest.suffix
    stem = dest.name[: -len(suffix)] if suffix else dest.name
    candidate = dest.with_name(f"{stem}.conflict-{timestamp}{suffix}")
    counter = 2
    while candidate.exists():
        candidate = dest.with_name(f"{stem}.conflict-{timestamp}-{counter}{suffix}")
        counter += 1
    return candidate


def plan_vault_migration(
    *,
    old_vault_path: str | None,
    paths: BootstrapPaths,
    timestamp: str,
    apply: bool,
) -> dict[str, Any]:
    log: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "migrated_from": old_vault_path,
        "migrated_to": str(paths.vault_path),
        "copied_files": [],
        "skipped_files": [],
        "conflicts": [],
        "warnings": [],
    }
    if not old_vault_path:
        log["warnings"].append("no existing vault path configured")
        return log
    old_path = Path(old_vault_path).expanduser()
    if not old_path.is_absolute():
        old_path = (paths.repo_root / old_path).resolve()
    if not old_path.exists() or not old_path.is_dir():
        log["warnings"].append("configured old vault path does not exist")
        return log
    if _path_inside(old_path, paths.workspace_path):
        log["warnings"].append("configured vault already lives inside .local")
        return log
    if not _contains_files(old_path):
        log["warnings"].append("configured old vault is empty")
        return log

    for source in sorted(item for item in old_path.rglob("*") if item.is_file()):
        relative = source.relative_to(old_path)
        dest = paths.vault_path / relative
        if dest.exists():
            if source.read_bytes() == dest.read_bytes():
                log["skipped_files"].append(relative.as_posix())
            else:
                conflict = _conflict_path(dest, timestamp)
                log["conflicts"].append(
                    {"source": relative.as_posix(), "conflict": conflict.relative_to(paths.vault_path).as_posix()}
                )
                if apply:
                    conflict.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, conflict)
            continue
        log["copied_files"].append(relative.as_posix())
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    return log


def _migration_has_inventory(log: dict[str, Any]) -> bool:
    return bool(log.get("copied_files") or log.get("skipped_files") or log.get("conflicts"))


def bootstrap_local_workspace(
    *,
    repo_root: Path | None = None,
    apply: bool,
) -> dict[str, Any]:
    paths = local_paths(repo_root or repo_root_from_script())
    existing_text = (
        paths.env_local_path.read_text(encoding="utf-8")
        if paths.env_local_path.exists()
        else ""
    )
    existing_values = parse_env_values(existing_text)
    old_vault_path = existing_values.get("FOUNDEROS_OBSIDIAN_VAULT_PATH")
    managed_values = managed_env_values(existing_values, paths)
    new_env_text = update_env_local_text(existing_text, managed_values)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    migration_log = plan_vault_migration(
        old_vault_path=old_vault_path,
        paths=paths,
        timestamp=timestamp,
        apply=apply,
    )
    planned_dirs = [str(paths.repo_root / relative) for relative in LOCAL_DIRS]

    if apply:
        for relative in LOCAL_DIRS:
            (paths.repo_root / relative).mkdir(parents=True, exist_ok=True)
        paths.env_local_path.write_text(new_env_text, encoding="utf-8")
        write_migration_log = (
            _migration_has_inventory(migration_log)
            or not paths.migration_log_path.exists()
        )
        if write_migration_log:
            paths.migration_log_path.write_text(
                json.dumps(migration_log, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )

    return {
        "status": "applied" if apply else "dry_run",
        "repo_root": str(paths.repo_root),
        "workspace_path": str(paths.workspace_path),
        "vault_path": str(paths.vault_path),
        "env_local_path": str(paths.env_local_path),
        "planned_directories": planned_dirs,
        "env_updates": redacted_env_updates(managed_values),
        "env_local_changed": existing_text != new_env_text,
        "migration": migration_log,
        "warnings": migration_log.get("warnings", []),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = bootstrap_local_workspace(apply=bool(args.apply))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
