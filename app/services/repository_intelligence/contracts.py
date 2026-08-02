"""Strict, bounded Repository Intelligence v1 validation contracts.

This module defines the validation boundary only. It performs no persistence,
provider access, repository checkout, target-code execution, or LLM call.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from app.services.action_proposal_service import action_evidence_ref_matches_schema
from app.services.repository_intelligence.taxonomy import (
    AnalyzerClaimStatus,
    AuditLevel,
    CommitAlgorithm,
    EvidenceKind,
    EvidenceSource,
    FindingLifecycleStatus,
    FindingSeverity,
    HumanResolutionStatus,
    REPOSITORY_INTELLIGENCE_MAX_BYTES,
    REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
    REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    RelationshipType,
    RepositoryProvider,
    RepositoryResolutionStatus,
    RepositoryType,
    SYMMETRIC_RELATIONSHIP_TYPES,
    TargetStatus,
)


_LOWER_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_LOWER_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_STABLE_KEY = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_PROFILE = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_GITHUB_FULL_NAME = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254})$"
)

StrictShortText = Annotated[str, StringConstraints(min_length=1, max_length=255)]
StrictSummary = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
StrictDetail = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
StrictRef = Annotated[str, StringConstraints(min_length=1, max_length=500)]


class RepositoryIntelligenceContractError(ValueError):
    """A repository-intelligence payload is invalid or exceeds safe bounds."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _reject_unsafe_text(value: str, *, field_name: str) -> str:
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field_name} contains control characters")
    return value


def _unique_evidence_refs(
    refs: list[EvidenceRefV1],
    *,
    field_name: str,
) -> list[EvidenceRefV1]:
    seen: set[str] = set()
    for ref in refs:
        key = json.dumps(
            ref.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if key in seen:
            raise ValueError(f"{field_name} must not contain duplicate evidence")
        seen.add(key)
    return refs


class EvidenceRefV1(_StrictModel):
    """Repository Intelligence evidence compatible with ``evidence_ref.v1``."""

    kind: EvidenceKind
    source: EvidenceSource
    evidence_ref_id: UUID | None = None
    source_record_id: UUID | None = None
    record_id: UUID | None = None
    ref: StrictRef | None = None
    id: StrictRef | None = None
    url: Annotated[str, StringConstraints(min_length=1, max_length=1000)] | None = None

    @field_validator("ref", "id", "url")
    @classmethod
    def validate_text_selector(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _reject_unsafe_text(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_existing_evidence_contract(self) -> Self:
        material = self.model_dump(mode="json", exclude_none=True)
        if not action_evidence_ref_matches_schema(material):
            raise ValueError("evidence item must match evidence_ref.v1")
        return self


class AnalyzerHumanResolutionV1(_StrictModel):
    """Analyzer-visible resolution state; terminal human values are impossible."""

    status: Literal["pending"] = "pending"
    resolved_by_user_id: None = None
    resolved_at: None = None


class AnalysisTargetV1(_StrictModel):
    target_status: TargetStatus
    commit_algorithm: CommitAlgorithm | None
    commit_sha: Annotated[str, StringConstraints(min_length=40, max_length=40)] | None
    metadata_snapshot_id: StrictShortText | None = None

    @field_validator("commit_sha")
    @classmethod
    def validate_commit_sha_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        _reject_unsafe_text(value, field_name="commit_sha")
        if _LOWER_HEX_40.fullmatch(value) is None:
            raise ValueError("commit_sha must be a full lowercase SHA-1")
        return value

    @model_validator(mode="after")
    def validate_target_shape(self) -> Self:
        if self.target_status == TargetStatus.UNAVAILABLE:
            if self.commit_algorithm is not None or self.commit_sha is not None:
                raise ValueError(
                    "unavailable target must not claim a commit algorithm or SHA"
                )
            return self
        if (
            self.commit_algorithm != CommitAlgorithm.SHA1
            or self.commit_sha is None
        ):
            raise ValueError("exact target requires sha1 and a full commit SHA")
        return self


class RepositoryIdentityV1(_StrictModel):
    provider: Literal[RepositoryProvider.GITHUB]
    external_id: StrictShortText
    full_name: Annotated[str, StringConstraints(min_length=3, max_length=500)]
    default_branch: StrictShortText | None = None
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=1000)] | None = None

    @field_validator("external_id", "default_branch", "source_url")
    @classmethod
    def validate_identity_text(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _reject_unsafe_text(value, field_name=info.field_name)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        _reject_unsafe_text(value, field_name="full_name")
        if _GITHUB_FULL_NAME.fullmatch(value) is None:
            raise ValueError("full_name must be an owner/repository identity")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        evidence_probe = {
            "kind": "repository_metadata",
            "source": "github",
            "ref": "repository-identity",
            "url": value,
        }
        if not action_evidence_ref_matches_schema(evidence_probe):
            raise ValueError("source_url must be a safe HTTP(S) URL")
        return value


class RepositoryReferenceV1(_StrictModel):
    workspace_id: UUID
    repository_id: UUID | None = None
    provider: Literal[RepositoryProvider.GITHUB]
    external_id: StrictShortText
    full_name: Annotated[str, StringConstraints(min_length=3, max_length=500)]
    resolution_status: RepositoryResolutionStatus

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        return _reject_unsafe_text(value, field_name="external_id")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        _reject_unsafe_text(value, field_name="full_name")
        if _GITHUB_FULL_NAME.fullmatch(value) is None:
            raise ValueError("full_name must be an owner/repository identity")
        return value

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> Self:
        if (
            self.resolution_status == RepositoryResolutionStatus.CANONICAL
            and self.repository_id is None
        ):
            raise ValueError("canonical repository reference requires repository_id")
        if (
            self.resolution_status == RepositoryResolutionStatus.CANDIDATE
            and self.repository_id is not None
        ):
            raise ValueError("candidate repository reference must not claim repository_id")
        return self

    def stable_identity(self) -> tuple[str, str]:
        return (self.provider.value, self.external_id)

    def ordering_key(self) -> tuple[str, str, str]:
        return (self.provider.value, self.external_id, self.full_name.casefold())


class HumanResolutionV1(_StrictModel):
    """Human-only provenance, deliberately separate from analyzer status."""

    status: HumanResolutionStatus = HumanResolutionStatus.PENDING
    resolved_by_user_id: UUID | None = None
    resolved_at: datetime | None = None

    @model_validator(mode="after")
    def validate_provenance(self) -> Self:
        terminal = self.status in {
            HumanResolutionStatus.CONFIRMED,
            HumanResolutionStatus.REJECTED,
        }
        if terminal and (
            self.resolved_by_user_id is None or self.resolved_at is None
        ):
            raise ValueError("terminal human resolution requires actor and timestamp")
        if not terminal and (
            self.resolved_by_user_id is not None or self.resolved_at is not None
        ):
            raise ValueError("pending human resolution cannot carry terminal provenance")
        if self.resolved_at is not None and self.resolved_at.tzinfo is None:
            raise ValueError("human resolution timestamp must be timezone-aware")
        return self


class _EvidenceBackedAnalyzerItem(_StrictModel):
    workspace_id: UUID
    status: AnalyzerClaimStatus
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    evidence_refs: list[EvidenceRefV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
    )
    contradicting_evidence_refs: list[EvidenceRefV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
    )
    human_resolution: AnalyzerHumanResolutionV1 = Field(
        default_factory=AnalyzerHumanResolutionV1
    )
    reconciliation_status: Literal["current"] = "current"

    @field_validator("evidence_refs", "contradicting_evidence_refs")
    @classmethod
    def validate_unique_evidence(
        cls,
        value: list[EvidenceRefV1],
        info: Any,
    ) -> list[EvidenceRefV1]:
        return _unique_evidence_refs(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_analyzer_authority_and_evidence(self) -> Self:
        if (
            self.status != AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE
            and not self.evidence_refs
        ):
            raise ValueError("observed and inferred analyzer items require evidence")
        return self


class PurposeClaimV1(_EvidenceBackedAnalyzerItem):
    claim_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    summary: StrictSummary | None
    operational_summary: StrictDetail | None = None
    repository_type: RepositoryType

    @field_validator("claim_id")
    @classmethod
    def validate_claim_id(cls, value: str) -> str:
        _reject_unsafe_text(value, field_name="claim_id")
        if _STABLE_KEY.fullmatch(value) is None:
            raise ValueError("claim_id must be a stable lowercase key")
        return value

    @field_validator("summary", "operational_summary")
    @classmethod
    def validate_summary_text(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _reject_unsafe_text(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_purpose_shape(self) -> Self:
        if self.status == AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE:
            if self.repository_type != RepositoryType.UNKNOWN:
                raise ValueError(
                    "insufficient purpose evidence cannot assert a repository type"
                )
            return self
        if self.summary is None:
            raise ValueError("observed or inferred purpose requires a summary")
        return self


class RepositoryClaimV1(_EvidenceBackedAnalyzerItem):
    claim_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    claim_type: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    summary: StrictSummary | None
    details: list[StrictSummary] = Field(
        default_factory=list,
        max_length=20,
    )

    @field_validator("claim_id")
    @classmethod
    def validate_claim_id(cls, value: str) -> str:
        _reject_unsafe_text(value, field_name="claim_id")
        if _STABLE_KEY.fullmatch(value) is None:
            raise ValueError("claim_id must be a stable lowercase key")
        return value

    @field_validator("claim_type")
    @classmethod
    def validate_claim_type(cls, value: str) -> str:
        _reject_unsafe_text(value, field_name="claim_type")
        if _STABLE_KEY.fullmatch(value) is None:
            raise ValueError("claim_type must be a stable lowercase key")
        return value

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_unsafe_text(value, field_name="summary")

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("details must be unique")
        return [
            _reject_unsafe_text(item, field_name="details")
            for item in value
        ]

    @model_validator(mode="after")
    def validate_claim_shape(self) -> Self:
        if (
            self.status != AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE
            and self.summary is None
        ):
            raise ValueError("observed or inferred claim requires a summary")
        return self


class RepositoryRelationshipV1(_EvidenceBackedAnalyzerItem):
    relationship_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    from_repository: RepositoryReferenceV1
    to_repository: RepositoryReferenceV1
    relationship_type: RelationshipType
    summary: StrictSummary | None = None

    @field_validator("relationship_id")
    @classmethod
    def validate_relationship_id(cls, value: str) -> str:
        _reject_unsafe_text(value, field_name="relationship_id")
        if _STABLE_KEY.fullmatch(value) is None:
            raise ValueError("relationship_id must be a stable lowercase key")
        return value

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_unsafe_text(value, field_name="summary")

    @model_validator(mode="after")
    def validate_and_normalize_relationship(self) -> Self:
        workspaces = {
            self.workspace_id,
            self.from_repository.workspace_id,
            self.to_repository.workspace_id,
        }
        if len(workspaces) != 1:
            raise ValueError("repository relationship cannot cross workspaces")
        if (
            self.from_repository.stable_identity()
            == self.to_repository.stable_identity()
        ):
            raise ValueError("repository relationship cannot be a self-edge")
        if self.relationship_type in SYMMETRIC_RELATIONSHIP_TYPES and (
            self.from_repository.ordering_key()
            > self.to_repository.ordering_key()
        ):
            original_from = self.from_repository
            self.from_repository = self.to_repository
            self.to_repository = original_from
        return self

    def normalized_identity(self) -> tuple[str, str, str, str, str]:
        return (
            self.relationship_type.value,
            *self.from_repository.stable_identity(),
            *self.to_repository.stable_identity(),
        )


class RepositoryFindingV1(_EvidenceBackedAnalyzerItem):
    finding_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    rule_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    category: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    severity: FindingSeverity
    lifecycle_status: FindingLifecycleStatus
    title: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    summary: StrictDetail
    recommended_next_step: StrictSummary | None = None

    @field_validator("finding_id", "rule_id", "category")
    @classmethod
    def validate_stable_key(cls, value: str, info: Any) -> str:
        _reject_unsafe_text(value, field_name=info.field_name)
        if _STABLE_KEY.fullmatch(value) is None:
            raise ValueError(f"{info.field_name} must be a stable lowercase key")
        return value

    @field_validator("title", "summary", "recommended_next_step")
    @classmethod
    def validate_finding_text(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _reject_unsafe_text(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_analyzer_lifecycle(self) -> Self:
        allowed = {
            FindingLifecycleStatus.NEW,
            FindingLifecycleStatus.INSUFFICIENT_EVIDENCE,
        }
        if self.lifecycle_status not in allowed:
            raise ValueError("analyzer output cannot assert persisted finding lifecycle")
        if (
            self.status == AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE
            and self.lifecycle_status
            != FindingLifecycleStatus.INSUFFICIENT_EVIDENCE
        ):
            raise ValueError(
                "insufficient finding evidence requires insufficient lifecycle"
            )
        if (
            self.status != AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE
            and self.lifecycle_status != FindingLifecycleStatus.NEW
        ):
            raise ValueError("observed or inferred analyzer finding must be new")
        return self


class RepositoryUnknownV1(_StrictModel):
    unknown_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    workspace_id: UUID
    question: StrictSummary
    status: Literal[AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE] = (
        AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE
    )
    evidence_refs: list[EvidenceRefV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
    )

    @field_validator("unknown_id")
    @classmethod
    def validate_unknown_id(cls, value: str) -> str:
        _reject_unsafe_text(value, field_name="unknown_id")
        if _STABLE_KEY.fullmatch(value) is None:
            raise ValueError("unknown_id must be a stable lowercase key")
        return value

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return _reject_unsafe_text(value, field_name="question")

    @field_validator("evidence_refs")
    @classmethod
    def validate_unique_evidence(
        cls,
        value: list[EvidenceRefV1],
    ) -> list[EvidenceRefV1]:
        return _unique_evidence_refs(value, field_name="evidence_refs")


class RepositoryContradictionV1(_StrictModel):
    contradiction_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    workspace_id: UUID
    left_claim_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    right_claim_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    status: Literal[
        AnalyzerClaimStatus.OBSERVED,
        AnalyzerClaimStatus.INFERRED,
    ]
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    summary: StrictSummary
    evidence_refs: list[EvidenceRefV1] = Field(
        min_length=1,
        max_length=REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
    )

    @field_validator("contradiction_id", "left_claim_id", "right_claim_id")
    @classmethod
    def validate_stable_key(cls, value: str, info: Any) -> str:
        _reject_unsafe_text(value, field_name=info.field_name)
        if _STABLE_KEY.fullmatch(value) is None:
            raise ValueError(f"{info.field_name} must be a stable lowercase key")
        return value

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return _reject_unsafe_text(value, field_name="summary")

    @field_validator("evidence_refs")
    @classmethod
    def validate_unique_evidence(
        cls,
        value: list[EvidenceRefV1],
    ) -> list[EvidenceRefV1]:
        return _unique_evidence_refs(value, field_name="evidence_refs")

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        if self.left_claim_id == self.right_claim_id:
            raise ValueError("contradiction cannot reference one claim twice")
        return self

    def normalized_pair(self) -> tuple[str, str]:
        left, right = sorted((self.left_claim_id, self.right_claim_id))
        return left, right


class RepositoryAnalyzerResultV1(_StrictModel):
    schema_version: Literal["repository_analyzer_result.v1"]
    purpose: PurposeClaimV1
    responsibilities: list[RepositoryClaimV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    interfaces_provided: list[RepositoryClaimV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    dependencies_consumed: list[RepositoryClaimV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    deployment_units: list[RepositoryClaimV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    ownership_candidates: list[RepositoryClaimV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    relationship_candidates: list[RepositoryRelationshipV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    findings: list[RepositoryFindingV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    contradictions: list[RepositoryContradictionV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    unknowns: list[RepositoryUnknownV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    limitations: list[StrictDetail] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("limitations must be unique")
        return [
            _reject_unsafe_text(item, field_name="limitations")
            for item in value
        ]

    def claims(self) -> Iterable[PurposeClaimV1 | RepositoryClaimV1]:
        yield self.purpose
        yield from self.responsibilities
        yield from self.interfaces_provided
        yield from self.dependencies_consumed
        yield from self.deployment_units
        yield from self.ownership_candidates

    @model_validator(mode="after")
    def validate_identity_sets_and_contradictions(self) -> Self:
        claims = list(self.claims())
        claim_by_id = {claim.claim_id: claim for claim in claims}
        if len(claim_by_id) != len(claims):
            raise ValueError("claim IDs must be unique across analyzer sections")

        relationship_ids = [
            relationship.relationship_id
            for relationship in self.relationship_candidates
        ]
        if len(relationship_ids) != len(set(relationship_ids)):
            raise ValueError("relationship IDs must be unique")
        normalized_relationships = [
            relationship.normalized_identity()
            for relationship in self.relationship_candidates
        ]
        if len(normalized_relationships) != len(set(normalized_relationships)):
            raise ValueError("relationship candidates must not contain duplicates")

        finding_ids = [finding.finding_id for finding in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding IDs must be unique")

        unknown_ids = [unknown.unknown_id for unknown in self.unknowns]
        if len(unknown_ids) != len(set(unknown_ids)):
            raise ValueError("unknown IDs must be unique")

        contradiction_ids = [
            contradiction.contradiction_id
            for contradiction in self.contradictions
        ]
        if len(contradiction_ids) != len(set(contradiction_ids)):
            raise ValueError("contradiction IDs must be unique")
        contradiction_pairs = [
            contradiction.normalized_pair()
            for contradiction in self.contradictions
        ]
        if len(contradiction_pairs) != len(set(contradiction_pairs)):
            raise ValueError("contradiction claim pairs must be unique")

        for contradiction in self.contradictions:
            left = claim_by_id.get(contradiction.left_claim_id)
            right = claim_by_id.get(contradiction.right_claim_id)
            if left is None or right is None:
                raise ValueError("contradiction references an unknown claim")
            if not left.evidence_refs or not right.evidence_refs:
                raise ValueError(
                    "contradiction requires two preserved evidence-backed claims"
                )
        return self


class RepositoryIntelligenceV1(_StrictModel):
    """Trusted FounderOS envelope plus one bounded analyzer result."""

    schema_version: Literal["repository_intelligence.v1"]
    workspace_id: UUID
    repository_id: UUID
    repository: RepositoryIdentityV1
    audit_level: AuditLevel
    analysis_target: AnalysisTargetV1
    profile: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    policy_hash: Annotated[str, StringConstraints(min_length=64, max_length=64)]
    engine_version: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    result: RepositoryAnalyzerResultV1

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: str) -> str:
        _reject_unsafe_text(value, field_name="profile")
        if _PROFILE.fullmatch(value) is None:
            raise ValueError("profile must be a stable lowercase identifier")
        return value

    @field_validator("policy_hash")
    @classmethod
    def validate_policy_hash(cls, value: str) -> str:
        _reject_unsafe_text(value, field_name="policy_hash")
        if _LOWER_HEX_64.fullmatch(value) is None:
            raise ValueError("policy_hash must be a lowercase SHA-256")
        return value

    @field_validator("engine_version")
    @classmethod
    def validate_engine_version(cls, value: str) -> str:
        return _reject_unsafe_text(value, field_name="engine_version")

    @model_validator(mode="after")
    def validate_trusted_context(self) -> Self:
        if self.audit_level in {AuditLevel.L1, AuditLevel.L2} and (
            self.analysis_target.target_status != TargetStatus.EXACT
        ):
            raise ValueError("L1 and L2 require an exact commit target")

        scoped_items: list[Any] = [
            *self.result.claims(),
            *self.result.relationship_candidates,
            *self.result.findings,
            *self.result.contradictions,
            *self.result.unknowns,
        ]
        if any(item.workspace_id != self.workspace_id for item in scoped_items):
            raise ValueError("analyzer items must match the trusted workspace")
        for relationship in self.result.relationship_candidates:
            if relationship.from_repository.workspace_id != self.workspace_id:
                raise ValueError("relationship source must match trusted workspace")
            if relationship.to_repository.workspace_id != self.workspace_id:
                raise ValueError("relationship target must match trusted workspace")

        encoded = _serialized_contract(self)
        if len(encoded) > REPOSITORY_INTELLIGENCE_MAX_BYTES:
            raise ValueError(
                f"repository intelligence payload exceeds "
                f"{REPOSITORY_INTELLIGENCE_MAX_BYTES} bytes"
            )
        return self


def _serialized_contract(payload: RepositoryIntelligenceV1) -> bytes:
    try:
        return json.dumps(
            payload.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("repository intelligence payload is not strict JSON") from exc


def validate_repository_intelligence_json(
    raw_payload: str | bytes,
) -> RepositoryIntelligenceV1:
    """Validate raw JSON with a pre-parse byte cap and sanitized error boundary."""

    if isinstance(raw_payload, str):
        encoded = raw_payload.encode("utf-8")
    elif isinstance(raw_payload, bytes):
        encoded = raw_payload
    else:
        raise RepositoryIntelligenceContractError(
            "repository intelligence payload must be JSON text or bytes"
        )
    if len(encoded) > REPOSITORY_INTELLIGENCE_MAX_BYTES:
        raise RepositoryIntelligenceContractError(
            f"repository intelligence payload exceeds "
            f"{REPOSITORY_INTELLIGENCE_MAX_BYTES} bytes"
        )
    try:
        return RepositoryIntelligenceV1.model_validate_json(encoded)
    except ValidationError as exc:
        raise RepositoryIntelligenceContractError(
            "repository intelligence payload failed strict validation"
        ) from exc
