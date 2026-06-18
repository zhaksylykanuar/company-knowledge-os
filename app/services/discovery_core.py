"""Read-only discovery core.

Shared, network-free foundation for the per-source discovery scripts (Jira,
GitHub). It does three things, none of which touch the network or any provider:

1. **Credential preflight** — checks whether the *names* of the required local
   env vars are present (never their values) and reports the exact missing var
   names so the operator can fix ``.env.local`` without any secret leaving the
   process. Env var names are public configuration, not secrets.
2. **Safe local output** — full provider payloads are written under the
   gitignored ``.local/discovery/<source>/`` tree (founder-facing local files
   may contain real names); only sanitized counts/classes/paths are ever
   returned for stdout/chat.
3. **Sanitized summaries** — every summary is leak-checked with
   :func:`app.services.operator_output_sanitizer.inspect_operator_output`
   before it is returned.

Discovery is read-only by contract: this module exposes no write path. The
scripts that use it make GET-only calls behind the live-provider ack.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.operator_output_sanitizer import inspect_operator_output

DISCOVERY_LOCAL_DIRNAME = ".local"
DISCOVERY_SUBDIR = "discovery"

SOURCE_JIRA = "jira"
SOURCE_GITHUB = "github"

# Required local env var NAMES per source. Names only; values are never read.
CREDENTIAL_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    SOURCE_JIRA: (
        "FOS_JIRA_READONLY_SITE",
        "FOS_JIRA_READONLY_USER",
        "FOS_JIRA_READONLY_TOKEN",
    ),
    SOURCE_GITHUB: (
        "FOS_GITHUB_READONLY_TOKEN",
        "FOS_GITHUB_TARGET_ORG",
    ),
}
# Optional vars that enrich discovery but are not required for it to run.
OPTIONAL_CREDENTIALS: dict[str, tuple[str, ...]] = {
    SOURCE_JIRA: (),
    SOURCE_GITHUB: ("FOS_GITHUB_READONLY_ACCOUNT",),
}

SAFE_SOURCES = frozenset(CREDENTIAL_REQUIREMENTS)

# The only env var names discovery ever reads from local env files. Restricting
# the parse to this allowlist keeps unrelated secrets out of memory entirely.
DISCOVERY_ENV_KEYS: frozenset[str] = frozenset(
    name
    for source in SAFE_SOURCES
    for name in (*CREDENTIAL_REQUIREMENTS[source], *OPTIONAL_CREDENTIALS.get(source, ()))
)

# Local env files, lowest precedence first; later files override earlier ones.
DISCOVERY_ENV_FILES = (".env", ".env.local")

CRED_READY = "credentials_present"
CRED_MISSING = "credentials_missing"
CRED_UNKNOWN_SOURCE = "unknown_discovery_source"


@dataclass(frozen=True)
class CredentialPreflight:
    """Presence-only view of a source's local credentials.

    ``missing_var_names`` holds the exact env var names still to be set; those
    names are allowlisted as safe values by the operator output sanitizer, so a
    preflight summary is safe to print. No credential *value* is ever read.
    """

    source: str
    ready: bool
    reason_code: str
    required_var_names: tuple[str, ...]
    present_var_names: tuple[str, ...]
    missing_var_names: tuple[str, ...]
    optional_present_var_names: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ready": self.ready,
            "reason_code": self.reason_code,
            "required_var_count": len(self.required_var_names),
            "present_var_count": len(self.present_var_names),
            "missing_var_count": len(self.missing_var_names),
            "missing_var_names": list(self.missing_var_names),
            "optional_present_var_names": list(self.optional_present_var_names),
        }


@dataclass(frozen=True)
class ArtifactRef:
    """Sanitized reference to a locally written discovery artifact.

    Carries no payload and no hash (a hex digest would look like a secret to the
    sanitizer); only the local path, the record count, and the byte size.
    """

    artifact_name: str
    relative_path: str
    record_count: int
    byte_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "relative_path": self.relative_path,
            "record_count": self.record_count,
            "byte_count": self.byte_count,
        }


def _env_value_present(environ: Mapping[str, str], name: str) -> bool:
    value = environ.get(name)
    return isinstance(value, str) and bool(value.strip())


def credential_preflight(
    source: str,
    environ: Mapping[str, str],
) -> CredentialPreflight:
    """Report whether ``source`` has its required local credentials set.

    Reads only the *presence* of each required env var name. Unknown sources
    fail closed with no required/present vars.
    """

    if source not in SAFE_SOURCES:
        return CredentialPreflight(
            source=_safe_source(source),
            ready=False,
            reason_code=CRED_UNKNOWN_SOURCE,
            required_var_names=(),
            present_var_names=(),
            missing_var_names=(),
            optional_present_var_names=(),
        )

    required = CREDENTIAL_REQUIREMENTS[source]
    optional = OPTIONAL_CREDENTIALS.get(source, ())
    present = tuple(name for name in required if _env_value_present(environ, name))
    missing = tuple(name for name in required if name not in present)
    optional_present = tuple(name for name in optional if _env_value_present(environ, name))
    ready = not missing
    return CredentialPreflight(
        source=source,
        ready=ready,
        reason_code=CRED_READY if ready else CRED_MISSING,
        required_var_names=required,
        present_var_names=present,
        missing_var_names=missing,
        optional_present_var_names=optional_present,
    )


def discovery_dir(source: str, *, root: Path) -> Path:
    """Return (and create) the local discovery directory for ``source``.

    Always under ``<root>/.local/discovery/<source>/`` — a gitignored tree.
    """

    safe = _safe_source(source)
    target = Path(root) / DISCOVERY_LOCAL_DIRNAME / DISCOVERY_SUBDIR / safe
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_local_artifact(
    source: str,
    *,
    root: Path,
    artifact_name: str,
    records: Any,
) -> ArtifactRef:
    """Write a full discovery payload to a local file; return a sanitized ref.

    The file lives under the gitignored discovery tree and may contain real
    provider data (it never leaves the machine). The returned :class:`ArtifactRef`
    is the only thing safe to surface.
    """

    safe_name = _safe_artifact_name(artifact_name)
    directory = discovery_dir(source, root=root)
    path = directory / f"{safe_name}.json"
    text = json.dumps(records, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    record_count = len(records) if isinstance(records, (list, tuple, dict)) else 1
    relative_path = (
        f"{DISCOVERY_LOCAL_DIRNAME}/{DISCOVERY_SUBDIR}/{_safe_source(source)}/{safe_name}.json"
    )
    return ArtifactRef(
        artifact_name=safe_name,
        relative_path=relative_path,
        record_count=record_count,
        byte_count=len(text.encode("utf-8")),
    )


def assert_summary_safe(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Leak-check a stdout summary; raise if it would expose anything unsafe."""

    safety = inspect_operator_output(summary)
    if not safety.safe:
        raise ValueError("discovery_summary_unsafe")
    return dict(summary)


def load_discovery_environment(
    *,
    root: Path,
    base_environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the discovery env from local files, restricted to the allowlist.

    Reads only :data:`DISCOVERY_ENV_KEYS` from ``.env`` then ``.env.local``
    (local overrides), layered over ``base_environ``. Values are held in memory
    only and never logged. Unrelated keys in the files are ignored entirely.
    """

    env: dict[str, str] = {
        key: value
        for key, value in (base_environ or {}).items()
        if key in DISCOVERY_ENV_KEYS and isinstance(value, str)
    }
    for filename in DISCOVERY_ENV_FILES:
        path = Path(root) / filename
        env.update(_parse_env_allowlisted(path))
    return env


def _parse_env_allowlisted(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        name, _, value = line.partition("=")
        name = name.strip()
        if name not in DISCOVERY_ENV_KEYS:
            continue
        cleaned = value.strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
            cleaned = cleaned[1:-1]
        parsed[name] = cleaned
    return parsed


def run_dir(source: str, *, root: Path, timestamp: str) -> Path:
    """Create and return ``<root>/.local/discovery/<source>/<timestamp>/``."""

    target = (
        Path(root)
        / DISCOVERY_LOCAL_DIRNAME
        / DISCOVERY_SUBDIR
        / _safe_source(source)
        / _safe_timestamp(timestamp)
    )
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_run_artifact(
    *,
    root: Path,
    run_directory: Path,
    name: str,
    records: Any,
    subdir: str | None = None,
    scrub: Any = None,
) -> ArtifactRef:
    """Write a JSON artifact inside a run dir; optionally scrub before saving."""

    directory = run_directory / _safe_artifact_name(subdir) if subdir else run_directory
    directory.mkdir(parents=True, exist_ok=True)
    payload = scrub(records) if callable(scrub) else records
    safe_name = _safe_artifact_name(name)
    path = directory / f"{safe_name}.json"
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    record_count = len(payload) if isinstance(payload, (list, tuple, dict)) else 1
    return ArtifactRef(
        artifact_name=safe_name,
        relative_path=_relative_path(path, root),
        record_count=record_count,
        byte_count=len(text.encode("utf-8")),
    )


def write_run_text(
    *,
    root: Path,
    run_directory: Path,
    name: str,
    text: str,
    extension: str = "md",
) -> ArtifactRef:
    """Write a text artifact (e.g. an audit.md) inside a run dir."""

    run_directory.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_artifact_name(name)
    safe_ext = _safe_artifact_name(extension) or "txt"
    path = run_directory / f"{safe_name}.{safe_ext}"
    body = text if text.endswith("\n") else text + "\n"
    path.write_text(body, encoding="utf-8")
    return ArtifactRef(
        artifact_name=f"{safe_name}.{safe_ext}",
        relative_path=_relative_path(path, root),
        record_count=body.count("\n"),
        byte_count=len(body.encode("utf-8")),
    )


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(Path(root)))
    except ValueError:
        return str(path)


def _safe_timestamp(timestamp: str) -> str:
    cleaned = "".join(c for c in str(timestamp) if c.isalnum() or c in {"-", "_"})
    return cleaned or "run"


def _safe_source(source: str) -> str:
    if source in SAFE_SOURCES:
        return source
    return "unknown_source"


def _safe_artifact_name(name: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in str(name).strip().casefold()
    ).strip("_-")
    return cleaned or "artifact"
