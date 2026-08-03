"""Strict, execution-free preparation for the first RI portfolio run.

This module validates a private operator-authored L0/L1 manifest and returns a
content-free plan receipt. It does not read target paths, call providers, enqueue
jobs, inspect a database, execute repository code, persist results, or write
artifacts.
"""

from __future__ import annotations

from enum import StrEnum
import json
from pathlib import PurePosixPath
import re
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.services.repository_intelligence.taxonomy import (
    AuditLevel,
    CommitAlgorithm,
    RepositoryProvider,
)


_PORTFOLIO_DRY_RUN_MAX_BYTES = 64 * 1024
_PORTFOLIO_DRY_RUN_MAX_REPOSITORIES = 50
_LOWER_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_LOWER_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_GITHUB_FULL_NAME = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254})$"
)
_STABLE_EXTERNAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_PROFILE = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_ENGINE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,79}$")
_LOCAL_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")

StrictName = Annotated[str, StringConstraints(min_length=1, max_length=500)]
StrictProfile = Annotated[str, StringConstraints(min_length=1, max_length=80)]
StrictHash = Annotated[str, StringConstraints(min_length=64, max_length=64)]


class RepositoryPortfolioDryRunError(ValueError):
    """A portfolio dry-run manifest is invalid or outside safe bounds."""


class RepositoryPortfolioSourceMode(StrEnum):
    PROVIDER_EXACT_SHA = "provider_exact_sha"
    OPERATOR_MANAGED_LOCAL_MIRROR = "operator_managed_local_mirror"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RepositoryPortfolioDryRunEntryV1(_StrictModel):
    repository_id: UUID
    provider: Literal[RepositoryProvider.GITHUB] = RepositoryProvider.GITHUB
    external_id: StrictName
    full_name: StrictName
    commit_algorithm: Literal[CommitAlgorithm.SHA1] = CommitAlgorithm.SHA1
    commit_sha: Annotated[
        str,
        StringConstraints(min_length=40, max_length=40),
    ]
    audit_levels: list[Literal[AuditLevel.L0, AuditLevel.L1]] = Field(
        min_length=1,
        max_length=2,
    )
    profile: StrictProfile
    policy_hash: StrictHash
    engine_version: StrictProfile
    source_mode: RepositoryPortfolioSourceMode
    local_mirror_ref: StrictName | None = None
    enabled: Literal[True] = True

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        if _STABLE_EXTERNAL_ID.fullmatch(value) is None:
            raise ValueError("portfolio external_id is invalid")
        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        if value != value.strip() or _GITHUB_FULL_NAME.fullmatch(value) is None:
            raise ValueError("portfolio full_name must be owner/repository")
        return value

    @field_validator("commit_sha")
    @classmethod
    def validate_commit_sha(cls, value: str) -> str:
        if _LOWER_HEX_40.fullmatch(value) is None:
            raise ValueError("portfolio commit_sha must be a full lowercase SHA-1")
        return value

    @field_validator("audit_levels")
    @classmethod
    def validate_audit_levels(
        cls,
        values: list[AuditLevel],
    ) -> list[AuditLevel]:
        expected = [AuditLevel.L0, AuditLevel.L1]
        normalized = sorted(values, key=lambda item: item.value)
        if normalized != expected:
            raise ValueError("portfolio dry run requires exact L0 and L1 levels")
        return expected

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: str) -> str:
        if _PROFILE.fullmatch(value) is None:
            raise ValueError("portfolio profile is invalid")
        return value

    @field_validator("policy_hash")
    @classmethod
    def validate_policy_hash(cls, value: str) -> str:
        if _LOWER_HEX_64.fullmatch(value) is None:
            raise ValueError("portfolio policy_hash must be lowercase SHA-256")
        return value

    @field_validator("engine_version")
    @classmethod
    def validate_engine_version(cls, value: str) -> str:
        if _ENGINE_VERSION.fullmatch(value) is None:
            raise ValueError("portfolio engine_version is invalid")
        return value

    @field_validator("local_mirror_ref")
    @classmethod
    def validate_local_mirror_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if (
            value != value.strip()
            or value.startswith("/")
            or "\\" in value
            or _LOCAL_REF.fullmatch(value) is None
        ):
            raise ValueError("local_mirror_ref must be an opaque relative reference")
        path = PurePosixPath(value)
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("local_mirror_ref must not traverse directories")
        return value

    @model_validator(mode="after")
    def validate_source_mode(self) -> Self:
        if (
            self.source_mode == RepositoryPortfolioSourceMode.OPERATOR_MANAGED_LOCAL_MIRROR
            and self.local_mirror_ref is None
        ):
            raise ValueError("operator-managed mirror requires local_mirror_ref")
        if (
            self.source_mode == RepositoryPortfolioSourceMode.PROVIDER_EXACT_SHA
            and self.local_mirror_ref is not None
        ):
            raise ValueError("provider source must not claim a local mirror ref")
        return self


class RepositoryPortfolioDryRunManifestV1(_StrictModel):
    schema_version: Literal["repository_portfolio_dry_run.v1"]
    workspace_id: UUID
    l2_enabled: Literal[False]
    provider_calls_authorized: Literal[False]
    target_reads_authorized: Literal[False]
    target_execution_authorized: Literal[False]
    persistence_authorized: Literal[False]
    repositories: list[RepositoryPortfolioDryRunEntryV1] = Field(
        min_length=1,
        max_length=_PORTFOLIO_DRY_RUN_MAX_REPOSITORIES,
    )

    @model_validator(mode="after")
    def validate_unique_identities(self) -> Self:
        if self.repositories != sorted(
            self.repositories,
            key=lambda item: item.full_name.casefold(),
        ):
            raise ValueError("portfolio repositories must be sorted by full_name")
        repository_ids = [item.repository_id for item in self.repositories]
        stable_ids = [(item.provider.value, item.external_id) for item in self.repositories]
        full_names = [item.full_name.casefold() for item in self.repositories]
        local_refs = [
            item.local_mirror_ref.casefold()
            for item in self.repositories
            if item.local_mirror_ref is not None
        ]
        if len(repository_ids) != len(set(repository_ids)):
            raise ValueError("portfolio repository IDs must be unique")
        if len(stable_ids) != len(set(stable_ids)):
            raise ValueError("portfolio stable identities must be unique")
        if len(full_names) != len(set(full_names)):
            raise ValueError("portfolio full names must be unique")
        if len(local_refs) != len(set(local_refs)):
            raise ValueError("portfolio local mirror refs must be unique")
        return self


class RepositoryPortfolioDryRunReceiptV1(_StrictModel):
    schema_version: Literal["repository_portfolio_dry_run_receipt.v1"]
    status: Literal["ready_for_separate_run_approval"]
    repository_count: int = Field(ge=1, le=_PORTFOLIO_DRY_RUN_MAX_REPOSITORIES)
    l0_repository_count: int = Field(ge=1, le=_PORTFOLIO_DRY_RUN_MAX_REPOSITORIES)
    l1_repository_count: int = Field(ge=1, le=_PORTFOLIO_DRY_RUN_MAX_REPOSITORIES)
    exact_sha_count: int = Field(ge=1, le=_PORTFOLIO_DRY_RUN_MAX_REPOSITORIES)
    provider_source_count: int = Field(ge=0, le=_PORTFOLIO_DRY_RUN_MAX_REPOSITORIES)
    local_mirror_source_count: int = Field(ge=0, le=_PORTFOLIO_DRY_RUN_MAX_REPOSITORIES)
    l2_enabled: Literal[False]
    provider_calls_performed: Literal[0]
    target_paths_opened: Literal[0]
    target_repositories_read: Literal[0]
    target_repositories_cloned: Literal[0]
    target_code_executed: Literal[0]
    analysis_jobs_enqueued: Literal[0]
    persistence_writes: Literal[0]
    external_writes: Literal[0]
    output_contract: Literal["central_audit_workspace_only"]
    evidence_contract: Literal["schema_and_evidence_valid_only"]
    failure_isolation: Literal["one_repository_one_job_continue_others"]
    artifact_retention_days: Literal[30]
    checkout_retention: Literal["deleted_on_exit"]
    rollback: Literal["no_runtime_mutation_in_dry_run"]
    restart: Literal["resume_by_exact_repository_sha_profile_policy_engine"]
    next_gate: Literal["explicit_founder_approval_required"]

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (
            self.l0_repository_count != self.repository_count
            or self.l1_repository_count != self.repository_count
            or self.exact_sha_count != self.repository_count
            or self.provider_source_count + self.local_mirror_source_count != self.repository_count
        ):
            raise ValueError("portfolio dry-run receipt counts are inconsistent")
        return self

    def deterministic_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


def prepare_repository_portfolio_dry_run(
    manifest: RepositoryPortfolioDryRunManifestV1,
) -> RepositoryPortfolioDryRunReceiptV1:
    """Validate a private L0/L1 manifest without starting any real read."""

    repository_count = len(manifest.repositories)
    provider_count = sum(
        item.source_mode == RepositoryPortfolioSourceMode.PROVIDER_EXACT_SHA
        for item in manifest.repositories
    )
    local_count = repository_count - provider_count
    return RepositoryPortfolioDryRunReceiptV1(
        schema_version="repository_portfolio_dry_run_receipt.v1",
        status="ready_for_separate_run_approval",
        repository_count=repository_count,
        l0_repository_count=repository_count,
        l1_repository_count=repository_count,
        exact_sha_count=repository_count,
        provider_source_count=provider_count,
        local_mirror_source_count=local_count,
        l2_enabled=False,
        provider_calls_performed=0,
        target_paths_opened=0,
        target_repositories_read=0,
        target_repositories_cloned=0,
        target_code_executed=0,
        analysis_jobs_enqueued=0,
        persistence_writes=0,
        external_writes=0,
        output_contract="central_audit_workspace_only",
        evidence_contract="schema_and_evidence_valid_only",
        failure_isolation="one_repository_one_job_continue_others",
        artifact_retention_days=30,
        checkout_retention="deleted_on_exit",
        rollback="no_runtime_mutation_in_dry_run",
        restart="resume_by_exact_repository_sha_profile_policy_engine",
        next_gate="explicit_founder_approval_required",
    )


def validate_repository_portfolio_dry_run_json(
    raw_payload: str | bytes,
) -> RepositoryPortfolioDryRunManifestV1:
    """Validate bounded raw JSON without emitting private manifest contents."""

    if isinstance(raw_payload, str):
        encoded = raw_payload.encode("utf-8")
    elif isinstance(raw_payload, bytes):
        encoded = raw_payload
    else:
        raise RepositoryPortfolioDryRunError("portfolio dry-run payload must be JSON text")
    if len(encoded) > _PORTFOLIO_DRY_RUN_MAX_BYTES:
        raise RepositoryPortfolioDryRunError(
            "portfolio dry-run payload exceeds the configured byte bound"
        )
    try:
        parsed = json.loads(encoded)
        if not isinstance(parsed, dict):
            raise ValueError("portfolio dry-run payload must be a JSON object")
        return RepositoryPortfolioDryRunManifestV1.model_validate_json(encoded)
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise RepositoryPortfolioDryRunError(
            "portfolio dry-run payload failed strict validation"
        ) from exc
