"""Bounded static collectors for synthetic Repository Intelligence checkouts.

The collector reads regular files from one RI-003 materialized checkout. It
never imports modules, executes target commands, follows links, reads provider
data, persists results, or emits file bodies.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import stat
import time
import tomllib
from typing import Any, Literal
import unicodedata
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from typing_extensions import Annotated

from app.services.repository_intelligence.checkout import MaterializedRepositoryCheckout
from app.services.repository_intelligence.contracts import (
    EvidenceRefV1,
    RepositoryClaimV1,
)
from app.services.repository_intelligence.taxonomy import (
    AnalyzerClaimStatus,
    EvidenceKind,
    EvidenceSource,
    REPOSITORY_INTELLIGENCE_MAX_BYTES,
    REPOSITORY_INTELLIGENCE_MAX_ITEMS,
)


_SAFE_IDENTIFIER = re.compile(r"^(?=.{1,255}$)[A-Za-z0-9@/_.:+*-]+$")
_SAFE_CLAIM_KEY = re.compile(r"[^a-z0-9]+")
_PYTHON_MAIN = re.compile(
    r"""(?m)^\s*if\s+__name__\s*==\s*["']__main__["']\s*:"""
)
_ROUTE_DECORATOR = re.compile(
    r"""(?m)^\s*@(?:[A-Za-z_][A-Za-z0-9_]*\.)?"""
    r"""(?:get|post|put|patch|delete|options|head|api_route)\(\s*"""
    r"""["']([^"'\r\n]{1,200})["']"""
)
_MARKDOWN_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S")
_SQL_TABLE = re.compile(
    r"""(?i)\b(?:create\s+table|alter\s+table)\s+"""
    r"""(?:if\s+not\s+exists\s+)?["`]?([A-Za-z_][A-Za-z0-9_.-]{0,127})"""
)
_TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".conf",
        ".css",
        ".dockerfile",
        ".graphql",
        ".hcl",
        ".html",
        ".ini",
        ".js",
        ".json",
        ".jsx",
        ".md",
        ".mjs",
        ".py",
        ".rst",
        ".sql",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
)
_MANIFEST_NAMES = frozenset(
    {
        "cargo.toml",
        "composer.json",
        "go.mod",
        "package.json",
        "pom.xml",
        "pyproject.toml",
        "requirements.txt",
    }
)
_LOCKFILE_NAMES = frozenset(
    {
        "cargo.lock",
        "composer.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "yarn.lock",
    }
)
_DOCUMENT_NAMES = frozenset(
    {
        "architecture.md",
        "changelog.md",
        "contributing.md",
        "readme.md",
        "readme.rst",
        "readme.txt",
    }
)
_CI_NAMES = frozenset(
    {
        ".circleci/config.yml",
        ".circleci/config.yaml",
        ".gitlab-ci.yml",
        "azure-pipelines.yml",
        "bitbucket-pipelines.yml",
        "jenkinsfile",
    }
)
_DEPLOYMENT_NAMES = frozenset(
    {
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "fly.toml",
        "netlify.toml",
        "procfile",
        "render.yaml",
        "vercel.json",
    }
)
_INTERFACE_NAMES = frozenset(
    {
        "api.graphql",
        "asyncapi.json",
        "asyncapi.yaml",
        "asyncapi.yml",
        "openapi.json",
        "openapi.yaml",
        "openapi.yml",
        "schema.graphql",
    }
)
_ENTRYPOINT_BASENAMES = frozenset(
    {
        "__main__.py",
        "app.py",
        "cli.py",
        "main.py",
        "manage.py",
        "server.py",
        "worker.py",
    }
)
_TEST_DIRECTORY_PARTS = frozenset(
    {
        "__tests__",
        "e2e",
        "integration",
        "spec",
        "specs",
        "test",
        "tests",
    }
)
_IGNORED_DIRECTORY_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".terraform",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "vendor",
    }
)
_DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)


class RepositoryStaticCollectionError(RuntimeError):
    """Sanitized static collection failure."""


class RepositoryStaticCollectionPathError(RepositoryStaticCollectionError):
    """The supplied checkout or an inspected file crossed a safety boundary."""


class RepositoryStaticCollectionLimitError(RepositoryStaticCollectionError):
    """The collection exceeded an explicit resource or output bound."""


class RepositoryStaticCollectionParseError(RepositoryStaticCollectionError):
    """A recognized structured file failed bounded strict parsing."""


@dataclass(frozen=True)
class RepositoryStaticCollectorPolicy:
    timeout_seconds: float = 10.0
    max_files: int = 2_000
    max_total_bytes: int = 16 * 1024 * 1024
    max_file_bytes: int = 512 * 1024
    max_path_bytes: int = 512
    max_depth: int = 32
    max_dependencies_per_manifest: int = 100
    max_items_per_category: int = REPOSITORY_INTELLIGENCE_MAX_ITEMS
    max_total_items: int = REPOSITORY_INTELLIGENCE_MAX_ITEMS
    max_output_bytes: int = REPOSITORY_INTELLIGENCE_MAX_BYTES
    max_text_chars: int = 255

    def validate(self) -> None:
        if self.timeout_seconds <= 0:
            raise RepositoryStaticCollectionLimitError(
                "collector timeout must be positive"
            )
        integer_bounds = (
            self.max_files,
            self.max_total_bytes,
            self.max_file_bytes,
            self.max_path_bytes,
            self.max_depth,
            self.max_dependencies_per_manifest,
            self.max_items_per_category,
            self.max_total_items,
            self.max_output_bytes,
            self.max_text_chars,
        )
        if any(value <= 0 for value in integer_bounds):
            raise RepositoryStaticCollectionLimitError(
                "collector resource bounds must be positive"
            )
        if self.max_file_bytes > self.max_total_bytes:
            raise RepositoryStaticCollectionLimitError(
                "collector file bound cannot exceed total byte bound"
            )
        if self.max_items_per_category > REPOSITORY_INTELLIGENCE_MAX_ITEMS:
            raise RepositoryStaticCollectionLimitError(
                "collector item bound exceeds the Repository Intelligence contract"
            )
        if self.max_total_items > REPOSITORY_INTELLIGENCE_MAX_ITEMS:
            raise RepositoryStaticCollectionLimitError(
                "collector total-item bound exceeds the Repository Intelligence contract"
            )
        if self.max_output_bytes > REPOSITORY_INTELLIGENCE_MAX_BYTES:
            raise RepositoryStaticCollectionLimitError(
                "collector output bound exceeds the Repository Intelligence contract"
            )
        if self.max_text_chars > 255:
            raise RepositoryStaticCollectionLimitError(
                "collector text bound exceeds the Repository Intelligence contract"
            )


StrictCollectorText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255),
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepositoryStaticFactV1(_StrictModel):
    fact_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    category: Literal[
        "manifest",
        "entrypoint",
        "dependency",
        "interface",
        "deployment",
        "test_ci",
        "documentation",
        "migration",
    ]
    fact_type: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    value: StrictCollectorText
    path: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    evidence_ref: EvidenceRefV1

    @field_validator("fact_id", "fact_type", "value", "path")
    @classmethod
    def validate_safe_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("collector text must not contain surrounding whitespace")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("collector text contains control characters")
        return value


class RepositoryStaticCollectionV1(_StrictModel):
    schema_version: Literal["repository_static_collection.v1"]
    workspace_id: UUID
    repository_id: UUID
    commit_sha: Annotated[
        str,
        StringConstraints(
            min_length=40,
            max_length=40,
            pattern=r"^[0-9a-f]{40}$",
        ),
    ]
    manifests: list[RepositoryStaticFactV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    entrypoints: list[RepositoryStaticFactV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    dependencies: list[RepositoryStaticFactV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    interfaces: list[RepositoryStaticFactV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    deployment: list[RepositoryStaticFactV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    tests_ci: list[RepositoryStaticFactV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    documentation: list[RepositoryStaticFactV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    migrations: list[RepositoryStaticFactV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    files_considered: int = Field(ge=0)
    bytes_read: int = Field(ge=0)
    skipped_files: int = Field(ge=0)
    target_code_executed: Literal[False] = False
    network_used: Literal[False] = False
    limitations: list[StrictCollectorText] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )

    def facts(self) -> Iterable[RepositoryStaticFactV1]:
        yield from self.manifests
        yield from self.entrypoints
        yield from self.dependencies
        yield from self.interfaces
        yield from self.deployment
        yield from self.tests_ci
        yield from self.documentation
        yield from self.migrations

    def analyzer_claims(self) -> list[RepositoryClaimV1]:
        """Project collected facts into the strict RI-001 analyzer claim shape."""

        section_by_category = {
            "manifest": "manifest",
            "entrypoint": "entrypoint",
            "dependency": "dependency",
            "interface": "interface",
            "deployment": "deployment",
            "test_ci": "test_ci",
            "documentation": "documentation",
            "migration": "migration",
        }
        return [
            RepositoryClaimV1(
                workspace_id=self.workspace_id,
                status=AnalyzerClaimStatus.OBSERVED,
                confidence=1.0,
                evidence_refs=[fact.evidence_ref],
                claim_id=fact.fact_id,
                claim_type=section_by_category[fact.category],
                summary=f"{fact.fact_type}: {fact.value}",
                details=[fact.path],
            )
            for fact in self.facts()
        ]

    def deterministic_json(self) -> bytes:
        """Return strict stable JSON suitable for validation or artifact hashing."""

        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


@dataclass
class _MutableCollection:
    manifests: list[RepositoryStaticFactV1] = field(default_factory=list)
    entrypoints: list[RepositoryStaticFactV1] = field(default_factory=list)
    dependencies: list[RepositoryStaticFactV1] = field(default_factory=list)
    interfaces: list[RepositoryStaticFactV1] = field(default_factory=list)
    deployment: list[RepositoryStaticFactV1] = field(default_factory=list)
    tests_ci: list[RepositoryStaticFactV1] = field(default_factory=list)
    documentation: list[RepositoryStaticFactV1] = field(default_factory=list)
    migrations: list[RepositoryStaticFactV1] = field(default_factory=list)
    files_considered: int = 0
    bytes_read: int = 0
    skipped_files: int = 0


@dataclass(frozen=True)
class _CollectorContext:
    workspace_id: UUID
    repository_id: UUID
    repository_full_name: str
    commit_sha: str
    policy: RepositoryStaticCollectorPolicy
    deadline: float


def validate_repository_static_collection_json(
    raw_payload: str | bytes,
) -> RepositoryStaticCollectionV1:
    """Validate one strict bounded serialized collector result."""

    if isinstance(raw_payload, str):
        encoded = raw_payload.encode("utf-8")
    elif isinstance(raw_payload, bytes):
        encoded = raw_payload
    else:
        raise RepositoryStaticCollectionParseError(
            "collector payload must be JSON text or bytes"
        )
    if len(encoded) > REPOSITORY_INTELLIGENCE_MAX_BYTES:
        raise RepositoryStaticCollectionLimitError(
            "collector payload exceeds the configured byte bound"
        )
    try:
        return RepositoryStaticCollectionV1.model_validate_json(encoded)
    except (ValueError, TypeError) as exc:
        raise RepositoryStaticCollectionParseError(
            "collector payload failed strict validation"
        ) from exc


def collect_repository_static_facts(
    checkout: MaterializedRepositoryCheckout,
    *,
    workspace_id: UUID,
    repository_id: UUID,
    repository_full_name: str,
    policy: RepositoryStaticCollectorPolicy | None = None,
) -> RepositoryStaticCollectionV1:
    """Collect deterministic static facts from one read-only RI-003 checkout."""

    selected_policy = policy or RepositoryStaticCollectorPolicy()
    selected_policy.validate()
    _validate_repository_full_name(repository_full_name)
    root = _validate_checkout(checkout)
    actual_file_count, actual_total_bytes = _checkout_manifest(
        root,
        policy=selected_policy,
        deadline=time.monotonic() + selected_policy.timeout_seconds,
    )
    if (
        actual_file_count != checkout.file_count
        or actual_total_bytes != checkout.total_bytes
    ):
        raise RepositoryStaticCollectionPathError(
            "collector checkout manifest changed before inspection"
        )
    context = _CollectorContext(
        workspace_id=workspace_id,
        repository_id=repository_id,
        repository_full_name=repository_full_name,
        commit_sha=checkout.commit_sha,
        policy=selected_policy,
        deadline=time.monotonic() + selected_policy.timeout_seconds,
    )
    collection = _MutableCollection()
    for relative_path, absolute_path, size in _bounded_files(root, context=context):
        _require_time_remaining(context.deadline)
        collection.files_considered += 1
        normalized = relative_path.as_posix()
        lower_path = normalized.casefold()
        basename = relative_path.name.casefold()
        suffix = relative_path.suffix.casefold()

        classification = _file_classification(
            lower_path=lower_path,
            basename=basename,
            suffix=suffix,
        )
        if not classification:
            collection.skipped_files += 1
            continue
        if size > selected_policy.max_file_bytes:
            collection.skipped_files += 1
            continue
        raw = _read_bounded_file(
            absolute_path,
            expected_size=size,
            root=root,
            context=context,
        )
        collection.bytes_read += len(raw)
        if collection.bytes_read > selected_policy.max_total_bytes:
            raise RepositoryStaticCollectionLimitError(
                "collector exceeded the configured total byte bound"
            )

        if "manifest" in classification:
            _collect_manifest(
                relative_path=relative_path,
                raw=raw,
                collection=collection,
                context=context,
            )
        text = _decode_text(raw)
        if "entrypoint" in classification:
            _collect_entrypoint(
                relative_path=relative_path,
                text=text,
                collection=collection,
                context=context,
            )
        if "interface" in classification:
            _collect_interface(
                relative_path=relative_path,
                text=text,
                collection=collection,
                context=context,
            )
        if "deployment" in classification:
            _collect_deployment(
                relative_path=relative_path,
                collection=collection,
                context=context,
            )
        if "test_ci" in classification:
            _collect_test_ci(
                relative_path=relative_path,
                text=text,
                collection=collection,
                context=context,
            )
        if "documentation" in classification:
            _collect_documentation(
                relative_path=relative_path,
                text=text,
                collection=collection,
                context=context,
            )
        if "migration" in classification:
            _collect_migration(
                relative_path=relative_path,
                text=text,
                collection=collection,
                context=context,
            )

    result = RepositoryStaticCollectionV1(
        schema_version="repository_static_collection.v1",
        workspace_id=workspace_id,
        repository_id=repository_id,
        commit_sha=checkout.commit_sha,
        manifests=_sorted_unique(collection.manifests),
        entrypoints=_sorted_unique(collection.entrypoints),
        dependencies=_sorted_unique(collection.dependencies),
        interfaces=_sorted_unique(collection.interfaces),
        deployment=_sorted_unique(collection.deployment),
        tests_ci=_sorted_unique(collection.tests_ci),
        documentation=_sorted_unique(collection.documentation),
        migrations=_sorted_unique(collection.migrations),
        files_considered=collection.files_considered,
        bytes_read=collection.bytes_read,
        skipped_files=collection.skipped_files,
        limitations=[
            "Static exact-SHA collection only; target repository code was not executed.",
            "Only recognized bounded text manifests and source clues were inspected.",
            "Collected output contains sanitized identifiers and paths, not file bodies or values.",
        ],
    )
    facts = list(result.facts())
    if len(facts) > selected_policy.max_total_items:
        raise RepositoryStaticCollectionLimitError(
            "collector exceeded the configured total-item bound"
        )
    encoded = result.deterministic_json()
    if len(encoded) > selected_policy.max_output_bytes:
        raise RepositoryStaticCollectionLimitError(
            "collector exceeded the configured output byte bound"
        )
    return validate_repository_static_collection_json(encoded)


def _validate_repository_full_name(value: str) -> None:
    if (
        value != value.strip()
        or value.count("/") != 1
        or not _SAFE_IDENTIFIER.fullmatch(value)
    ):
        raise RepositoryStaticCollectionPathError(
            "collector repository identity is invalid"
        )


def _validate_checkout(checkout: MaterializedRepositoryCheckout) -> Path:
    if checkout.target_code_executed or checkout.network_used:
        raise RepositoryStaticCollectionPathError(
            "collector requires a no-execution, no-network checkout"
        )
    if not checkout.files_read_only:
        raise RepositoryStaticCollectionPathError(
            "collector requires a read-only checkout"
        )
    try:
        metadata = checkout.path.lstat()
        root = checkout.path.resolve(strict=True)
    except OSError as exc:
        raise RepositoryStaticCollectionPathError(
            "collector checkout is unavailable"
        ) from exc
    if not stat.S_ISDIR(metadata.st_mode) or checkout.path.is_symlink():
        raise RepositoryStaticCollectionPathError(
            "collector checkout boundary is invalid"
        )
    return root


def _bounded_files(
    root: Path,
    *,
    context: _CollectorContext,
) -> Iterable[tuple[PurePosixPath, Path, int]]:
    candidates: list[tuple[PurePosixPath, Path, int]] = []
    total_files = 0
    try:
        for absolute_path in root.rglob("*"):
            _require_time_remaining(context.deadline)
            relative_path = _safe_relative_path(
                absolute_path,
                root=root,
                policy=context.policy,
            )
            metadata = absolute_path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise RepositoryStaticCollectionPathError(
                    "collector checkout contains an unsupported link"
                )
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise RepositoryStaticCollectionPathError(
                    "collector checkout contains an unsupported file type"
                )
            total_files += 1
            if total_files > context.policy.max_files:
                raise RepositoryStaticCollectionLimitError(
                    "collector exceeded the configured file-count bound"
                )
            if _ignored_path(relative_path):
                continue
            if len(candidates) >= context.policy.max_files:
                raise RepositoryStaticCollectionLimitError(
                    "collector exceeded the configured inspected-file bound"
                )
            candidates.append((relative_path, absolute_path, metadata.st_size))
    except RepositoryStaticCollectionError:
        raise
    except OSError as exc:
        raise RepositoryStaticCollectionPathError(
            "collector could not enumerate the checkout"
        ) from exc
    return sorted(candidates, key=lambda item: item[0].as_posix().casefold())


def _checkout_manifest(
    root: Path,
    *,
    policy: RepositoryStaticCollectorPolicy,
    deadline: float,
) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    try:
        for absolute_path in root.rglob("*"):
            _require_time_remaining(deadline)
            _safe_relative_path(
                absolute_path,
                root=root,
                policy=policy,
            )
            metadata = absolute_path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise RepositoryStaticCollectionPathError(
                    "collector checkout contains an unsupported link"
                )
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise RepositoryStaticCollectionPathError(
                    "collector checkout contains an unsupported file type"
                )
            file_count += 1
            total_bytes += metadata.st_size
    except RepositoryStaticCollectionError:
        raise
    except OSError as exc:
        raise RepositoryStaticCollectionPathError(
            "collector could not verify the checkout"
        ) from exc
    return file_count, total_bytes


def _safe_relative_path(
    absolute_path: Path,
    *,
    root: Path,
    policy: RepositoryStaticCollectorPolicy,
) -> PurePosixPath:
    try:
        relative = absolute_path.relative_to(root)
    except ValueError as exc:
        raise RepositoryStaticCollectionPathError(
            "collector path escaped the checkout boundary"
        ) from exc
    value = relative.as_posix()
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RepositoryStaticCollectionPathError(
            "collector checkout contains an unsafe path"
        )
    if len(value.encode("utf-8")) > policy.max_path_bytes:
        raise RepositoryStaticCollectionLimitError(
            "collector path exceeds the configured byte bound"
        )
    parsed = PurePosixPath(value)
    if len(parsed.parts) > policy.max_depth:
        raise RepositoryStaticCollectionLimitError(
            "collector path exceeds the configured depth bound"
        )
    if any(
        part in {"", ".", ".."} or part.casefold() == ".git"
        for part in parsed.parts
    ):
        raise RepositoryStaticCollectionPathError(
            "collector checkout contains an unsafe path"
        )
    return parsed


def _ignored_path(path: PurePosixPath) -> bool:
    return any(part.casefold() in _IGNORED_DIRECTORY_PARTS for part in path.parts[:-1])


def _read_bounded_file(
    path: Path,
    *,
    expected_size: int,
    root: Path,
    context: _CollectorContext,
) -> bytes:
    _require_time_remaining(context.deadline)
    if expected_size < 0 or expected_size > context.policy.max_file_bytes:
        raise RepositoryStaticCollectionLimitError(
            "collector file exceeds the configured byte bound"
        )
    try:
        with path.open("rb") as stream:
            raw = stream.read(context.policy.max_file_bytes + 1)
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise RepositoryStaticCollectionPathError(
            "collector could not read a bounded checkout file"
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not resolved.is_relative_to(root)
    ):
        raise RepositoryStaticCollectionPathError(
            "collector file crossed the checkout boundary"
        )
    if len(raw) > context.policy.max_file_bytes:
        raise RepositoryStaticCollectionLimitError(
            "collector file exceeded the configured byte bound"
        )
    if len(raw) != expected_size:
        raise RepositoryStaticCollectionPathError(
            "collector file changed during inspection"
        )
    return raw


def _file_classification(
    *,
    lower_path: str,
    basename: str,
    suffix: str,
) -> set[str]:
    classifications: set[str] = set()
    parts = PurePosixPath(lower_path).parts
    if basename in _MANIFEST_NAMES or basename in _LOCKFILE_NAMES:
        classifications.add("manifest")
    if _is_entrypoint_path(lower_path=lower_path, basename=basename):
        classifications.add("entrypoint")
    if basename in _INTERFACE_NAMES or suffix in {".graphql", ".proto"}:
        classifications.add("interface")
    if _is_deployment_path(lower_path=lower_path, basename=basename):
        classifications.add("deployment")
    if _is_test_or_ci_path(lower_path=lower_path, basename=basename, parts=parts):
        classifications.add("test_ci")
    if basename in _DOCUMENT_NAMES or (
        any(part in {"doc", "docs"} for part in parts[:-1])
        and suffix in {".md", ".rst", ".txt"}
    ):
        classifications.add("documentation")
    if _is_migration_path(lower_path=lower_path, suffix=suffix, parts=parts):
        classifications.add("migration")
    if suffix in _TEXT_SUFFIXES and suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        classifications.update({"entrypoint", "interface"})
    return classifications


def _is_entrypoint_path(*, lower_path: str, basename: str) -> bool:
    return (
        basename in _ENTRYPOINT_BASENAMES
        or lower_path.startswith("bin/")
        or lower_path.startswith("cmd/")
        or lower_path.startswith("src/pages/")
        or lower_path.startswith("app/")
        or lower_path.startswith("pages/")
    )


def _is_deployment_path(*, lower_path: str, basename: str) -> bool:
    return (
        basename in _DEPLOYMENT_NAMES
        or basename == "dockerfile"
        or basename.startswith("dockerfile.")
        or lower_path.startswith(("deploy/", "helm/", "k8s/", "kubernetes/", "terraform/"))
        or PurePosixPath(lower_path).suffix.casefold() == ".tf"
    )


def _is_test_or_ci_path(
    *,
    lower_path: str,
    basename: str,
    parts: tuple[str, ...],
) -> bool:
    return (
        lower_path in _CI_NAMES
        or lower_path.startswith(".github/workflows/")
        or any(part in _TEST_DIRECTORY_PARTS for part in parts[:-1])
        or basename.startswith("test_")
        or basename.endswith((".spec.js", ".spec.ts", ".test.js", ".test.ts"))
    )


def _is_migration_path(
    *,
    lower_path: str,
    suffix: str,
    parts: tuple[str, ...],
) -> bool:
    return (
        suffix == ".sql"
        and any(part in {"migration", "migrations"} for part in parts[:-1])
    ) or lower_path.startswith(("alembic/versions/", "db/migrations/", "migrations/"))


def _collect_manifest(
    *,
    relative_path: PurePosixPath,
    raw: bytes,
    collection: _MutableCollection,
    context: _CollectorContext,
) -> None:
    basename = relative_path.name.casefold()
    manifest_type = _manifest_type(basename)
    _append_fact(
        collection.manifests,
        category="manifest",
        fact_type=manifest_type,
        value=relative_path.name,
        relative_path=relative_path,
        evidence_kind=EvidenceKind.REPOSITORY_MANIFEST,
        context=context,
    )
    dependencies: list[tuple[str, str]] = []
    try:
        if basename == "package.json":
            payload = _load_json_object(raw)
            dependencies.extend(_package_json_dependencies(payload))
            dependencies.extend(_package_json_entrypoints(payload))
        elif basename == "pyproject.toml":
            payload = _load_toml_object(raw)
            dependencies.extend(_pyproject_dependencies(payload))
            dependencies.extend(_pyproject_entrypoints(payload))
        elif basename == "requirements.txt":
            dependencies.extend(_requirements_dependencies(_decode_text(raw)))
        elif basename == "go.mod":
            dependencies.extend(_go_mod_dependencies(_decode_text(raw)))
        elif basename == "cargo.toml":
            payload = _load_toml_object(raw)
            dependencies.extend(_cargo_dependencies(payload))
    except RepositoryStaticCollectionParseError:
        raise
    except (TypeError, ValueError) as exc:
        raise RepositoryStaticCollectionParseError(
            "recognized manifest failed strict bounded parsing"
        ) from exc

    unique_dependencies = {
        (fact_type, value)
        for fact_type, value in dependencies
        if fact_type != "manifest_entrypoint"
    }
    if len(unique_dependencies) > context.policy.max_dependencies_per_manifest:
        raise RepositoryStaticCollectionLimitError(
            "collector exceeded the configured dependency-per-manifest bound"
        )
    seen: set[tuple[str, str]] = set()
    for fact_type, value in dependencies:
        if (fact_type, value) in seen:
            continue
        seen.add((fact_type, value))
        target = (
            collection.entrypoints
            if fact_type == "manifest_entrypoint"
            else collection.dependencies
        )
        _append_fact(
            target,
            category="entrypoint" if fact_type == "manifest_entrypoint" else "dependency",
            fact_type=fact_type,
            value=value,
            relative_path=relative_path,
            evidence_kind=(
                EvidenceKind.REPOSITORY_MANIFEST
                if fact_type == "manifest_entrypoint"
                else EvidenceKind.REPOSITORY_DEPENDENCY
            ),
            context=context,
        )


def _manifest_type(basename: str) -> str:
    return {
        "cargo.lock": "rust_lockfile",
        "cargo.toml": "rust_manifest",
        "composer.json": "php_manifest",
        "composer.lock": "php_lockfile",
        "go.mod": "go_manifest",
        "package-lock.json": "node_lockfile",
        "package.json": "node_manifest",
        "pnpm-lock.yaml": "node_lockfile",
        "poetry.lock": "python_lockfile",
        "pom.xml": "java_manifest",
        "pyproject.toml": "python_manifest",
        "requirements.txt": "python_requirements",
        "uv.lock": "python_lockfile",
        "yarn.lock": "node_lockfile",
    }.get(basename, "manifest")


def _load_json_object(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepositoryStaticCollectionParseError(
            "recognized JSON manifest failed strict bounded parsing"
        ) from exc
    if not isinstance(payload, dict):
        raise RepositoryStaticCollectionParseError(
            "recognized JSON manifest must contain an object"
        )
    return payload


def _load_toml_object(raw: bytes) -> dict[str, Any]:
    try:
        payload = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RepositoryStaticCollectionParseError(
            "recognized TOML manifest failed strict bounded parsing"
        ) from exc
    return payload


def _package_json_dependencies(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    dependencies: set[str] = set()
    for section in _DEPENDENCY_SECTIONS:
        values = payload.get(section)
        if not isinstance(values, Mapping):
            continue
        for name in values:
            safe_name = _safe_identifier(name)
            if safe_name is not None:
                dependencies.add(safe_name)
    return [("package_dependency", value) for value in sorted(dependencies)]


def _package_json_entrypoints(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    values: set[str] = set()
    for key in ("main", "module", "browser"):
        safe = _safe_identifier(payload.get(key))
        if safe is not None:
            values.add(safe)
    bin_value = payload.get("bin")
    if isinstance(bin_value, str):
        safe = _safe_identifier(bin_value)
        if safe is not None:
            values.add(safe)
    elif isinstance(bin_value, Mapping):
        for value in bin_value.values():
            safe = _safe_identifier(value)
            if safe is not None:
                values.add(safe)
    return [("manifest_entrypoint", value) for value in sorted(values)]


def _pyproject_dependencies(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    dependencies: set[str] = set()
    project = payload.get("project")
    if isinstance(project, Mapping):
        raw_dependencies = project.get("dependencies")
        if isinstance(raw_dependencies, list):
            for value in raw_dependencies:
                dependency = _python_dependency_name(value)
                if dependency is not None:
                    dependencies.add(dependency)
        optional = project.get("optional-dependencies")
        if isinstance(optional, Mapping):
            for values in optional.values():
                if not isinstance(values, list):
                    continue
                for value in values:
                    dependency = _python_dependency_name(value)
                    if dependency is not None:
                        dependencies.add(dependency)
    poetry = _nested_mapping(payload, "tool", "poetry")
    if poetry is not None:
        values = poetry.get("dependencies")
        if isinstance(values, Mapping):
            for name in values:
                safe_name = _safe_identifier(name)
                if safe_name is not None and safe_name.casefold() != "python":
                    dependencies.add(safe_name)
    return [("package_dependency", value) for value in sorted(dependencies)]


def _pyproject_entrypoints(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    values: set[str] = set()
    project = payload.get("project")
    if isinstance(project, Mapping):
        for section in ("scripts", "gui-scripts"):
            scripts = project.get(section)
            if isinstance(scripts, Mapping):
                for target in scripts.values():
                    safe = _safe_identifier(target)
                    if safe is not None:
                        values.add(safe)
        entry_points = project.get("entry-points")
        if isinstance(entry_points, Mapping):
            for group in entry_points.values():
                if not isinstance(group, Mapping):
                    continue
                for target in group.values():
                    safe = _safe_identifier(target)
                    if safe is not None:
                        values.add(safe)
    poetry = _nested_mapping(payload, "tool", "poetry")
    if poetry is not None:
        scripts = poetry.get("scripts")
        if isinstance(scripts, Mapping):
            for target in scripts.values():
                safe = _safe_identifier(target)
                if safe is not None:
                    values.add(safe)
    return [("manifest_entrypoint", value) for value in sorted(values)]


def _cargo_dependencies(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    values: set[str] = set()
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        dependencies = payload.get(section)
        if not isinstance(dependencies, Mapping):
            continue
        for name in dependencies:
            safe = _safe_identifier(name)
            if safe is not None:
                values.add(safe)
    return [("package_dependency", value) for value in sorted(values)]


def _requirements_dependencies(text: str | None) -> list[tuple[str, str]]:
    if text is None:
        return []
    values: set[str] = set()
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith(("#", "-", ".")):
            continue
        name = re.split(r"[<>=!~;\s\[]", candidate, maxsplit=1)[0]
        safe = _safe_identifier(name)
        if safe is not None:
            values.add(safe)
    return [("package_dependency", value) for value in sorted(values)]


def _go_mod_dependencies(text: str | None) -> list[tuple[str, str]]:
    if text is None:
        return []
    values: set[str] = set()
    inside_require = False
    for line in text.splitlines():
        candidate = line.strip()
        if candidate.startswith("require ("):
            inside_require = True
            continue
        if inside_require and candidate == ")":
            inside_require = False
            continue
        if candidate.startswith("require "):
            candidate = candidate.removeprefix("require ").strip()
        elif not inside_require:
            continue
        name = candidate.split(maxsplit=1)[0] if candidate else ""
        safe = _safe_identifier(name)
        if safe is not None:
            values.add(safe)
    return [("package_dependency", value) for value in sorted(values)]


def _python_dependency_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    name = re.split(r"[<>=!~;\s\[]", value.strip(), maxsplit=1)[0]
    return _safe_identifier(name)


def _nested_mapping(
    payload: Mapping[str, Any],
    *keys: str,
) -> Mapping[str, Any] | None:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current if isinstance(current, Mapping) else None


def _collect_entrypoint(
    *,
    relative_path: PurePosixPath,
    text: str | None,
    collection: _MutableCollection,
    context: _CollectorContext,
) -> None:
    lower_path = relative_path.as_posix().casefold()
    basename = relative_path.name.casefold()
    detected = (
        basename in _ENTRYPOINT_BASENAMES
        or lower_path.startswith(("bin/", "cmd/", "src/pages/", "pages/"))
        or (text is not None and _PYTHON_MAIN.search(text) is not None)
    )
    if not detected:
        return
    _append_fact(
        collection.entrypoints,
        category="entrypoint",
        fact_type="source_entrypoint",
        value=relative_path.as_posix(),
        relative_path=relative_path,
        evidence_kind=EvidenceKind.REPOSITORY_SYMBOL,
        context=context,
    )


def _collect_interface(
    *,
    relative_path: PurePosixPath,
    text: str | None,
    collection: _MutableCollection,
    context: _CollectorContext,
) -> None:
    basename = relative_path.name.casefold()
    suffix = relative_path.suffix.casefold()
    if basename.startswith("openapi."):
        _append_fact(
            collection.interfaces,
            category="interface",
            fact_type="openapi_contract",
            value=relative_path.as_posix(),
            relative_path=relative_path,
            evidence_kind=EvidenceKind.REPOSITORY_FILE,
            context=context,
        )
    elif basename.startswith("asyncapi."):
        _append_fact(
            collection.interfaces,
            category="interface",
            fact_type="asyncapi_contract",
            value=relative_path.as_posix(),
            relative_path=relative_path,
            evidence_kind=EvidenceKind.REPOSITORY_FILE,
            context=context,
        )
    elif suffix == ".graphql":
        _append_fact(
            collection.interfaces,
            category="interface",
            fact_type="graphql_schema",
            value=relative_path.as_posix(),
            relative_path=relative_path,
            evidence_kind=EvidenceKind.REPOSITORY_FILE,
            context=context,
        )
    elif suffix == ".proto":
        _append_fact(
            collection.interfaces,
            category="interface",
            fact_type="protobuf_schema",
            value=relative_path.as_posix(),
            relative_path=relative_path,
            evidence_kind=EvidenceKind.REPOSITORY_FILE,
            context=context,
        )
    if text is None or suffix != ".py":
        return
    for route in sorted(set(_ROUTE_DECORATOR.findall(text))):
        safe_route = _safe_identifier(route)
        if safe_route is None:
            continue
        _append_fact(
            collection.interfaces,
            category="interface",
            fact_type="http_route",
            value=safe_route,
            relative_path=relative_path,
            evidence_kind=EvidenceKind.REPOSITORY_SYMBOL,
            context=context,
        )


def _collect_deployment(
    *,
    relative_path: PurePosixPath,
    collection: _MutableCollection,
    context: _CollectorContext,
) -> None:
    lower_path = relative_path.as_posix().casefold()
    basename = relative_path.name.casefold()
    if basename == "dockerfile" or basename.startswith("dockerfile."):
        fact_type = "container_build"
    elif relative_path.suffix.casefold() == ".tf" or lower_path.startswith("terraform/"):
        fact_type = "terraform_definition"
    elif lower_path.startswith("helm/") or "/templates/" in lower_path:
        fact_type = "helm_definition"
    elif lower_path.startswith(("k8s/", "kubernetes/")):
        fact_type = "kubernetes_definition"
    elif basename in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
        fact_type = "compose_definition"
    elif basename == "procfile":
        fact_type = "process_definition"
    else:
        fact_type = "deployment_definition"
    _append_fact(
        collection.deployment,
        category="deployment",
        fact_type=fact_type,
        value=relative_path.as_posix(),
        relative_path=relative_path,
        evidence_kind=EvidenceKind.REPOSITORY_DEPLOYMENT,
        context=context,
    )


def _collect_test_ci(
    *,
    relative_path: PurePosixPath,
    text: str | None,
    collection: _MutableCollection,
    context: _CollectorContext,
) -> None:
    lower_path = relative_path.as_posix().casefold()
    parts = tuple(part.casefold() for part in relative_path.parts)
    if lower_path.startswith(".github/workflows/") or lower_path in _CI_NAMES:
        fact_type = "ci_workflow"
        evidence_kind = EvidenceKind.REPOSITORY_WORKFLOW
    elif any(part in _TEST_DIRECTORY_PARTS for part in parts[:-1]) or (
        relative_path.name.casefold().startswith("test_")
    ):
        fact_type = "test_source"
        evidence_kind = EvidenceKind.REPOSITORY_FILE
    else:
        fact_type = "test_source"
        evidence_kind = EvidenceKind.REPOSITORY_FILE
    _append_fact(
        collection.tests_ci,
        category="test_ci",
        fact_type=fact_type,
        value=relative_path.as_posix(),
        relative_path=relative_path,
        evidence_kind=evidence_kind,
        context=context,
    )


def _collect_documentation(
    *,
    relative_path: PurePosixPath,
    text: str | None,
    collection: _MutableCollection,
    context: _CollectorContext,
) -> None:
    fact_type = (
        "architecture_document"
        if "architecture" in relative_path.name.casefold()
        else "documentation_file"
    )
    if text is not None and relative_path.suffix.casefold() == ".md":
        fact_type = (
            fact_type
            if _MARKDOWN_HEADING.search(text) is not None
            else "documentation_text"
        )
    _append_fact(
        collection.documentation,
        category="documentation",
        fact_type=fact_type,
        value=relative_path.as_posix(),
        relative_path=relative_path,
        evidence_kind=EvidenceKind.REPOSITORY_FILE,
        context=context,
    )


def _collect_migration(
    *,
    relative_path: PurePosixPath,
    text: str | None,
    collection: _MutableCollection,
    context: _CollectorContext,
) -> None:
    _append_fact(
        collection.migrations,
        category="migration",
        fact_type="migration_file",
        value=relative_path.as_posix(),
        relative_path=relative_path,
        evidence_kind=EvidenceKind.REPOSITORY_FILE,
        context=context,
    )
    if text is None:
        return
    for table in sorted(set(_SQL_TABLE.findall(text))):
        safe_table = _safe_identifier(table)
        if safe_table is None:
            continue
        _append_fact(
            collection.migrations,
            category="migration",
            fact_type="database_object",
            value=safe_table,
            relative_path=relative_path,
            evidence_kind=EvidenceKind.REPOSITORY_SYMBOL,
            context=context,
        )


def _append_fact(
    target: list[RepositoryStaticFactV1],
    *,
    category: Literal[
        "manifest",
        "entrypoint",
        "dependency",
        "interface",
        "deployment",
        "test_ci",
        "documentation",
        "migration",
    ],
    fact_type: str,
    value: str,
    relative_path: PurePosixPath,
    evidence_kind: EvidenceKind,
    context: _CollectorContext,
) -> None:
    safe_value = _safe_output_text(value, limit=context.policy.max_text_chars)
    if safe_value is None:
        return
    if len(target) >= context.policy.max_items_per_category:
        raise RepositoryStaticCollectionLimitError(
            f"collector exceeded the configured {category} output bound"
        )
    path = relative_path.as_posix()
    claim_key = _stable_key(f"{category}.{fact_type}.{path}.{safe_value}")
    target.append(
        RepositoryStaticFactV1(
            fact_id=claim_key,
            category=category,
            fact_type=fact_type,
            value=safe_value,
            path=path,
            evidence_ref=EvidenceRefV1(
                kind=evidence_kind,
                source=EvidenceSource.INTERNAL,
                ref=(
                    f"{context.repository_full_name}@"
                    f"{context.commit_sha}:{path}"
                ),
            ),
        )
    )


def _safe_identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _safe_output_text(value, limit=255, require_identifier=True)


def _safe_output_text(
    value: str,
    *,
    limit: int,
    require_identifier: bool = False,
) -> str | None:
    text = unicodedata.normalize("NFC", value).strip()
    if not text or len(text) > limit:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        return None
    if require_identifier and _SAFE_IDENTIFIER.fullmatch(text) is None:
        return None
    return text


def _stable_key(material: str) -> str:
    normalized = _SAFE_CLAIM_KEY.sub("-", material.casefold()).strip("-")
    if not normalized:
        normalized = "fact"
    digest = sha256(material.encode("utf-8")).hexdigest()[:16]
    prefix = normalized[:110].rstrip("-") or "fact"
    return f"{prefix}-{digest}"


def _decode_text(raw: bytes) -> str | None:
    if b"\0" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _sorted_unique(
    facts: list[RepositoryStaticFactV1],
) -> list[RepositoryStaticFactV1]:
    by_identity: dict[tuple[str, str, str, str], RepositoryStaticFactV1] = {}
    for fact in facts:
        key = (fact.category, fact.fact_type, fact.value, fact.path)
        by_identity[key] = fact
    return [
        by_identity[key]
        for key in sorted(
            by_identity,
            key=lambda item: tuple(value.casefold() for value in item),
        )
    ]


def _require_time_remaining(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise RepositoryStaticCollectionLimitError(
            "collector exceeded the configured timeout"
        )
