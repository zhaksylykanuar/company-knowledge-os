"""Read-only canonical L0 Repository Intelligence projection.

The projection reads only workspace-scoped ``Repository`` rows and their exact
active repository ``SourceRecord`` evidence. It never uses filesystem
discovery, legacy seeds, provider calls, checkout, target execution or LLMs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.canonical_models import (
    SOURCE_RECORD_PROVIDER_GITHUB,
    Repository,
    SourceRecord,
)
from app.services.repository_intelligence.contracts import (
    AnalysisTargetV1,
    EvidenceRefV1,
    PurposeClaimV1,
    RepositoryAnalyzerResultV1,
    RepositoryFindingV1,
    RepositoryIdentityV1,
    RepositoryIntelligenceV1,
    RepositoryUnknownV1,
)
from app.services.repository_intelligence.taxonomy import (
    AnalyzerClaimStatus,
    AuditLevel,
    EvidenceKind,
    EvidenceSource,
    FindingLifecycleStatus,
    FindingSeverity,
    RepositoryProvider,
    RepositoryType,
    TargetStatus,
)


REPOSITORY_INTELLIGENCE_L0_ENGINE_VERSION = "repository-intelligence-l0.v1"
REPOSITORY_INTELLIGENCE_L0_PROFILE = "repository_l0"
REPOSITORY_INTELLIGENCE_L0_POLICY_HASH = sha256(
    b"repository-intelligence-l0.v1:canonical-only"
).hexdigest()
REPOSITORY_INTELLIGENCE_L0_MAX_REPOSITORIES = 1000
SOURCE_RECORD_TYPE_REPOSITORY = "repository"
_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "code",
        "credential",
        "key",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "sig",
        "signature",
        "token",
        "webhook",
        "x_amz_signature",
        "x_goog_signature",
    }
)


class RepositoryIntelligenceL0Error(RuntimeError):
    """Canonical L0 data cannot be represented by the strict RI contract."""


@dataclass(frozen=True)
class _SourceContext:
    source_record: SourceRecord
    normalized_repository: Mapping[str, Any]
    evidence: EvidenceRefV1


async def build_workspace_repository_intelligence_l0(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> list[RepositoryIntelligenceV1]:
    """Build deterministic L0 results for one workspace without side effects."""

    statement = (
        select(Repository, SourceRecord)
        .outerjoin(
            SourceRecord,
            and_(
                SourceRecord.workspace_id == Repository.workspace_id,
                SourceRecord.provider == Repository.provider,
                SourceRecord.external_id == Repository.external_id,
                SourceRecord.record_type == SOURCE_RECORD_TYPE_REPOSITORY,
                SourceRecord.is_deleted.is_(False),
            ),
        )
        .where(Repository.workspace_id == workspace_id)
        .where(Repository.provider == SOURCE_RECORD_PROVIDER_GITHUB)
        .order_by(Repository.full_name.asc(), Repository.id.asc())
        .limit(REPOSITORY_INTELLIGENCE_L0_MAX_REPOSITORIES + 1)
    )
    rows = (await session.execute(statement)).all()
    if len(rows) > REPOSITORY_INTELLIGENCE_L0_MAX_REPOSITORIES:
        raise RepositoryIntelligenceL0Error(
            "canonical repository count exceeds the bounded L0 limit"
        )
    results: list[RepositoryIntelligenceV1] = []
    for repository, source_record in rows:
        try:
            results.append(
                _project_repository(
                    workspace_id=workspace_id,
                    repository=repository,
                    source_record=source_record,
                )
            )
        except ValueError as exc:
            raise RepositoryIntelligenceL0Error(
                "canonical repository row failed Repository Intelligence validation"
            ) from exc
    return results


def _project_repository(
    *,
    workspace_id: UUID,
    repository: Repository,
    source_record: SourceRecord | None,
) -> RepositoryIntelligenceV1:
    source_context = _source_context(repository, source_record)
    evidence = [source_context.evidence] if source_context is not None else []
    repository_type = _repository_type_candidate(source_context)
    purpose = _purpose_claim(
        workspace_id=workspace_id,
        repository_type=repository_type,
        evidence=evidence,
    )
    unknowns = _unknowns(
        workspace_id=workspace_id,
        repository=repository,
        source_context=source_context,
        purpose=purpose,
    )
    findings = _findings(
        workspace_id=workspace_id,
        repository=repository,
        source_context=source_context,
    )

    return RepositoryIntelligenceV1(
        schema_version="repository_intelligence.v1",
        workspace_id=workspace_id,
        repository_id=repository.id,
        repository=RepositoryIdentityV1(
            provider=RepositoryProvider.GITHUB,
            external_id=repository.external_id,
            full_name=repository.full_name,
            default_branch=_safe_text(repository.default_branch, limit=255),
            source_url=_safe_http_url(repository.source_url),
        ),
        audit_level=AuditLevel.L0,
        analysis_target=AnalysisTargetV1(
            target_status=TargetStatus.UNAVAILABLE,
            commit_algorithm=None,
            commit_sha=None,
            metadata_snapshot_id=_metadata_snapshot_id(
                repository=repository,
                source_context=source_context,
            ),
        ),
        profile=REPOSITORY_INTELLIGENCE_L0_PROFILE,
        policy_hash=REPOSITORY_INTELLIGENCE_L0_POLICY_HASH,
        engine_version=REPOSITORY_INTELLIGENCE_L0_ENGINE_VERSION,
        result=RepositoryAnalyzerResultV1(
            schema_version="repository_analyzer_result.v1",
            purpose=purpose,
            findings=findings,
            unknowns=unknowns,
            limitations=_limitations(
                source_record=source_record,
                source_context=source_context,
            ),
        ),
    )


def _source_context(
    repository: Repository,
    source_record: SourceRecord | None,
) -> _SourceContext | None:
    if source_record is None:
        return None
    payload = source_record.payload if isinstance(source_record.payload, Mapping) else {}
    normalized = payload.get("normalized_repository")
    if not isinstance(normalized, Mapping):
        return None
    normalized_external_id = _safe_text(
        normalized.get("external_id") or normalized.get("id"),
        limit=255,
    )
    normalized_full_name = _safe_text(normalized.get("full_name"), limit=500)
    if normalized_external_id != repository.external_id:
        return None
    if (
        normalized_full_name is None
        or normalized_full_name.casefold() != repository.full_name.casefold()
    ):
        return None
    evidence = EvidenceRefV1(
        kind=EvidenceKind.REPOSITORY_METADATA,
        source=EvidenceSource.GITHUB,
        source_record_id=source_record.id,
        ref=f"repository:{repository.external_id}",
        url=_safe_http_url(source_record.source_url),
    )
    return _SourceContext(
        source_record=source_record,
        normalized_repository=normalized,
        evidence=evidence,
    )


def _repository_type_candidate(
    source_context: _SourceContext | None,
) -> RepositoryType:
    if source_context is None:
        return RepositoryType.UNKNOWN
    normalized = source_context.normalized_repository
    metadata = normalized.get("metadata")
    metadata_mapping = metadata if isinstance(metadata, Mapping) else {}
    candidate = normalized.get("repository_type_candidate")
    if candidate is None:
        candidate = metadata_mapping.get("repository_type_candidate")
    if not isinstance(candidate, str):
        return RepositoryType.UNKNOWN
    try:
        repository_type = RepositoryType(candidate.strip())
    except ValueError:
        return RepositoryType.UNKNOWN
    return (
        repository_type
        if repository_type != RepositoryType.UNKNOWN
        else RepositoryType.UNKNOWN
    )


def _purpose_claim(
    *,
    workspace_id: UUID,
    repository_type: RepositoryType,
    evidence: list[EvidenceRefV1],
) -> PurposeClaimV1:
    if repository_type == RepositoryType.UNKNOWN or not evidence:
        return PurposeClaimV1(
            workspace_id=workspace_id,
            status=AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE,
            confidence=0.0,
            evidence_refs=[],
            claim_id="purpose.primary",
            summary=None,
            operational_summary=None,
            repository_type=RepositoryType.UNKNOWN,
        )
    readable_type = repository_type.value.replace("_", " ")
    return PurposeClaimV1(
        workspace_id=workspace_id,
        status=AnalyzerClaimStatus.INFERRED,
        confidence=0.65,
        evidence_refs=evidence,
        claim_id="purpose.primary",
        summary=(
            f"Canonical metadata supports a {readable_type} repository type "
            "candidate."
        ),
        operational_summary=None,
        repository_type=repository_type,
    )


def _unknowns(
    *,
    workspace_id: UUID,
    repository: Repository,
    source_context: _SourceContext | None,
    purpose: PurposeClaimV1,
) -> list[RepositoryUnknownV1]:
    evidence = [source_context.evidence] if source_context is not None else []
    unknowns = [
        RepositoryUnknownV1(
            unknown_id="unknown.exact-sha",
            workspace_id=workspace_id,
            question="The exact default-branch commit SHA is unavailable.",
            evidence_refs=evidence,
        )
    ]
    if source_context is None:
        unknowns.append(
            RepositoryUnknownV1(
                unknown_id="unknown.canonical-evidence",
                workspace_id=workspace_id,
                question=(
                    "No active identity-matching canonical repository evidence "
                    "is available."
                ),
                evidence_refs=[],
            )
        )
    if purpose.status == AnalyzerClaimStatus.INSUFFICIENT_EVIDENCE:
        unknowns.append(
            RepositoryUnknownV1(
                unknown_id="unknown.purpose",
                workspace_id=workspace_id,
                question=(
                    "Repository purpose and type are not established by "
                    "canonical L0 metadata."
                ),
                evidence_refs=evidence,
            )
        )
    if _safe_text(repository.default_branch, limit=255) is None:
        unknowns.append(
            RepositoryUnknownV1(
                unknown_id="unknown.default-branch",
                workspace_id=workspace_id,
                question="The canonical default branch is unavailable.",
                evidence_refs=evidence,
            )
        )
    return unknowns


def _findings(
    *,
    workspace_id: UUID,
    repository: Repository,
    source_context: _SourceContext | None,
) -> list[RepositoryFindingV1]:
    if source_context is None:
        return []
    source_archived = source_context.normalized_repository.get("archived")
    if source_archived is not True or repository.archived is not True:
        return []
    return [
        RepositoryFindingV1(
            workspace_id=workspace_id,
            status=AnalyzerClaimStatus.OBSERVED,
            confidence=1.0,
            evidence_refs=[source_context.evidence],
            finding_id="finding.repository-archived",
            rule_id="ri.l0.repository-archived",
            category="lifecycle",
            severity=FindingSeverity.INFO,
            lifecycle_status=FindingLifecycleStatus.NEW,
            title="Repository is archived",
            summary=(
                "Canonical repository metadata marks this repository as archived."
            ),
            recommended_next_step=None,
        )
    ]


def _metadata_snapshot_id(
    *,
    repository: Repository,
    source_context: _SourceContext | None,
) -> str:
    if source_context is None:
        material = {
            "archived": repository.archived,
            "default_branch": repository.default_branch,
            "external_id": repository.external_id,
            "full_name": repository.full_name,
            "id": repository.id,
            "last_activity_at": repository.last_activity_at,
            "updated_at": repository.updated_at,
            "visibility": repository.visibility,
            "workspace_id": repository.workspace_id,
        }
        encoded = json.dumps(
            material,
            default=str,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"canonical-repository-{sha256(encoded).hexdigest()}"
    source_record = source_context.source_record
    source_material = (
        f"{source_record.id}:{source_record.payload_hash}:"
        f"{source_record.observed_at.isoformat()}"
    )
    return (
        "canonical-source-record-"
        f"{sha256(source_material.encode('utf-8')).hexdigest()}"
    )


def _limitations(
    *,
    source_record: SourceRecord | None,
    source_context: _SourceContext | None,
) -> list[str]:
    limitations = [
        "L0 reads only canonical workspace-scoped Repository and active repository SourceRecord rows.",
        "No filesystem snapshot, provider call, checkout, target execution or LLM analysis was used.",
    ]
    if source_record is None:
        limitations.append(
            "No active canonical repository SourceRecord was available."
        )
    elif source_context is None:
        limitations.append(
            "The active repository SourceRecord failed exact identity validation and was not used as evidence."
        )
    return limitations


def _safe_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > limit:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        return None
    return text


def _safe_http_url(value: Any) -> str | None:
    text = _safe_text(value, limit=1000)
    if text is None or "\\" in text or any(character.isspace() for character in text):
        return None
    try:
        parsed = urlsplit(text)
        parsed.port
        query_pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            max_num_fields=100,
        )
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    if any(
        key.casefold().replace("-", "_") in _SENSITIVE_QUERY_KEYS
        for key, _value in query_pairs
    ):
        return None
    return text
