"""Bounded relationship candidates and graph validation for RI-005.

This module consumes only strict RI-004 static collections plus a trusted
synthetic portfolio manifest. It performs no repository read, target execution,
provider call, persistence, migration, UI operation, or LLM call.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
import json
import re
from hashlib import sha256
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.services.repository_intelligence.collectors import (
    RepositoryStaticCollectionV1,
)
from app.services.repository_intelligence.contracts import (
    EvidenceRefV1,
    RepositoryReferenceV1,
    RepositoryRelationshipV1,
)
from app.services.repository_intelligence.taxonomy import (
    AnalyzerClaimStatus,
    RELATIONSHIP_INVERSE_VIEW,
    REPOSITORY_INTELLIGENCE_MAX_BYTES,
    REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
    REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    RelationshipType,
    RepositoryProvider,
    RepositoryResolutionStatus,
    SYMMETRIC_RELATIONSHIP_TYPES,
)


_GITHUB_FULL_NAME = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254})$"
)
_STABLE_EXTERNAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_STABLE_KEY = re.compile(r"[^a-z0-9]+")
_RELATIONSHIP_FACT_TYPES = frozenset(
    {
        "internal_package_dependency",
        "api_call_target",
        "event_consumer",
        "deployed_repository",
        "container_image_dependency",
        "generated_client_target",
        "tested_repository",
        "documented_repository",
        "shared_schema_target",
        "shared_database_target",
        "migration_target",
    }
)


class RepositoryRelationshipError(RuntimeError):
    """Sanitized RI-005 relationship failure."""


class RepositoryRelationshipValidationError(RepositoryRelationshipError):
    """The trusted manifest or strict relationship input is invalid."""


class RepositoryRelationshipLimitError(RepositoryRelationshipError):
    """The relationship or graph result exceeded an explicit bound."""


StrictRelationshipText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255),
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepositoryRelationshipPolicy(_StrictModel):
    max_repositories: int = Field(
        default=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
        ge=1,
        le=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    max_relationships: int = Field(
        default=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
        ge=1,
        le=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    max_evidence_refs_per_relationship: int = Field(
        default=REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
        ge=1,
        le=REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
    )
    max_findings: int = Field(
        default=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
        ge=1,
        le=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    max_cycles: int = Field(
        default=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
        ge=1,
        le=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    max_cycle_depth: int = Field(default=16, ge=2, le=50)
    max_output_bytes: int = Field(
        default=REPOSITORY_INTELLIGENCE_MAX_BYTES,
        ge=1024,
        le=REPOSITORY_INTELLIGENCE_MAX_BYTES,
    )


class RepositoryPortfolioEntryV1(_StrictModel):
    workspace_id: UUID
    repository_id: UUID
    provider: Literal[RepositoryProvider.GITHUB] = RepositoryProvider.GITHUB
    external_id: StrictRelationshipText
    full_name: Annotated[str, StringConstraints(min_length=3, max_length=500)]
    package_names: list[StrictRelationshipText] = Field(
        default_factory=list,
        max_length=20,
    )
    api_contracts: list[StrictRelationshipText] = Field(
        default_factory=list,
        max_length=20,
    )
    event_contracts: list[StrictRelationshipText] = Field(
        default_factory=list,
        max_length=20,
    )
    image_names: list[StrictRelationshipText] = Field(
        default_factory=list,
        max_length=20,
    )
    deployment_targets: list[StrictRelationshipText] = Field(
        default_factory=list,
        max_length=20,
    )
    test_targets: list[StrictRelationshipText] = Field(
        default_factory=list,
        max_length=20,
    )
    document_targets: list[StrictRelationshipText] = Field(
        default_factory=list,
        max_length=20,
    )

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        if _STABLE_EXTERNAL_ID.fullmatch(value) is None:
            raise ValueError("external_id must be a stable provider identity")
        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        if value != value.strip() or _GITHUB_FULL_NAME.fullmatch(value) is None:
            raise ValueError("full_name must be a safe owner/repository identity")
        return value

    @field_validator(
        "package_names",
        "api_contracts",
        "event_contracts",
        "image_names",
        "deployment_targets",
        "test_targets",
        "document_targets",
    )
    @classmethod
    def validate_unique_aliases(cls, values: list[str]) -> list[str]:
        normalized = [_normalize_selector(value) for value in values]
        if any(value is None for value in normalized):
            raise ValueError("portfolio selectors must be safe stable text")
        material = [value for value in normalized if value is not None]
        if len(material) != len(set(material)):
            raise ValueError("portfolio selectors must be unique")
        return sorted(values, key=str.casefold)

    def reference(self) -> RepositoryReferenceV1:
        return RepositoryReferenceV1(
            workspace_id=self.workspace_id,
            repository_id=self.repository_id,
            provider=self.provider,
            external_id=self.external_id,
            full_name=self.full_name,
            resolution_status=RepositoryResolutionStatus.CANONICAL,
        )


class RepositoryPortfolioV1(_StrictModel):
    schema_version: Literal["repository_portfolio.v1"]
    workspace_id: UUID
    repositories: list[RepositoryPortfolioEntryV1] = Field(
        min_length=1,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )

    @model_validator(mode="after")
    def validate_identity_sets(self) -> Self:
        if any(
            repository.workspace_id != self.workspace_id
            for repository in self.repositories
        ):
            raise ValueError("portfolio repositories must match the workspace")
        repository_ids = [
            repository.repository_id for repository in self.repositories
        ]
        stable_identities = [
            (repository.provider.value, repository.external_id)
            for repository in self.repositories
        ]
        full_names = [
            repository.full_name.casefold()
            for repository in self.repositories
        ]
        if len(repository_ids) != len(set(repository_ids)):
            raise ValueError("portfolio repository IDs must be unique")
        if len(stable_identities) != len(set(stable_identities)):
            raise ValueError("portfolio stable identities must be unique")
        if len(full_names) != len(set(full_names)):
            raise ValueError("portfolio full names must be unique")
        _selector_index(self.repositories)
        return self


class RepositoryRelationshipSignalV1(_StrictModel):
    workspace_id: UUID
    from_repository_id: UUID
    relationship_type: RelationshipType
    target_selector: StrictRelationshipText
    evidence_refs: list[EvidenceRefV1] = Field(
        min_length=1,
        max_length=REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
    )
    source_status: Literal[
        AnalyzerClaimStatus.OBSERVED,
        AnalyzerClaimStatus.INFERRED,
    ] = AnalyzerClaimStatus.OBSERVED

    @field_validator("target_selector")
    @classmethod
    def validate_selector(cls, value: str) -> str:
        if _normalize_selector(value) is None:
            raise ValueError("target_selector must be safe stable text")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def validate_unique_evidence(
        cls,
        evidence_refs: list[EvidenceRefV1],
    ) -> list[EvidenceRefV1]:
        keys = [
            json.dumps(
                evidence.model_dump(mode="json", exclude_none=True),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            for evidence in evidence_refs
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("relationship signal evidence must be unique")
        return evidence_refs


class RepositoryGraphFindingV1(_StrictModel):
    finding_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    finding_type: Literal[
        "cycle",
        "orphan",
        "unresolved_target",
        "contradiction",
    ]
    repository_ids: list[UUID] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    relationship_ids: list[
        Annotated[str, StringConstraints(min_length=1, max_length=128)]
    ] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    summary: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    evidence_refs: list[EvidenceRefV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_EVIDENCE_REFS,
    )

    @field_validator("finding_id", "summary")
    @classmethod
    def validate_safe_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("graph finding text must not contain whitespace padding")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("graph finding text contains control characters")
        return value


class RepositoryRelationshipAnalysisV1(_StrictModel):
    schema_version: Literal["repository_relationship_analysis.v1"]
    workspace_id: UUID
    relationships: list[RepositoryRelationshipV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    inverse_views: list[StrictRelationshipText] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    cycles: list[list[UUID]] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    orphan_repository_ids: list[UUID] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    unresolved_relationship_ids: list[
        Annotated[str, StringConstraints(min_length=1, max_length=128)]
    ] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    findings: list[RepositoryGraphFindingV1] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )
    limitations: list[
        Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    ] = Field(
        default_factory=list,
        max_length=REPOSITORY_INTELLIGENCE_MAX_ITEMS,
    )

    @model_validator(mode="after")
    def validate_identity_sets(self) -> Self:
        if any(
            relationship.workspace_id != self.workspace_id
            for relationship in self.relationships
        ):
            raise ValueError("relationships must match the analysis workspace")
        relationship_ids = [
            relationship.relationship_id for relationship in self.relationships
        ]
        normalized = [
            relationship.normalized_identity()
            for relationship in self.relationships
        ]
        if len(relationship_ids) != len(set(relationship_ids)):
            raise ValueError("relationship IDs must be unique")
        if len(normalized) != len(set(normalized)):
            raise ValueError("normalized relationships must be unique")
        known_ids = set(relationship_ids)
        if any(
            relationship_id not in known_ids
            for relationship_id in self.unresolved_relationship_ids
        ):
            raise ValueError("unresolved relationship ID is unknown")
        finding_ids = [finding.finding_id for finding in self.findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("graph finding IDs must be unique")
        relationship_count = len(self.relationships)
        if len(self.inverse_views) != relationship_count:
            raise ValueError("each relationship requires one inverse view")
        if len(self.cycles) != len(
            {
                tuple(sorted(cycle, key=lambda item: item.hex))
                for cycle in self.cycles
            }
        ):
            raise ValueError("cycles must be unique")
        if len(self.orphan_repository_ids) != len(
            set(self.orphan_repository_ids)
        ):
            raise ValueError("orphan repository IDs must be unique")
        if len(self.unresolved_relationship_ids) != len(
            set(self.unresolved_relationship_ids)
        ):
            raise ValueError("unresolved relationship IDs must be unique")
        return self

    def deterministic_json(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


def relationship_signals_from_static_collection(
    collection: RepositoryStaticCollectionV1,
) -> list[RepositoryRelationshipSignalV1]:
    """Project only explicit RI-004 relationship-bearing fact types."""

    mapping: dict[str, RelationshipType] = {
        "internal_package_dependency": RelationshipType.IMPORTS_PACKAGE_FROM,
        "api_call_target": RelationshipType.CALLS_API_OF,
        "event_consumer": RelationshipType.CONSUMES_EVENT_FROM,
        "deployed_repository": RelationshipType.DEPLOYED_BY,
        "container_image_dependency": RelationshipType.USES_IMAGE_FROM,
        "generated_client_target": RelationshipType.GENERATES_CLIENT_FOR,
        "tested_repository": RelationshipType.TESTS,
        "documented_repository": RelationshipType.DOCUMENTS,
        "shared_schema_target": RelationshipType.SHARES_SCHEMA_WITH,
        "shared_database_target": RelationshipType.SHARES_DATABASE_WITH,
        "migration_target": RelationshipType.OWNS_MIGRATIONS_FOR,
    }
    signals = [
        RepositoryRelationshipSignalV1(
            workspace_id=collection.workspace_id,
            from_repository_id=collection.repository_id,
            relationship_type=mapping[fact.fact_type],
            target_selector=fact.value,
            evidence_refs=[fact.evidence_ref],
        )
        for fact in collection.facts()
        if fact.fact_type in mapping
    ]
    return sorted(
        signals,
        key=lambda signal: (
            signal.from_repository_id.hex,
            signal.relationship_type.value,
            signal.target_selector.casefold(),
        ),
    )


def build_repository_relationship_analysis(
    *,
    portfolio: RepositoryPortfolioV1,
    collections: Iterable[RepositoryStaticCollectionV1] = (),
    signals: Iterable[RepositoryRelationshipSignalV1] = (),
    policy: RepositoryRelationshipPolicy | None = None,
) -> RepositoryRelationshipAnalysisV1:
    """Resolve bounded directional candidates and validate the portfolio graph."""

    selected_policy = policy or RepositoryRelationshipPolicy()
    if len(portfolio.repositories) > selected_policy.max_repositories:
        raise RepositoryRelationshipLimitError(
            "relationship portfolio exceeds the configured repository bound"
        )
    repository_by_id = {
        repository.repository_id: repository
        for repository in portfolio.repositories
    }
    collection_by_id: dict[UUID, RepositoryStaticCollectionV1] = {}
    projected_signals: list[RepositoryRelationshipSignalV1] = []
    for collection in collections:
        if collection.workspace_id != portfolio.workspace_id:
            raise RepositoryRelationshipValidationError(
                "static collection cannot cross portfolio workspaces"
            )
        if collection.repository_id not in repository_by_id:
            raise RepositoryRelationshipValidationError(
                "static collection repository is absent from the portfolio"
            )
        if collection.repository_id in collection_by_id:
            raise RepositoryRelationshipValidationError(
                "portfolio accepts one static collection per repository"
            )
        collection_by_id[collection.repository_id] = collection
        projected_signals.extend(
            relationship_signals_from_static_collection(collection)
        )
    projected_signals.extend(signals)
    if len(projected_signals) > (
        selected_policy.max_relationships
        * selected_policy.max_evidence_refs_per_relationship
    ):
        raise RepositoryRelationshipLimitError(
            "relationship signals exceed the configured input bound"
        )
    try:
        indexes = _selector_index(portfolio.repositories)
    except ValueError as exc:
        raise RepositoryRelationshipValidationError(
            "portfolio relationship selectors failed strict validation"
        ) from exc
    relationships = _resolve_signals(
        workspace_id=portfolio.workspace_id,
        repository_by_id=repository_by_id,
        selector_indexes=indexes,
        signals=projected_signals,
        policy=selected_policy,
    )
    cycles = _find_cycles(
        repository_ids=set(repository_by_id),
        relationships=relationships,
        policy=selected_policy,
    )
    connected_repository_ids = {
        repository_id
        for relationship in relationships
        for repository_id in (
            relationship.from_repository.repository_id,
            relationship.to_repository.repository_id,
        )
        if repository_id is not None
    }
    orphan_repository_ids = sorted(
        set(repository_by_id) - connected_repository_ids,
        key=lambda repository_id: repository_id.hex,
    )
    unresolved = sorted(
        relationship.relationship_id
        for relationship in relationships
        if relationship.to_repository.resolution_status
        == RepositoryResolutionStatus.CANDIDATE
    )
    findings = _graph_findings(
        relationships=relationships,
        cycles=cycles,
        orphan_repository_ids=orphan_repository_ids,
        unresolved_relationship_ids=unresolved,
        policy=selected_policy,
    )
    result = RepositoryRelationshipAnalysisV1(
        schema_version="repository_relationship_analysis.v1",
        workspace_id=portfolio.workspace_id,
        relationships=relationships,
        inverse_views=[
            _inverse_view(relationship)
            for relationship in relationships
        ],
        cycles=cycles,
        orphan_repository_ids=orphan_repository_ids,
        unresolved_relationship_ids=unresolved,
        findings=findings,
        limitations=[
            "Relationship candidates use only trusted synthetic portfolio metadata and RI-004 facts.",
            "Name similarity alone never creates a relationship.",
            "Observed and inferred candidates remain pending human confirmation.",
            "Graph validation performs no repository read, target execution, persistence, provider or LLM call.",
        ],
    )
    encoded = result.deterministic_json()
    if len(encoded) > selected_policy.max_output_bytes:
        raise RepositoryRelationshipLimitError(
            "relationship analysis exceeds the configured output byte bound"
        )
    return validate_repository_relationship_analysis_json(encoded)


def validate_repository_relationship_analysis_json(
    raw_payload: str | bytes,
) -> RepositoryRelationshipAnalysisV1:
    if isinstance(raw_payload, str):
        encoded = raw_payload.encode("utf-8")
    elif isinstance(raw_payload, bytes):
        encoded = raw_payload
    else:
        raise RepositoryRelationshipValidationError(
            "relationship payload must be JSON text or bytes"
        )
    if len(encoded) > REPOSITORY_INTELLIGENCE_MAX_BYTES:
        raise RepositoryRelationshipLimitError(
            "relationship payload exceeds the configured byte bound"
        )
    try:
        return RepositoryRelationshipAnalysisV1.model_validate_json(encoded)
    except (TypeError, ValueError) as exc:
        raise RepositoryRelationshipValidationError(
            "relationship payload failed strict validation"
        ) from exc


def _selector_index(
    repositories: Iterable[RepositoryPortfolioEntryV1],
) -> dict[RelationshipType, dict[str, RepositoryPortfolioEntryV1]]:
    indexes: dict[
        RelationshipType,
        dict[str, RepositoryPortfolioEntryV1],
    ] = {
        relationship_type: {}
        for relationship_type in RelationshipType
    }
    for repository in repositories:
        selector_sets: dict[RelationshipType, Iterable[str]] = {
            RelationshipType.IMPORTS_PACKAGE_FROM: repository.package_names,
            RelationshipType.CALLS_API_OF: repository.api_contracts,
            RelationshipType.CONSUMES_EVENT_FROM: repository.event_contracts,
            RelationshipType.USES_IMAGE_FROM: repository.image_names,
            RelationshipType.DEPLOYED_BY: repository.deployment_targets,
            RelationshipType.TESTS: repository.test_targets,
            RelationshipType.DOCUMENTS: repository.document_targets,
            RelationshipType.GENERATES_CLIENT_FOR: repository.api_contracts,
            RelationshipType.SHARES_SCHEMA_WITH: repository.api_contracts,
            RelationshipType.SHARES_DATABASE_WITH: (),
            RelationshipType.OWNS_MIGRATIONS_FOR: repository.full_name,
        }
        for relationship_type, selectors in selector_sets.items():
            iterable = [selectors] if isinstance(selectors, str) else selectors
            for selector in iterable:
                normalized = _normalize_selector(selector)
                if normalized is None:
                    raise ValueError("portfolio contains an invalid selector")
                existing = indexes[relationship_type].get(normalized)
                if existing is not None and (
                    existing.repository_id != repository.repository_id
                ):
                    raise ValueError(
                        "portfolio relationship selectors must resolve uniquely"
                    )
                indexes[relationship_type][normalized] = repository
        for relationship_type in RelationshipType:
            for selector in (
                repository.external_id,
                repository.full_name,
            ):
                normalized = _normalize_selector(selector)
                if normalized is None:
                    continue
                existing = indexes[relationship_type].get(normalized)
                if existing is not None and (
                    existing.repository_id != repository.repository_id
                ):
                    raise ValueError(
                        "portfolio stable selectors must resolve uniquely"
                    )
                indexes[relationship_type][normalized] = repository
    return indexes


def _resolve_signals(
    *,
    workspace_id: UUID,
    repository_by_id: dict[UUID, RepositoryPortfolioEntryV1],
    selector_indexes: dict[
        RelationshipType,
        dict[str, RepositoryPortfolioEntryV1],
    ],
    signals: Iterable[RepositoryRelationshipSignalV1],
    policy: RepositoryRelationshipPolicy,
) -> list[RepositoryRelationshipV1]:
    grouped: dict[
        tuple[UUID, RelationshipType, str],
        list[RepositoryRelationshipSignalV1],
    ] = defaultdict(list)
    for signal in signals:
        if signal.workspace_id != workspace_id:
            raise RepositoryRelationshipValidationError(
                "relationship signal cannot cross portfolio workspaces"
            )
        if signal.from_repository_id not in repository_by_id:
            raise RepositoryRelationshipValidationError(
                "relationship signal source is absent from the portfolio"
            )
        selector = _normalize_selector(signal.target_selector)
        if selector is None:
            raise RepositoryRelationshipValidationError(
                "relationship signal target selector is invalid"
            )
        grouped[(signal.from_repository_id, signal.relationship_type, selector)].append(
            signal
        )

    relationships_by_identity: dict[
        tuple[str, str, str, str, str],
        RepositoryRelationshipV1,
    ] = {}
    for key in sorted(
        grouped,
        key=lambda item: (item[0].hex, item[1].value, item[2]),
    ):
        from_repository_id, relationship_type, selector = key
        group = grouped[key]
        from_entry = repository_by_id[from_repository_id]
        target_entry = selector_indexes[relationship_type].get(selector)
        if target_entry is not None and (
            target_entry.repository_id == from_repository_id
        ):
            raise RepositoryRelationshipValidationError(
                "relationship signal resolved to a self-edge"
            )
        to_reference = (
            target_entry.reference()
            if target_entry is not None
            else _candidate_reference(
                workspace_id=workspace_id,
                relationship_type=relationship_type,
                selector=selector,
            )
        )
        evidence = _unique_evidence(
            evidence
            for signal in group
            for evidence in signal.evidence_refs
        )
        if len(evidence) > policy.max_evidence_refs_per_relationship:
            raise RepositoryRelationshipLimitError(
                "relationship evidence exceeds the configured bound"
            )
        status = (
            AnalyzerClaimStatus.OBSERVED
            if any(
                signal.source_status == AnalyzerClaimStatus.OBSERVED
                for signal in group
            )
            else AnalyzerClaimStatus.INFERRED
        )
        confidence = _confidence(
            status=status,
            evidence_count=len(evidence),
            resolved=target_entry is not None,
        )
        relationship = RepositoryRelationshipV1(
            workspace_id=workspace_id,
            status=status,
            confidence=confidence,
            evidence_refs=evidence,
            relationship_id=_relationship_id(
                from_entry=from_entry,
                relationship_type=relationship_type,
                target_entry=target_entry,
                selector=selector,
            ),
            from_repository=from_entry.reference(),
            to_repository=to_reference,
            relationship_type=relationship_type,
            summary=_relationship_summary(
                from_entry=from_entry,
                relationship_type=relationship_type,
                target_entry=target_entry,
                selector=selector,
                status=status,
            ),
        )
        normalized = relationship.normalized_identity()
        existing = relationships_by_identity.get(normalized)
        if existing is not None:
            relationships_by_identity[normalized] = _merge_relationships(
                existing,
                relationship,
                policy=policy,
            )
            continue
        relationships_by_identity[normalized] = relationship
        if len(relationships_by_identity) > policy.max_relationships:
            raise RepositoryRelationshipLimitError(
                "relationship analysis exceeds the configured edge bound"
            )
    relationships = list(relationships_by_identity.values())
    _reject_directional_contradictions(relationships)
    return sorted(
        relationships,
        key=lambda relationship: (
            relationship.from_repository.ordering_key(),
            relationship.relationship_type.value,
            relationship.to_repository.ordering_key(),
        ),
    )


def _merge_relationships(
    left: RepositoryRelationshipV1,
    right: RepositoryRelationshipV1,
    *,
    policy: RepositoryRelationshipPolicy,
) -> RepositoryRelationshipV1:
    evidence = _unique_evidence([*left.evidence_refs, *right.evidence_refs])
    if len(evidence) > policy.max_evidence_refs_per_relationship:
        raise RepositoryRelationshipLimitError(
            "relationship evidence exceeds the configured bound"
        )
    status = (
        AnalyzerClaimStatus.OBSERVED
        if (
            left.status == AnalyzerClaimStatus.OBSERVED
            or right.status == AnalyzerClaimStatus.OBSERVED
        )
        else AnalyzerClaimStatus.INFERRED
    )
    resolved = (
        left.to_repository.resolution_status
        == RepositoryResolutionStatus.CANONICAL
    )
    return left.model_copy(
        update={
            "status": status,
            "confidence": _confidence(
                status=status,
                evidence_count=len(evidence),
                resolved=resolved,
            ),
            "evidence_refs": evidence,
            "summary": (
                left.summary
                if left.summary is not None
                else right.summary
            ),
        }
    )


def _candidate_reference(
    *,
    workspace_id: UUID,
    relationship_type: RelationshipType,
    selector: str,
) -> RepositoryReferenceV1:
    slug = _stable_slug(selector)
    return RepositoryReferenceV1(
        workspace_id=workspace_id,
        repository_id=None,
        provider=RepositoryProvider.GITHUB,
        external_id=f"unresolved:{relationship_type.value}:{slug}"[:255],
        full_name=f"unresolved/{slug}"[:500],
        resolution_status=RepositoryResolutionStatus.CANDIDATE,
    )


def _confidence(
    *,
    status: AnalyzerClaimStatus,
    evidence_count: int,
    resolved: bool,
) -> float:
    if status == AnalyzerClaimStatus.INFERRED:
        return 0.55 if resolved else 0.4
    if not resolved:
        return 0.7
    return min(1.0, 0.9 + 0.02 * max(0, evidence_count - 1))


def _relationship_id(
    *,
    from_entry: RepositoryPortfolioEntryV1,
    relationship_type: RelationshipType,
    target_entry: RepositoryPortfolioEntryV1 | None,
    selector: str,
) -> str:
    target = (
        target_entry.external_id
        if target_entry is not None
        else selector
    )
    return _stable_id(
        "relationship",
        from_entry.external_id,
        relationship_type.value,
        target,
    )


def _relationship_summary(
    *,
    from_entry: RepositoryPortfolioEntryV1,
    relationship_type: RelationshipType,
    target_entry: RepositoryPortfolioEntryV1 | None,
    selector: str,
    status: AnalyzerClaimStatus,
) -> str:
    target = target_entry.full_name if target_entry is not None else selector
    resolution = "resolved" if target_entry is not None else "unresolved"
    return (
        f"{from_entry.full_name} {relationship_type.value.replace('_', ' ')} "
        f"{target}; {status.value} {resolution} candidate."
    )


def _inverse_view(relationship: RepositoryRelationshipV1) -> str:
    if relationship.relationship_type in SYMMETRIC_RELATIONSHIP_TYPES:
        label = relationship.relationship_type.value
        source = relationship.from_repository.full_name
        target = relationship.to_repository.full_name
    else:
        label = RELATIONSHIP_INVERSE_VIEW.get(
            relationship.relationship_type,
            relationship.relationship_type.value,
        )
        source = relationship.to_repository.full_name
        target = relationship.from_repository.full_name
    return f"{source} {label.replace('_', ' ')} {target}"


def _reject_directional_contradictions(
    relationships: list[RepositoryRelationshipV1],
) -> None:
    directional_types = {
        RelationshipType.CALLS_API_OF,
        RelationshipType.IMPORTS_PACKAGE_FROM,
        RelationshipType.CONSUMES_EVENT_FROM,
        RelationshipType.DEPLOYED_BY,
        RelationshipType.USES_IMAGE_FROM,
        RelationshipType.GENERATES_CLIENT_FOR,
        RelationshipType.TESTS,
        RelationshipType.DOCUMENTS,
        RelationshipType.REPLACES,
        RelationshipType.FORKED_FROM,
        RelationshipType.OWNS_MIGRATIONS_FOR,
    }
    seen: set[tuple[RelationshipType, tuple[str, str], tuple[str, str]]] = set()
    for relationship in relationships:
        if (
            relationship.relationship_type not in directional_types
            or relationship.to_repository.resolution_status
            != RepositoryResolutionStatus.CANONICAL
        ):
            continue
        forward = (
            relationship.relationship_type,
            relationship.from_repository.stable_identity(),
            relationship.to_repository.stable_identity(),
        )
        reverse = (
            relationship.relationship_type,
            relationship.to_repository.stable_identity(),
            relationship.from_repository.stable_identity(),
        )
        if reverse in seen:
            raise RepositoryRelationshipValidationError(
                "opposing directional relationship candidates require explicit contradiction review"
            )
        seen.add(forward)


def _find_cycles(
    *,
    repository_ids: set[UUID],
    relationships: list[RepositoryRelationshipV1],
    policy: RepositoryRelationshipPolicy,
) -> list[list[UUID]]:
    adjacency: dict[UUID, set[UUID]] = {
        repository_id: set() for repository_id in repository_ids
    }
    for relationship in relationships:
        source_id = relationship.from_repository.repository_id
        target_id = relationship.to_repository.repository_id
        if source_id is None or target_id is None:
            continue
        if relationship.relationship_type in SYMMETRIC_RELATIONSHIP_TYPES:
            continue
        adjacency[source_id].add(target_id)
    components = _strongly_connected_components(adjacency)
    cycles = [
        sorted(component, key=lambda repository_id: repository_id.hex)
        for component in components
        if len(component) > 1
    ]
    cycles.sort(key=lambda cycle: [repository_id.hex for repository_id in cycle])
    if len(cycles) > policy.max_cycles:
        raise RepositoryRelationshipLimitError(
            "relationship graph exceeds the configured cycle bound"
        )
    if any(len(cycle) > policy.max_cycle_depth for cycle in cycles):
        raise RepositoryRelationshipLimitError(
            "relationship graph exceeds the configured cycle-depth bound"
        )
    return cycles


def _strongly_connected_components(
    adjacency: dict[UUID, set[UUID]],
) -> list[list[UUID]]:
    index = 0
    indexes: dict[UUID, int] = {}
    low_links: dict[UUID, int] = {}
    stack: list[UUID] = []
    on_stack: set[UUID] = set()
    components: list[list[UUID]] = []

    def visit(node: UUID) -> None:
        nonlocal index
        indexes[node] = index
        low_links[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in sorted(adjacency[node], key=lambda item: item.hex):
            if target not in indexes:
                visit(target)
                low_links[node] = min(low_links[node], low_links[target])
            elif target in on_stack:
                low_links[node] = min(low_links[node], indexes[target])
        if low_links[node] != indexes[node]:
            return
        component: list[UUID] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(component)

    for repository_id in sorted(adjacency, key=lambda item: item.hex):
        if repository_id not in indexes:
            visit(repository_id)
    return components


def _graph_findings(
    *,
    relationships: list[RepositoryRelationshipV1],
    cycles: list[list[UUID]],
    orphan_repository_ids: list[UUID],
    unresolved_relationship_ids: list[str],
    policy: RepositoryRelationshipPolicy,
) -> list[RepositoryGraphFindingV1]:
    relationship_by_id = {
        relationship.relationship_id: relationship
        for relationship in relationships
    }
    findings: list[RepositoryGraphFindingV1] = []
    for cycle in cycles:
        relationship_ids = sorted(
            relationship.relationship_id
            for relationship in relationships
            if (
                relationship.from_repository.repository_id in cycle
                and relationship.to_repository.repository_id in cycle
            )
        )
        evidence = _unique_evidence(
            evidence
            for relationship_id in relationship_ids
            for evidence in relationship_by_id[relationship_id].evidence_refs
        )
        findings.append(
            RepositoryGraphFindingV1(
                finding_id=_stable_id(
                    "graph-cycle",
                    *(repository_id.hex for repository_id in cycle),
                ),
                finding_type="cycle",
                repository_ids=cycle,
                relationship_ids=relationship_ids,
                summary="Directional repository relationships contain a cycle.",
                evidence_refs=evidence,
            )
        )
    for repository_id in orphan_repository_ids:
        findings.append(
            RepositoryGraphFindingV1(
                finding_id=_stable_id("graph-orphan", repository_id.hex),
                finding_type="orphan",
                repository_ids=[repository_id],
                summary=(
                    "Repository has no observed or inferred portfolio relationship."
                ),
                evidence_refs=[],
            )
        )
    for relationship_id in unresolved_relationship_ids:
        relationship = relationship_by_id[relationship_id]
        findings.append(
            RepositoryGraphFindingV1(
                finding_id=_stable_id("graph-unresolved", relationship_id),
                finding_type="unresolved_target",
                repository_ids=[
                    relationship.from_repository.repository_id
                ]
                if relationship.from_repository.repository_id is not None
                else [],
                relationship_ids=[relationship_id],
                summary="Relationship target is not resolved to a portfolio repository.",
                evidence_refs=relationship.evidence_refs,
            )
        )
    if len(findings) > policy.max_findings:
        raise RepositoryRelationshipLimitError(
            "relationship graph exceeds the configured finding bound"
        )
    return sorted(findings, key=lambda finding: finding.finding_id)


def _unique_evidence(
    evidence_refs: Iterable[EvidenceRefV1],
) -> list[EvidenceRefV1]:
    by_key: dict[str, EvidenceRefV1] = {}
    for evidence in evidence_refs:
        key = json.dumps(
            evidence.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        by_key[key] = evidence
    return [by_key[key] for key in sorted(by_key)]


def _normalize_selector(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().casefold()
    if (
        not text
        or len(text) > 255
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
        return None
    return text


def _stable_slug(value: str) -> str:
    slug = _STABLE_KEY.sub("-", value.casefold()).strip("-")
    return (slug or "target")[:240].rstrip("-") or "target"


def _stable_id(prefix: str, *parts: str) -> str:
    material = ".".join((prefix, *parts))
    value = _STABLE_KEY.sub(".", material.casefold()).strip(".")
    digest = sha256(material.encode("utf-8")).hexdigest()[:16]
    stem = value[:110].rstrip(".") or "item"
    return f"{stem}.{digest}"


def is_relationship_fact_type(fact_type: str) -> bool:
    """Return whether RI-005 consumes this strict RI-004 fact type."""

    return fact_type in _RELATIONSHIP_FACT_TYPES
