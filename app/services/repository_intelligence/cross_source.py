"""Deterministic cross-source Repository Intelligence comparisons (RI-008).

The service compares current RI-006 facts with explicitly structured claims
embedded in canonical GitHub/Jira task metadata or opt-in internal documents.
It never derives claims from free text, fuzzy names, embeddings, or provider
calls. Conflicting claims are preserved in the read model; this slice adds no
new persistence or migration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import math
import re
from typing import Any, Literal
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
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated, Self

from app.db.canonical_models import (
    EvidenceRef,
    PullRequest,
    Repository,
    SourceRecord,
    Task,
)
from app.db.document_models import DOCUMENT_STATUS_ARCHIVED, Document
from app.db.repository_intelligence_models import (
    REPOSITORY_EVIDENCE_ROLE_CONTRADICTING,
    REPOSITORY_EVIDENCE_ROLE_SUPPORTING,
    REPOSITORY_LIFECYCLE_STATUS_CURRENT,
    RepositoryEvidenceLink,
    RepositoryFact,
)
from app.services.headquarters_read_service import (
    sanitize_headquarters_evidence_url,
)
from app.services.repository_intelligence.taxonomy import RepositoryType


CROSS_SOURCE_CLAIM_SET_SCHEMA = "repository_cross_source_claim_set.v1"
CROSS_SOURCE_CLAIM_SCHEMA = "repository_cross_source_claim.v1"
CROSS_SOURCE_METADATA_KEY = "repository_intelligence_claims"
CROSS_SOURCE_DOCUMENT_TAG = "repository-intelligence"

MAX_CROSS_SOURCE_SOURCES = 200
MAX_CROSS_SOURCE_CLAIMS_PER_SOURCE = 20
MAX_CROSS_SOURCE_COMPARISONS = 200
MAX_CROSS_SOURCE_REJECTIONS = 100
MAX_CROSS_SOURCE_CLAIM_BYTES = 16 * 1024
MAX_CROSS_SOURCE_EVIDENCE_PER_FACT = 20

_STABLE_KEY = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_GITHUB_FULL_NAME = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,254})$"
)
_SUPPORTED_FACT_TYPES = frozenset(
    {
        "purpose",
        "responsibility",
        "interface_provided",
        "dependency_consumed",
        "deployment_unit",
        "owner_candidate",
    }
)
StrictSummary = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
StrictValue = Annotated[str, StringConstraints(min_length=1, max_length=255)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepositoryCrossSourceClaimV1(_StrictModel):
    """One explicit source assertion about one exact persisted RI fact."""

    schema_version: Literal["repository_cross_source_claim.v1"] = (
        "repository_cross_source_claim.v1"
    )
    repository_id: UUID
    repository_full_name: Annotated[
        str,
        StringConstraints(min_length=3, max_length=500),
    ]
    fact_type: Literal[
        "purpose",
        "responsibility",
        "interface_provided",
        "dependency_consumed",
        "deployment_unit",
        "owner_candidate",
    ]
    claim_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    field: Literal["repository_type", "claim_type"]
    expected_value: StrictValue
    summary: StrictSummary
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator(
        "repository_full_name",
        "claim_id",
        "expected_value",
        "summary",
    )
    @classmethod
    def validate_safe_text(cls, value: str, info: Any) -> str:
        if (
            value != value.strip()
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in value
            )
        ):
            raise ValueError(f"{info.field_name} contains unsafe text")
        return value

    @field_validator("repository_full_name")
    @classmethod
    def validate_repository_full_name(cls, value: str) -> str:
        if _GITHUB_FULL_NAME.fullmatch(value) is None:
            raise ValueError("repository_full_name must be owner/repository")
        return value

    @field_validator("claim_id")
    @classmethod
    def validate_claim_id(cls, value: str) -> str:
        if _STABLE_KEY.fullmatch(value) is None:
            raise ValueError("claim_id must be a stable key")
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence_type(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("confidence must be a number")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_finite_confidence(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("confidence must be finite")
        return value

    @model_validator(mode="after")
    def validate_fact_field(self) -> Self:
        if self.fact_type == "purpose":
            if (
                self.claim_id != "purpose.primary"
                or self.field != "repository_type"
            ):
                raise ValueError(
                    "purpose claims compare only purpose.primary repository_type"
                )
            try:
                repository_type = RepositoryType(self.expected_value)
            except ValueError as exc:
                raise ValueError("unsupported repository_type value") from exc
            if repository_type == RepositoryType.UNKNOWN:
                raise ValueError("unknown cannot be asserted as a source claim")
            return self
        if self.field != "claim_type":
            raise ValueError(
                "non-purpose claims compare only their controlled claim_type"
            )
        if _STABLE_KEY.fullmatch(self.expected_value) is None:
            raise ValueError("claim_type must be a stable key")
        return self


class RepositoryCrossSourceClaimSetV1(_StrictModel):
    """Bounded envelope reused by task metadata and opt-in documents."""

    schema_version: Literal["repository_cross_source_claim_set.v1"] = (
        "repository_cross_source_claim_set.v1"
    )
    claims: list[RepositoryCrossSourceClaimV1] = Field(
        min_length=1,
        max_length=MAX_CROSS_SOURCE_CLAIMS_PER_SOURCE,
    )

    @model_validator(mode="after")
    def validate_unique_claims(self) -> Self:
        identities = [
            (claim.fact_type, claim.claim_id, claim.field)
            for claim in self.claims
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("claim set contains duplicate comparisons")
        repositories = {
            (claim.repository_id, claim.repository_full_name.casefold())
            for claim in self.claims
        }
        if len(repositories) != 1:
            raise ValueError("claim set must target one exact repository")
        return self


async def build_repository_cross_source_comparisons(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    repository: Repository,
) -> dict[str, Any]:
    """Compare exact structured source claims with current RI facts."""

    facts = list(
        (
            await session.execute(
                select(RepositoryFact)
                .where(
                    RepositoryFact.workspace_id == workspace_id,
                    RepositoryFact.repository_id == repository.id,
                    RepositoryFact.lifecycle_status
                    == REPOSITORY_LIFECYCLE_STATUS_CURRENT,
                    RepositoryFact.fact_type.in_(_SUPPORTED_FACT_TYPES),
                )
                .order_by(
                    RepositoryFact.fact_type.asc(),
                    RepositoryFact.claim_id.asc(),
                    RepositoryFact.id.asc(),
                )
                .limit(500)
            )
        ).scalars()
    )
    facts_by_identity = {
        (fact.fact_type, fact.claim_id): fact for fact in facts
    }
    fact_evidence = await _fact_evidence(
        session=session,
        workspace_id=workspace_id,
        fact_ids=[fact.id for fact in facts],
    )

    sources, sources_truncated = await _cross_source_records(
        session=session,
        workspace_id=workspace_id,
    )
    comparisons: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rejected_total = 0
    comparisons_truncated = False

    for source in sources:
        claim_set, error_code = _claim_set_from_source(source)
        if error_code is not None:
            rejected_total += 1
            if len(rejected) < MAX_CROSS_SOURCE_REJECTIONS:
                rejected.append(
                    {
                        "source": _source_payload(source),
                        "error_code": error_code,
                    }
                )
            continue
        if claim_set is None:
            continue
        first_claim = claim_set.claims[0]
        if (
            first_claim.repository_id != repository.id
            or first_claim.repository_full_name.casefold()
            != repository.full_name.casefold()
        ):
            rejected_total += 1
            if len(rejected) < MAX_CROSS_SOURCE_REJECTIONS:
                rejected.append(
                    {
                        "source": _source_payload(source),
                        "error_code": "repository_identity_mismatch",
                    }
                )
            continue
        for claim in claim_set.claims:
            if len(comparisons) >= MAX_CROSS_SOURCE_COMPARISONS:
                comparisons_truncated = True
                break
            fact = facts_by_identity.get((claim.fact_type, claim.claim_id))
            comparisons.append(
                _comparison_payload(
                    source=source,
                    claim=claim,
                    fact=fact,
                    repository_evidence=(
                        fact_evidence.get(fact.id, []) if fact is not None else []
                    ),
                )
            )
        if comparisons_truncated:
            break

    return {
        "summary": {
            "sources_considered": len(sources),
            "comparisons": len(comparisons),
            "agreements": sum(
                1 for item in comparisons if item["status"] == "agreement"
            ),
            "contradictions": sum(
                1 for item in comparisons if item["status"] == "contradiction"
            ),
            "insufficient_evidence": sum(
                1
                for item in comparisons
                if item["status"] == "insufficient_evidence"
            ),
            "rejected_claim_sets": rejected_total,
        },
        "comparisons": comparisons,
        "rejected_claim_sets": rejected,
        "truncated": {
            "sources": sources_truncated,
            "comparisons": comparisons_truncated,
            "rejected_claim_sets": len(rejected)
            < rejected_total,
        },
        "contract": {
            "claim_set_schema": CROSS_SOURCE_CLAIM_SET_SCHEMA,
            "claim_schema": CROSS_SOURCE_CLAIM_SCHEMA,
            "exact_repository_identity_required": True,
            "free_text_inference": False,
            "fuzzy_matching": False,
            "persistence_write": False,
        },
    }


async def _cross_source_records(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> tuple[list[dict[str, Any]], bool]:
    tasks = list(
        (
            await session.execute(
                select(Task, SourceRecord)
                .join(
                    SourceRecord,
                    and_(
                        SourceRecord.workspace_id == Task.workspace_id,
                        SourceRecord.id == Task.source_record_id,
                    ),
                )
                .where(
                    Task.workspace_id == workspace_id,
                    Task.source_provider.in_(("github", "jira")),
                    SourceRecord.provider == Task.source_provider,
                    SourceRecord.record_type == "issue",
                    SourceRecord.is_deleted.is_(False),
                )
                .order_by(
                    Task.source_updated_at.desc().nullslast(),
                    Task.updated_at.desc(),
                    Task.id.desc(),
                )
                .limit(MAX_CROSS_SOURCE_SOURCES + 1)
            )
        ).all()
    )
    pull_requests = list(
        (
            await session.execute(
                select(PullRequest, SourceRecord)
                .join(
                    SourceRecord,
                    and_(
                        SourceRecord.workspace_id == PullRequest.workspace_id,
                        SourceRecord.id == PullRequest.source_record_id,
                    ),
                )
                .where(
                    PullRequest.workspace_id == workspace_id,
                    SourceRecord.provider == "github",
                    SourceRecord.record_type == "pull_request",
                    SourceRecord.is_deleted.is_(False),
                )
                .order_by(
                    PullRequest.updated_at_source.desc().nullslast(),
                    PullRequest.created_at.desc(),
                    PullRequest.id.desc(),
                )
                .limit(MAX_CROSS_SOURCE_SOURCES + 1)
            )
        ).all()
    )
    documents = list(
        (
            await session.execute(
                select(Document)
                .where(
                    Document.workspace_id == workspace_id,
                    Document.status != DOCUMENT_STATUS_ARCHIVED,
                )
                .order_by(Document.updated_at.desc(), Document.id.desc())
                .limit(MAX_CROSS_SOURCE_SOURCES + 1)
            )
        ).scalars()
    )
    task_truncated = len(tasks) > MAX_CROSS_SOURCE_SOURCES
    pull_request_truncated = (
        len(pull_requests) > MAX_CROSS_SOURCE_SOURCES
    )
    document_truncated = len(documents) > MAX_CROSS_SOURCE_SOURCES
    sources: list[dict[str, Any]] = []
    for task, source_record in tasks[:MAX_CROSS_SOURCE_SOURCES]:
        metadata = (
            task.task_metadata
            if isinstance(task.task_metadata, Mapping)
            else {}
        )
        if CROSS_SOURCE_METADATA_KEY not in metadata:
            continue
        sources.append(
            {
                "source_type": "task",
                "provider": task.source_provider,
                "record_id": source_record.id,
                "ref": task.external_id or task.title,
                "url": sanitize_headquarters_evidence_url(task.source_url),
                "observed_at": task.source_updated_at or task.updated_at,
                "claim_set": metadata.get(CROSS_SOURCE_METADATA_KEY),
            }
        )
    for pull_request, source_record in pull_requests[
        :MAX_CROSS_SOURCE_SOURCES
    ]:
        metadata = (
            pull_request.pr_metadata
            if isinstance(pull_request.pr_metadata, Mapping)
            else {}
        )
        if CROSS_SOURCE_METADATA_KEY not in metadata:
            continue
        sources.append(
            {
                "source_type": "pull_request",
                "provider": "github",
                "record_id": (
                    source_record.id
                ),
                "ref": pull_request.external_id or pull_request.title,
                "url": sanitize_headquarters_evidence_url(
                    pull_request.source_url
                ),
                "observed_at": (
                    pull_request.updated_at_source
                    or pull_request.created_at
                ),
                "claim_set": metadata.get(CROSS_SOURCE_METADATA_KEY),
            }
        )
    for document in documents[:MAX_CROSS_SOURCE_SOURCES]:
        tags = {
            tag.casefold()
            for tag in document.tags
            if isinstance(tag, str)
        }
        if CROSS_SOURCE_DOCUMENT_TAG not in tags:
            continue
        sources.append(
            {
                "source_type": "document",
                "provider": "internal",
                "record_id": document.id,
                "ref": document.title,
                "url": None,
                "observed_at": document.updated_at,
                "claim_set": document.body_markdown,
            }
        )
    sources.sort(
        key=lambda source: (
            source.get("observed_at") is not None,
            source.get("observed_at"),
            str(source.get("record_id")),
        ),
        reverse=True,
    )
    return (
        sources[:MAX_CROSS_SOURCE_SOURCES],
        task_truncated
        or pull_request_truncated
        or document_truncated
        or len(sources) > MAX_CROSS_SOURCE_SOURCES,
    )


async def _fact_evidence(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    fact_ids: Sequence[UUID],
) -> dict[UUID, list[dict[str, Any]]]:
    if not fact_ids:
        return {}
    rows = (
        await session.execute(
            select(RepositoryEvidenceLink, EvidenceRef)
            .join(
                EvidenceRef,
                and_(
                    EvidenceRef.workspace_id
                    == RepositoryEvidenceLink.workspace_id,
                    EvidenceRef.id == RepositoryEvidenceLink.evidence_ref_id,
                ),
            )
            .where(
                RepositoryEvidenceLink.workspace_id == workspace_id,
                RepositoryEvidenceLink.fact_id.in_(fact_ids),
            )
            .order_by(
                RepositoryEvidenceLink.fact_id.asc(),
                RepositoryEvidenceLink.created_at.asc(),
                RepositoryEvidenceLink.id.asc(),
            )
        )
    ).all()
    result: dict[UUID, list[dict[str, Any]]] = {}
    for link, evidence_ref in rows:
        fact_id = link.fact_id
        if fact_id is None:
            continue
        evidence = result.setdefault(fact_id, [])
        if len(evidence) >= MAX_CROSS_SOURCE_EVIDENCE_PER_FACT:
            continue
        evidence.append(
            {
                "id": evidence_ref.id,
                "role": link.evidence_role,
                "kind": evidence_ref.evidence_kind
                or "repository_metadata",
                "source": evidence_ref.evidence_source or "internal",
                "ref": _safe_text(evidence_ref.selector, limit=500),
                "record_id": evidence_ref.source_record_id,
                "url": sanitize_headquarters_evidence_url(
                    evidence_ref.source_url
                ),
                "confidence": evidence_ref.confidence,
            }
        )
    return result


def _claim_set_from_source(
    source: Mapping[str, Any],
) -> tuple[RepositoryCrossSourceClaimSetV1 | None, str | None]:
    value = source.get("claim_set")
    if source.get("source_type") == "document":
        if not isinstance(value, str):
            return None, "claim_set_invalid"
        encoded = value.encode("utf-8")
        if len(encoded) > MAX_CROSS_SOURCE_CLAIM_BYTES:
            return None, "claim_set_too_large"
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, UnicodeError):
            return None, "claim_set_invalid_json"
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return None, "claim_set_invalid"
    if len(encoded) > MAX_CROSS_SOURCE_CLAIM_BYTES:
        return None, "claim_set_too_large"
    try:
        return RepositoryCrossSourceClaimSetV1.model_validate(value), None
    except ValidationError:
        return None, "claim_set_invalid"


def _comparison_payload(
    *,
    source: Mapping[str, Any],
    claim: RepositoryCrossSourceClaimV1,
    fact: RepositoryFact | None,
    repository_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    actual_value = _fact_field_value(fact, claim.field)
    if (
        fact is None
        or actual_value is None
        or fact.claim_status == "insufficient_evidence"
        or fact.human_resolution_status == "rejected"
        or actual_value == "unknown"
    ):
        status: Literal[
            "agreement",
            "contradiction",
            "insufficient_evidence",
        ] = "insufficient_evidence"
        summary = (
            f"No current RI fact exactly matches {claim.fact_type}:"
            f"{claim.claim_id}.{claim.field}."
        )
    elif actual_value == claim.expected_value:
        status = "agreement"
        summary = (
            f"Source claim agrees with RI: {claim.claim_id}.{claim.field}="
            f"{claim.expected_value}."
        )
    else:
        status = "contradiction"
        summary = (
            f"Source claim asserts {claim.claim_id}.{claim.field}="
            f"{claim.expected_value}, while RI records {actual_value}."
        )
    source_payload = _source_payload(source)
    comparison_key = json.dumps(
        {
            "source": source_payload,
            "claim": claim.model_dump(mode="json"),
            "fact_id": str(fact.id) if fact is not None else None,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return {
        "id": sha256(comparison_key.encode("utf-8")).hexdigest(),
        "status": status,
        "summary": summary,
        "source": source_payload,
        "source_claim": {
            "fact_type": claim.fact_type,
            "claim_id": claim.claim_id,
            "field": claim.field,
            "expected_value": claim.expected_value,
            "summary": claim.summary,
            "confidence": claim.confidence,
        },
        "repository_fact": (
            {
                "id": fact.id,
                "fact_type": fact.fact_type,
                "claim_id": fact.claim_id,
                "field": claim.field,
                "actual_value": actual_value,
                "claim_status": fact.claim_status,
                "confidence": fact.confidence,
                "human_resolution_status": fact.human_resolution_status,
            }
            if fact is not None and actual_value is not None
            else None
        ),
        "source_evidence": [
            _source_evidence_payload(
                source,
                role=(
                    REPOSITORY_EVIDENCE_ROLE_CONTRADICTING
                    if status == "contradiction"
                    else REPOSITORY_EVIDENCE_ROLE_SUPPORTING
                ),
                confidence=claim.confidence,
            )
        ],
        "repository_evidence": repository_evidence,
    }


def _fact_field_value(
    fact: RepositoryFact | None,
    field: str,
) -> str | None:
    if fact is None or not isinstance(fact.value, Mapping):
        return None
    value = fact.value.get(field)
    return _safe_text(value, limit=255)


def _source_payload(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_type": source.get("source_type"),
        "provider": source.get("provider"),
        "record_id": source.get("record_id"),
        "ref": _safe_text(source.get("ref"), limit=500) or "unknown",
        "url": sanitize_headquarters_evidence_url(source.get("url")),
        "observed_at": source.get("observed_at"),
    }


def _source_evidence_payload(
    source: Mapping[str, Any],
    *,
    role: str,
    confidence: float,
) -> dict[str, Any]:
    provider = source.get("provider")
    source_type = source.get("source_type")
    kind = (
        "github_pull_request"
        if source_type == "pull_request"
        else "github_issue"
        if provider == "github"
        else "jira_issue"
        if provider == "jira"
        else "document"
    )
    return {
        "id": source.get("record_id"),
        "kind": kind,
        "source": provider,
        "ref": _safe_text(source.get("ref"), limit=500),
        "record_id": source.get("record_id"),
        "url": sanitize_headquarters_evidence_url(source.get("url")),
        "role": role,
        "confidence": confidence,
    }


def _safe_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if (
        not text
        or len(text) > limit
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
        return None
    return text
