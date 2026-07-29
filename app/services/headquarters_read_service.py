"""One deterministic, read-only projection for the FounderOS headquarters.

The service is deliberately the only place that ranks the headquarters mission
queue.  It reads promoted/canonical workspace data in one PostgreSQL
REPEATABLE READ, READ ONLY transaction and never calls providers, an LLM, or a
write service.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID

from sqlalchemy import Text, func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import CONNECTOR_DESCRIPTORS
from app.core.config import settings
from app.db.action_models import (
    ACTION_CREATED_BY_SYSTEM,
    ACTION_PROPOSAL_STATUS_PROPOSED,
    ACTION_TARGET_PROVIDER_GITHUB,
    ActionProposal,
)
from app.db.base import AsyncSessionLocal
from app.db.briefing_models import Briefing, BriefingItem
from app.db.canonical_models import EvidenceRef, Repository, SourceRecord
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_ERROR,
    SYNC_JOB_STATUS_FAILED,
    SYNC_JOB_STATUS_PARTIAL,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_STATUS_RUNNING,
    SYNC_JOB_STATUS_SUCCEEDED,
    IntegrationConnection,
    SyncJob,
)
from app.db.memory_models import (
    COMPANY_MEMORY_CHECKPOINT_VERSION,
    COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_APPROVED,
    COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_REJECTED,
    COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED,
    COMPANY_MEMORY_EVENT_COMPANY_WORLD_DISMISSED,
    COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED,
    COMPANY_MEMORY_EVENT_SOURCE_RECORD_RESTORED,
    COMPANY_MEMORY_LIFECYCLE_RESOLVED,
    CompanyMemoryCheckpoint,
    CompanyMemoryEvent,
    CompanyMemoryEventStream,
)
from app.services.action_proposal_service import (
    ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES,
    ACTION_PROPOSAL_EVIDENCE_REFS_MAX_ITEMS,
    ACTION_PROPOSAL_PAYLOAD_MAX_BYTES,
    action_evidence_ref_matches_schema,
    action_proposal_version,
)
from app.services.company_map_read_service import build_workspace_company_map
from app.services.identity_service import role_allows


HEADQUARTERS_CONTRACT_VERSION = "headquarters.v3"
HEADQUARTERS_RANKING_VERSION = "headquarters-ranking.v1"
HEADQUARTERS_ONBOARDING_CONTRACT_VERSION = "onboarding.v1"
HEADQUARTERS_ONBOARDING_READINESS_VERSION = "onboarding-readiness.v1"
HEADQUARTERS_SOURCE_HEALTH_VERSION = "source-health.v1"
HEADQUARTERS_CORRELATION_VERSION = "canonical-reference.v1"
HEADQUARTERS_TEMPORAL_MEMORY_VERSION = "temporal-memory.v2"
HEADQUARTERS_TEMPORAL_EVENT_LIMIT = 3
HEADQUARTERS_CHECKPOINT_FINGERPRINT_LIMIT = 512

SOURCE_FRESHNESS_THRESHOLD = timedelta(hours=72)
HEADQUARTERS_PROPOSAL_SCAN_LIMIT = 100
HEADQUARTERS_STATEMENT_TIMEOUT_MS = 5_000
SOURCE_KEY_ALIASES = {
    "canonical_github_company_brain": "github",
    "drive": "drive",
    "github": "github",
    "github_app_live_sync": "github",
    "github_app_setup": "github",
    "github_issue_read_api": "github",
    "github_normalization_work_item": "github",
    "github_repository_read_api": "github",
    "gmail": "gmail",
    "internal": "internal",
    "jira": "jira",
    "repository_inventory": "github",
    "selected_repository_issue_sync": "github",
    "selected_repository_pr_sync": "github",
}
GENERIC_SOURCE_ALIASES = frozenset(
    {
        "briefing_item",
        "canonical_source_record",
        "company_brain",
        "documents",
        "founderos",
        "local_db",
    }
)
KNOWN_SOURCE_KEYS = frozenset(SOURCE_KEY_ALIASES.values())
ACTIVE_CONNECTION_STATUSES = frozenset(
    {
        INTEGRATION_CONNECTION_STATUS_CONNECTED,
        INTEGRATION_CONNECTION_STATUS_ERROR,
    }
)
KNOWN_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
SEVERITY_RANK = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
SENSITIVE_EVIDENCE_URL_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "code",
        "key",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "sig",
        "signature",
        "token",
        "x_amz_signature",
        "x_goog_signature",
    }
)


class HeadquartersAccessChangedError(PermissionError):
    """Membership disappeared between the auth dependency and the snapshot."""


class HeadquartersSubprojectionUnavailable(RuntimeError):
    """Expected, isolated read unavailability that may produce a partial 200."""

    def __init__(self, *, key: str, code: str) -> None:
        if key not in {"company_world"}:
            raise ValueError("unknown headquarters subprojection")
        safe_code = "".join(
            character for character in code if character.isalnum() or character in "_-"
        )
        super().__init__(safe_code or "unavailable")
        self.key = key
        self.code = safe_code or "unavailable"


class ActionProposalEvidenceValidationError(ValueError):
    """A proposal does not have fully canonical, relevant workspace evidence."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class MissionCandidate:
    mission: dict[str, Any]
    score: int
    event_time: datetime | None
    observed_at: datetime | None
    change_kind: str | None


@dataclass(frozen=True)
class VerifiedProposal:
    proposal: ActionProposal
    evidence_refs: list[dict[str, Any]]
    trusted_briefing_item: BriefingItem | None


@dataclass(frozen=True)
class ResolvedEvidence:
    evidence: dict[str, Any]
    version: dict[str, Any]
    match_kind: str
    match_key: str | None


@dataclass(frozen=True)
class EvidenceSelector:
    kind: str
    token: str
    source_record_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionRows:
    proposals: list[ActionProposal]
    proposed_total: int
    oversized_proposal_count: int
    proposals_truncated: bool
    latest_proposal_updated_at: datetime | None
    briefing_count: int
    decided_proposal_count: int
    latest_briefing: Briefing | None


@dataclass(frozen=True)
class CompanyMemoryEventWindow:
    current_sequence: int
    resolved_rows: list[CompanyMemoryEvent]
    resolved_total: int
    cursor_valid: bool


async def read_workspace_headquarters(
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> dict[str, Any]:
    """Read one consistent headquarters snapshot without mutating any state."""

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # This is intentionally the first statement in the transaction.
            # PostgreSQL then rejects accidental writes anywhere below.
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            await session.execute(
                text(f"SET LOCAL statement_timeout = '{HEADQUARTERS_STATEMENT_TIMEOUT_MS}ms'")
            )
            as_of = await session.scalar(select(func.transaction_timestamp()))
            if not isinstance(as_of, datetime):
                raise RuntimeError("transaction timestamp is unavailable")
            payload = await _build_headquarters_snapshot(
                session=session,
                workspace_id=workspace_id,
                user_id=user_id,
                as_of=as_of,
            )
            payload.pop("_checkpoint_fingerprints", None)
            payload.pop("_memory_event_sequence", None)
            return payload


async def _build_headquarters_snapshot(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    as_of: datetime,
) -> dict[str, Any]:
    workspace, membership, member_count = await _read_identity(
        session=session,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    role = membership.role
    capabilities = _capabilities(role)
    checkpoint = await _read_company_memory_checkpoint(
        session=session,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    memory_event_window = await _read_company_memory_event_window(
        session=session,
        workspace_id=workspace_id,
        checkpoint=checkpoint,
    )

    (
        sources,
        source_mission_evidence,
        source_material,
        canonical_source_record_count,
    ) = await _read_sources(
        session=session,
        workspace_id=workspace_id,
        role=role,
        as_of=as_of,
    )
    decision_rows = await _read_decision_rows(
        session=session,
        workspace_id=workspace_id,
    )
    verified_proposals = await _verify_proposals(
        session=session,
        workspace_id=workspace_id,
        proposals=decision_rows.proposals,
    )

    warnings: list[str] = []
    company_world: dict[str, Any] | None
    company_world_status = "complete"
    company_world_warning: str | None = None
    try:
        # A savepoint keeps a known Company World statement timeout isolated
        # from the otherwise consistent read-only snapshot. PostgreSQL marks a
        # transaction failed after a cancelled statement, so the savepoint is
        # required before a typed partial response can be truthful.
        async with session.begin_nested():
            company_world = await _read_company_world_projection(
                session=session,
                workspace_id=workspace_id,
                role=role,
            )
    except HeadquartersSubprojectionUnavailable as exc:
        company_world = None
        company_world_status = "unavailable"
        company_world_warning = f"company_world_unavailable:{exc.code}"
        warnings.append(company_world_warning)
    except DBAPIError as exc:
        if _database_error_code(exc) != "57014":
            raise
        company_world = None
        company_world_status = "unavailable"
        company_world_warning = "company_world_unavailable:statement_timeout"
        warnings.append(company_world_warning)

    if company_world is not None and bool(company_world["window"]["truncated"]):
        company_world_status = "partial"
        company_world_warning = "company_world_window_truncated"
        warnings.append(company_world_warning)

    company_world_observed_at = (
        await _read_company_world_observed_at(
            session=session,
            workspace_id=workspace_id,
            company_world=company_world,
        )
        if company_world is not None
        else {}
    )

    excluded_proposals = len(decision_rows.proposals) - len(verified_proposals)
    if excluded_proposals:
        warnings.append(f"proposals_excluded_unverified_or_unrelated_evidence:{excluded_proposals}")
    decision_warning: str | None = None
    decision_partial = (
        decision_rows.proposals_truncated or decision_rows.oversized_proposal_count > 0
    )
    if decision_rows.proposals_truncated:
        decision_warning = "decision_window_truncated"
        warnings.append(
            f"decision_window_truncated:{decision_rows.proposed_total}:"
            f"{HEADQUARTERS_PROPOSAL_SCAN_LIMIT}"
        )
    if decision_rows.oversized_proposal_count:
        decision_warning = decision_warning or "decision_oversized_json_excluded"
        warnings.append(
            f"decision_oversized_json_excluded:{decision_rows.oversized_proposal_count}"
        )

    onboarding = _build_onboarding(
        member_count=member_count,
        configured_source_count=sources["configured_count"],
        canonical_source_record_count=canonical_source_record_count,
        briefing_count=decision_rows.briefing_count,
        decided_proposal_count=decision_rows.decided_proposal_count,
        company_world=company_world,
        company_world_status=company_world_status,
        capabilities=capabilities,
    )
    mission_candidates = _build_mission_candidates(
        verified_proposals=verified_proposals,
        sources=sources,
        source_mission_evidence=source_mission_evidence,
        company_world=company_world,
        company_world_observed_at=company_world_observed_at,
        briefing_count=decision_rows.briefing_count,
        latest_briefing=decision_rows.latest_briefing,
        capabilities=capabilities,
        workspace_id=workspace_id,
    )
    ranked = sorted(mission_candidates, key=_mission_sort_key)
    priority = ranked[0].mission if ranked else None
    queue = [candidate.mission for candidate in ranked[1:3]]
    pulse = _build_pulse(
        verified_proposal_count=len(verified_proposals),
        verified_proposal_count_is_lower_bound=decision_partial,
        sources=sources,
        company_world=company_world,
        company_world_status=company_world_status,
        capabilities=capabilities,
    )
    resolved_memory_items = await _build_resolved_memory_event_items(
        session=session,
        workspace_id=workspace_id,
        events=memory_event_window.resolved_rows,
    )
    changes, checkpoint_fingerprints, checkpoint_valid = _build_changes(
        ranked,
        checkpoint=checkpoint,
        partial=decision_partial or company_world_status != "complete",
        resolved_items=resolved_memory_items,
        resolved_total=memory_event_window.resolved_total,
        event_cursor_valid=memory_event_window.cursor_valid,
    )
    memory_status = "complete" if checkpoint_valid else "partial"
    memory_warning = None if checkpoint_valid else "memory_checkpoint_invalid"
    if memory_warning is not None:
        warnings.append(memory_warning)

    identity_material = {
        "workspace_id": workspace.id,
        "workspace_updated_at": workspace.updated_at,
        "membership_id": membership.id,
        "role": role,
        "member_count": member_count,
    }
    decision_material = {
        "briefing_count": decision_rows.briefing_count,
        "decided_proposal_count": decision_rows.decided_proposal_count,
        "proposed_total": decision_rows.proposed_total,
        "oversized_proposal_count": decision_rows.oversized_proposal_count,
        "payload_max_bytes": ACTION_PROPOSAL_PAYLOAD_MAX_BYTES,
        "evidence_refs_max_bytes": ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES,
        "evidence_refs_max_items": ACTION_PROPOSAL_EVIDENCE_REFS_MAX_ITEMS,
        "proposal_scan_limit": HEADQUARTERS_PROPOSAL_SCAN_LIMIT,
        "proposals_truncated": decision_rows.proposals_truncated,
        "latest_proposal_updated_at": decision_rows.latest_proposal_updated_at,
        "latest_briefing": (
            {
                "id": decision_rows.latest_briefing.id,
                "as_of": decision_rows.latest_briefing.as_of,
                "created_at": decision_rows.latest_briefing.created_at,
            }
            if decision_rows.latest_briefing is not None
            else None
        ),
        "proposals": [
            {
                "id": proposal.proposal.id,
                "status": proposal.proposal.status,
                "updated_at": proposal.proposal.updated_at,
                "verified_evidence": [ref["id"] for ref in proposal.evidence_refs],
            }
            for proposal in verified_proposals
        ],
        "excluded": excluded_proposals,
    }
    company_world_material = _company_world_watermark_material(company_world)
    memory_material = _company_memory_watermark_material(
        checkpoint=checkpoint,
        event_fingerprints=checkpoint_fingerprints,
        checkpoint_valid=checkpoint_valid,
        current_event_sequence=memory_event_window.current_sequence,
        resolved_event_count=memory_event_window.resolved_total,
    )
    coverage = [
        _coverage("identity", "complete", identity_material),
        _coverage("sources", "complete", source_material),
        _coverage(
            "decisions",
            "partial" if decision_partial else "complete",
            decision_material,
            decision_warning,
        ),
        _coverage(
            "company_world",
            company_world_status,
            company_world_material,
            company_world_warning,
        ),
        _coverage("memory", memory_status, memory_material, memory_warning),
    ]

    stable_payload: dict[str, Any] = {
        "contract_version": HEADQUARTERS_CONTRACT_VERSION,
        "ranking_version": HEADQUARTERS_RANKING_VERSION,
        "workspace": {"id": workspace.id, "name": workspace.name, "role": role},
        "onboarding": onboarding,
        "sources": sources,
        "priority": priority,
        "pulse": pulse,
        "queue": queue,
        "changes": changes,
        "capabilities": capabilities,
        "boundary": {
            "provider_calls": False,
            "external_writes": False,
            "llm": False,
            "reads_secrets": False,
            "transaction": "repeatable_read_read_only",
        },
        "coverage": coverage,
        "warnings": warnings,
    }
    snapshot_id = f"hqs1_{_digest(stable_payload)}"
    return {
        "contract_version": HEADQUARTERS_CONTRACT_VERSION,
        "ranking_version": HEADQUARTERS_RANKING_VERSION,
        "snapshot": {
            "id": snapshot_id,
            "as_of": as_of,
            "partial": any(item["status"] != "complete" for item in coverage),
            "warnings": warnings,
            "coverage": coverage,
        },
        "workspace": stable_payload["workspace"],
        "onboarding": onboarding,
        "sources": sources,
        "priority": priority,
        "pulse": pulse,
        "queue": queue,
        "changes": changes,
        "capabilities": capabilities,
        "boundary": stable_payload["boundary"],
        "_checkpoint_fingerprints": checkpoint_fingerprints,
        "_memory_event_sequence": memory_event_window.current_sequence,
    }


async def _read_identity(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> tuple[Workspace, Membership, int]:
    row = (
        await session.execute(
            select(Workspace, Membership)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .join(User, User.id == Membership.user_id)
            .where(
                Workspace.id == workspace_id,
                Membership.user_id == user_id,
                User.status == "active",
            )
        )
    ).one_or_none()
    if row is None:
        raise HeadquartersAccessChangedError("workspace access changed")
    workspace, membership = row
    member_count = int(
        await session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == workspace_id)
        )
        or 0
    )
    return workspace, membership, member_count


async def _read_company_memory_checkpoint(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> CompanyMemoryCheckpoint | None:
    return await session.scalar(
        select(CompanyMemoryCheckpoint).where(
            CompanyMemoryCheckpoint.workspace_id == workspace_id,
            CompanyMemoryCheckpoint.user_id == user_id,
        )
    )


async def _read_company_memory_event_window(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    checkpoint: CompanyMemoryCheckpoint | None,
) -> CompanyMemoryEventWindow:
    current_sequence = int(
        await session.scalar(
            select(CompanyMemoryEventStream.last_sequence).where(
                CompanyMemoryEventStream.workspace_id == workspace_id
            )
        )
        or 0
    )
    cursor_valid = _checkpoint_event_cursor_valid(
        checkpoint,
        current_sequence=current_sequence,
    )
    if checkpoint is None or not cursor_valid:
        return CompanyMemoryEventWindow(
            current_sequence=current_sequence,
            resolved_rows=[],
            resolved_total=0,
            cursor_valid=cursor_valid,
        )

    resolved_filter = (
        CompanyMemoryEvent.workspace_id == workspace_id,
        CompanyMemoryEvent.workspace_sequence > checkpoint.last_event_sequence,
        or_(
            CompanyMemoryEvent.lifecycle_state == COMPANY_MEMORY_LIFECYCLE_RESOLVED,
            CompanyMemoryEvent.event_type
            == COMPANY_MEMORY_EVENT_SOURCE_RECORD_RESTORED,
        ),
    )
    resolved_total = int(
        await session.scalar(
            select(func.count())
            .select_from(CompanyMemoryEvent)
            .where(*resolved_filter)
        )
        or 0
    )
    resolved_rows = list(
        (
            await session.execute(
                select(CompanyMemoryEvent)
                .where(*resolved_filter)
                .order_by(CompanyMemoryEvent.workspace_sequence.desc())
                .limit(HEADQUARTERS_TEMPORAL_EVENT_LIMIT)
            )
        ).scalars()
    )
    return CompanyMemoryEventWindow(
        current_sequence=current_sequence,
        resolved_rows=resolved_rows,
        resolved_total=resolved_total,
        cursor_valid=True,
    )


async def _read_sources(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    role: str,
    as_of: datetime,
) -> tuple[
    dict[str, Any],
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
    int,
]:
    connection_summary_rows = (
        await session.execute(
            select(
                IntegrationConnection.provider,
                func.count(IntegrationConnection.id).label("active_count"),
                func.max(IntegrationConnection.last_sync_at).label("last_sync_at"),
                func.max(IntegrationConnection.updated_at).label("watermark_at"),
                func.bool_or(
                    IntegrationConnection.status == INTEGRATION_CONNECTION_STATUS_ERROR
                ).label("has_error"),
            )
            .where(
                IntegrationConnection.workspace_id == workspace_id,
                IntegrationConnection.status.in_(ACTIVE_CONNECTION_STATUSES),
            )
            .group_by(IntegrationConnection.provider)
            .order_by(IntegrationConnection.provider.asc())
        )
    ).all()
    latest_connection_rows = (
        await session.execute(
            select(
                IntegrationConnection.id,
                IntegrationConnection.provider,
                IntegrationConnection.status,
                IntegrationConnection.display_name,
                IntegrationConnection.scopes,
                IntegrationConnection.last_sync_at,
                IntegrationConnection.updated_at,
            )
            .where(
                IntegrationConnection.workspace_id == workspace_id,
                IntegrationConnection.status.in_(ACTIVE_CONNECTION_STATUSES),
            )
            .distinct(IntegrationConnection.provider)
            .order_by(
                IntegrationConnection.provider.asc(),
                IntegrationConnection.updated_at.desc(),
                IntegrationConnection.id.desc(),
            )
        )
    ).all()
    job_summary_rows = (
        await session.execute(
            select(
                SyncJob.provider,
                func.count(SyncJob.id).label("job_count"),
                func.max(SyncJob.finished_at)
                .filter(SyncJob.status.in_({SYNC_JOB_STATUS_SUCCEEDED, SYNC_JOB_STATUS_PARTIAL}))
                .label("last_success_at"),
                func.max(SyncJob.updated_at).label("watermark_at"),
            )
            .join(
                IntegrationConnection,
                IntegrationConnection.id == SyncJob.connection_id,
            )
            .where(
                SyncJob.workspace_id == workspace_id,
                IntegrationConnection.workspace_id == workspace_id,
                SyncJob.provider == IntegrationConnection.provider,
                IntegrationConnection.status.in_(ACTIVE_CONNECTION_STATUSES),
            )
            .group_by(SyncJob.provider)
            .order_by(SyncJob.provider.asc())
        )
    ).all()
    latest_job_rows = (
        await session.execute(
            select(
                SyncJob.id,
                SyncJob.connection_id,
                SyncJob.provider,
                SyncJob.status,
                SyncJob.started_at,
                SyncJob.finished_at,
                SyncJob.records_seen,
                SyncJob.created_at,
                SyncJob.updated_at,
            )
            .join(
                IntegrationConnection,
                IntegrationConnection.id == SyncJob.connection_id,
            )
            .where(
                SyncJob.workspace_id == workspace_id,
                IntegrationConnection.workspace_id == workspace_id,
                SyncJob.provider == IntegrationConnection.provider,
                IntegrationConnection.status.in_(ACTIVE_CONNECTION_STATUSES),
            )
            .distinct(SyncJob.provider)
            .order_by(
                SyncJob.provider.asc(),
                SyncJob.created_at.desc(),
                SyncJob.id.desc(),
            )
        )
    ).all()
    record_summary_rows = (
        await session.execute(
            select(
                SourceRecord.provider,
                func.count(SourceRecord.id)
                .filter(SourceRecord.is_deleted.is_(False))
                .label("record_count"),
                func.count(SourceRecord.id).label("row_count"),
                func.count(SourceRecord.id)
                .filter(SourceRecord.is_deleted.is_(True))
                .label("deleted_count"),
                func.max(SourceRecord.observed_at)
                .filter(SourceRecord.is_deleted.is_(False))
                .label("observed_at"),
                func.max(SourceRecord.source_updated_at)
                .filter(SourceRecord.is_deleted.is_(False))
                .label("source_updated_at"),
                func.coalesce(
                    func.sum(
                        func.hashtextextended(
                            func.concat(
                                SourceRecord.id,
                                ":",
                                SourceRecord.payload_hash,
                                ":",
                                SourceRecord.is_deleted,
                            ),
                            0,
                        )
                    ),
                    0,
                ).label("content_checksum"),
            )
            .where(SourceRecord.workspace_id == workspace_id)
            .group_by(SourceRecord.provider)
            .order_by(SourceRecord.provider.asc())
        )
    ).all()

    connection_summaries = {row.provider: row for row in connection_summary_rows}
    latest_connections = {row.provider: row for row in latest_connection_rows}
    job_summaries = {row.provider: row for row in job_summary_rows}
    latest_jobs = {row.provider: row for row in latest_job_rows}
    record_summaries = {row.provider: row for row in record_summary_rows}

    can_manage = role_allows(role, MEMBERSHIP_ROLE_ADMIN)
    items: list[dict[str, Any]] = []
    evidence_by_provider: dict[str, list[dict[str, Any]]] = {}
    for descriptor in CONNECTOR_DESCRIPTORS:
        provider = descriptor.provider
        connection_summary = connection_summaries.get(provider)
        connection = latest_connections.get(provider)
        active_connection_count = int(
            connection_summary.active_count if connection_summary is not None else 0
        )
        configuration = "configured" if active_connection_count else "disconnected"
        latest_job = latest_jobs.get(provider)
        job_summary = job_summaries.get(provider)
        record_state = record_summaries.get(provider)
        record_count = int(record_state.record_count if record_state is not None else 0)

        if latest_job is not None and latest_job.status in {
            SYNC_JOB_STATUS_QUEUED,
            SYNC_JOB_STATUS_RUNNING,
        }:
            read_state = "running"
        elif latest_job is not None and latest_job.status == SYNC_JOB_STATUS_FAILED:
            read_state = "failed"
        elif latest_job is not None and latest_job.status in {
            SYNC_JOB_STATUS_SUCCEEDED,
            SYNC_JOB_STATUS_PARTIAL,
        }:
            read_state = "succeeded"
        elif connection_summary is not None and bool(connection_summary.has_error):
            read_state = "failed"
        else:
            read_state = "idle"

        if latest_job is not None and latest_job.status == SYNC_JOB_STATUS_PARTIAL:
            data_state = "partial"
        elif record_count > 0:
            data_state = "available"
        else:
            data_state = "empty"

        successful_times = [
            value
            for value in [
                connection_summary.last_sync_at if connection_summary is not None else None,
                job_summary.last_success_at if job_summary is not None else None,
            ]
            if isinstance(value, datetime)
        ]
        last_success_at = max(successful_times) if successful_times else None
        last_data_observed_at = record_state.observed_at if record_state is not None else None
        fresh_until = (
            _as_utc(last_data_observed_at) + SOURCE_FRESHNESS_THRESHOLD
            if isinstance(last_data_observed_at, datetime)
            else None
        )
        if record_count == 0 or last_data_observed_at is None:
            freshness = "unknown"
        elif as_of > fresh_until:
            freshness = "stale"
        else:
            freshness = "fresh"

        if read_state == "failed":
            primary_state = "failed"
            attention_reason = "read_failed"
            blocker = "Последняя попытка чтения не завершилась успешно."
        elif data_state == "partial":
            primary_state = "partial"
            attention_reason = "partial_data"
            blocker = "Источник вернул только часть ожидаемых данных."
        elif freshness == "stale":
            primary_state = "stale"
            attention_reason = "stale_data"
            blocker = "Данные старше допустимого окна свежести."
        elif data_state == "empty" and configuration == "configured":
            primary_state = "no_data"
            attention_reason = "no_data"
            blocker = "Источник настроен, но канонические записи ещё не получены."
        elif data_state in {"available", "partial"}:
            primary_state = "healthy"
            attention_reason = None
            blocker = None
        else:
            primary_state = "setup"
            attention_reason = None
            blocker = None

        last_attempt_at = None
        if latest_job is not None:
            last_attempt_at = latest_job.started_at or latest_job.created_at
        scopes = sorted(
            {
                scope.strip()
                for scope in ((connection.scopes or []) if connection is not None else [])
                if isinstance(scope, str) and scope.strip()
            }
        )
        debug_ids = [str(connection.id)] if connection is not None else []
        if latest_job is not None:
            debug_ids.append(str(latest_job.id))
        debug_material = f"{provider}:{':'.join(debug_ids)}"
        safe_debug_id = (
            f"src_{sha256(debug_material.encode()).hexdigest()[:16]}" if debug_ids else None
        )
        next_action = _source_action(
            provider=provider,
            name=descriptor.name,
            target=descriptor.manage_path,
            primary_state=("setup" if configuration == "disconnected" else primary_state),
            enabled=can_manage,
        )
        items.append(
            {
                "key": provider,
                "name": descriptor.name,
                "configuration": configuration,
                "read": read_state,
                "data": data_state,
                "freshness": freshness,
                "primary_state": primary_state,
                "attention_reason": attention_reason,
                "scopes": scopes,
                "last_success_at": last_success_at,
                "last_attempt_at": last_attempt_at,
                "last_data_observed_at": last_data_observed_at,
                "fresh_until": fresh_until,
                "freshness_policy_version": HEADQUARTERS_SOURCE_HEALTH_VERSION,
                "connection_count": active_connection_count,
                "connection_count_precision": "exact",
                "record_count": record_count,
                "record_count_precision": "exact",
                "blocker": blocker,
                "safe_debug_id": safe_debug_id,
                "next_action": next_action,
            }
        )

        source_evidence: list[dict[str, Any]] = []
        if configuration == "configured" and primary_state in {
            "failed",
            "partial",
            "stale",
            "no_data",
        }:
            health_basis = {
                "provider": provider,
                "state": primary_state,
                "active_connections": active_connection_count,
                "has_connection_error": bool(
                    connection_summary.has_error if connection_summary is not None else False
                ),
                "latest_job_id": latest_job.id if latest_job is not None else None,
                "latest_job_status": (latest_job.status if latest_job is not None else None),
                "record_count": record_count,
                "last_data_observed_at": last_data_observed_at,
                "fresh_until": fresh_until,
            }
            source_evidence = [
                _aggregate_evidence(
                    identity=(
                        f"source_inventory:{workspace_id}:{provider}:{_digest(health_basis)[:16]}"
                    ),
                    label=f"{descriptor.name}: вычисленное состояние {primary_state}",
                    target=descriptor.manage_path or "/settings/integrations",
                    source_key=provider,
                )
            ]
        evidence_by_provider[provider] = source_evidence

    healthy = sum(1 for item in items if item["primary_state"] == "healthy")
    configured_count = sum(1 for item in items if item["configuration"] == "configured")
    data_ready_count = sum(1 for item in items if item["data"] in {"available", "partial"})
    attention_count = sum(
        1
        for item in items
        if item["configuration"] == "configured"
        and item["primary_state"] in {"failed", "partial", "stale", "no_data"}
    )
    sources = {
        "healthy": healthy,
        "total": len(items),
        "configured_count": configured_count,
        "data_ready_count": data_ready_count,
        "attention_count": attention_count,
        "count_precision": "exact",
        "items": items,
    }
    material = {
        "rule_version": HEADQUARTERS_SOURCE_HEALTH_VERSION,
        "connections": [
            {
                "provider": provider,
                "active_count": int(summary.active_count),
                "has_error": bool(summary.has_error),
                "last_sync_at": summary.last_sync_at,
                "watermark_at": summary.watermark_at,
                "latest_id": latest_connections[provider].id,
                "latest_status": latest_connections[provider].status,
            }
            for provider, summary in sorted(connection_summaries.items())
        ],
        "jobs": [
            {
                "provider": provider,
                "job_count": int(summary.job_count),
                "last_success_at": summary.last_success_at,
                "watermark_at": summary.watermark_at,
                "latest_id": latest_jobs[provider].id,
                "latest_status": latest_jobs[provider].status,
                "latest_updated_at": latest_jobs[provider].updated_at,
            }
            for provider, summary in sorted(job_summaries.items())
        ],
        "records": [
            {
                "provider": row.provider,
                "record_count": int(row.record_count),
                "row_count": int(row.row_count),
                "deleted_count": int(row.deleted_count),
                "observed_at": row.observed_at,
                "source_updated_at": row.source_updated_at,
                "content_checksum": str(row.content_checksum),
            }
            for row in record_summary_rows
        ],
        "derived": items,
    }
    canonical_source_record_count = sum(int(row.record_count) for row in record_summary_rows)
    return sources, evidence_by_provider, material, canonical_source_record_count


async def _read_decision_rows(
    *,
    session: AsyncSession,
    workspace_id: UUID,
) -> DecisionRows:
    payload_octets = func.octet_length(ActionProposal.payload.cast(Text))
    evidence_refs_octets = func.octet_length(ActionProposal.evidence_refs.cast(Text))
    oversized_json = or_(
        payload_octets > ACTION_PROPOSAL_PAYLOAD_MAX_BYTES,
        evidence_refs_octets > ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES,
    )
    action_summary = (
        await session.execute(
            select(
                func.count(ActionProposal.id)
                .filter(ActionProposal.status == ACTION_PROPOSAL_STATUS_PROPOSED)
                .label("proposed_count"),
                func.count(ActionProposal.id)
                .filter(ActionProposal.status != ACTION_PROPOSAL_STATUS_PROPOSED)
                .label("decided_count"),
                func.count(ActionProposal.id)
                .filter(
                    ActionProposal.status == ACTION_PROPOSAL_STATUS_PROPOSED,
                    oversized_json,
                )
                .label("oversized_proposal_count"),
                func.max(ActionProposal.updated_at).label("latest_updated_at"),
            ).where(ActionProposal.workspace_id == workspace_id)
        )
    ).one()
    proposals = list(
        (
            await session.execute(
                select(ActionProposal)
                .where(
                    ActionProposal.workspace_id == workspace_id,
                    ActionProposal.status == ACTION_PROPOSAL_STATUS_PROPOSED,
                    payload_octets <= ACTION_PROPOSAL_PAYLOAD_MAX_BYTES,
                    evidence_refs_octets <= ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES,
                )
                .order_by(ActionProposal.updated_at.desc(), ActionProposal.id.asc())
                .limit(HEADQUARTERS_PROPOSAL_SCAN_LIMIT)
            )
        ).scalars()
    )
    briefing_count = int(
        await session.scalar(
            select(func.count()).select_from(Briefing).where(Briefing.workspace_id == workspace_id)
        )
        or 0
    )
    latest_briefing = (
        await session.execute(
            select(Briefing)
            .where(Briefing.workspace_id == workspace_id)
            .order_by(Briefing.created_at.desc(), Briefing.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    proposed_total = int(action_summary.proposed_count or 0)
    oversized_proposal_count = int(action_summary.oversized_proposal_count or 0)
    eligible_proposal_count = proposed_total - oversized_proposal_count
    return DecisionRows(
        proposals=proposals,
        proposed_total=proposed_total,
        oversized_proposal_count=oversized_proposal_count,
        proposals_truncated=eligible_proposal_count > len(proposals),
        latest_proposal_updated_at=action_summary.latest_updated_at,
        briefing_count=briefing_count,
        decided_proposal_count=int(action_summary.decided_count or 0),
        latest_briefing=latest_briefing,
    )


async def _verify_proposals(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    proposals: list[ActionProposal],
) -> list[VerifiedProposal]:
    briefing_item_ids = {
        proposal.briefing_item_id for proposal in proposals if proposal.briefing_item_id is not None
    }
    briefing_items: dict[UUID, BriefingItem] = {}
    if briefing_item_ids:
        rows = (
            await session.execute(
                select(BriefingItem)
                .join(Briefing, Briefing.id == BriefingItem.briefing_id)
                .where(
                    Briefing.workspace_id == workspace_id,
                    BriefingItem.id.in_(briefing_item_ids),
                )
            )
        ).scalars()
        briefing_items = {item.id: item for item in rows}

    proposal_refs = {
        proposal.id: refs
        for proposal in proposals
        if (refs := _strict_evidence_refs(proposal.evidence_refs)) is not None
    }
    direct_refs = [ref for refs in proposal_refs.values() for ref in refs]
    resolver = await _build_direct_evidence_resolver(
        session=session,
        workspace_id=workspace_id,
        refs=direct_refs,
    )

    verified: list[VerifiedProposal] = []
    for proposal in proposals:
        raw_refs = proposal_refs.get(proposal.id)
        if raw_refs is None:
            continue
        linked_item = briefing_items.get(proposal.briefing_item_id)
        resolved_refs = [
            resolved
            for ref in raw_refs
            if (resolved := _resolve_direct_evidence(ref, resolver)) is not None
        ]
        if not raw_refs or len(resolved_refs) != len(raw_refs):
            continue
        if not _proposal_evidence_is_relevant(proposal, resolved_refs):
            continue
        linked_item_refs = (
            _strict_evidence_refs(linked_item.evidence_refs) if linked_item is not None else None
        )
        trusted_item = (
            linked_item
            if linked_item is not None
            and linked_item_refs is not None
            and proposal.created_by == ACTION_CREATED_BY_SYSTEM
            and proposal.created_by_user_id is None
            and _evidence_material(raw_refs) == _evidence_material(linked_item_refs)
            else None
        )
        evidence_refs = _dedupe_evidence([resolved.evidence for resolved in resolved_refs])
        if evidence_refs:
            verified.append(
                VerifiedProposal(
                    proposal=proposal,
                    evidence_refs=evidence_refs,
                    trusted_briefing_item=trusted_item,
                )
            )
    return verified


async def validate_action_proposal_evidence(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    proposal: ActionProposal,
) -> list[ResolvedEvidence]:
    """Require every proposal reference to resolve to relevant workspace data."""

    if proposal.workspace_id != workspace_id:
        raise ActionProposalEvidenceValidationError(
            "proposal evidence belongs to another workspace"
        )
    refs = _strict_evidence_refs(proposal.evidence_refs)
    if refs is None:
        raise ActionProposalEvidenceValidationError(
            "proposal evidence_refs do not match the strict evidence schema"
        )
    resolver = await _build_direct_evidence_resolver(
        session=session,
        workspace_id=workspace_id,
        refs=refs,
    )
    resolved_refs = [
        resolved
        for ref in refs
        if (resolved := _resolve_direct_evidence(ref, resolver)) is not None
    ]
    if len(resolved_refs) != len(refs):
        raise ActionProposalEvidenceValidationError(
            "proposal evidence is missing, inactive, unsupported, or outside the workspace"
        )
    if not _proposal_evidence_is_relevant(proposal, resolved_refs):
        raise ActionProposalEvidenceValidationError(
            "proposal evidence is unrelated to the requested action"
        )
    return resolved_refs


async def _build_direct_evidence_resolver(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    refs: list[Mapping[str, Any]],
) -> dict[str, Any]:
    tokens = {token for ref in refs for token in _evidence_tokens(ref) if token}
    uuid_tokens = {_uuid_or_none(token) for token in tokens}
    uuid_tokens.discard(None)

    source_records: list[Any] = []
    repositories: list[Any] = []
    connections: list[Any] = []
    evidence_rows: list[Any] = []
    if tokens or uuid_tokens:
        source_records = (
            await session.execute(
                select(
                    SourceRecord.id,
                    SourceRecord.provider,
                    SourceRecord.external_id,
                    SourceRecord.record_type,
                    SourceRecord.source_url,
                    SourceRecord.payload_hash,
                    SourceRecord.observed_at,
                ).where(
                    SourceRecord.workspace_id == workspace_id,
                    SourceRecord.is_deleted.is_(False),
                    or_(
                        SourceRecord.id.in_(uuid_tokens),
                        SourceRecord.external_id.in_(tokens),
                    ),
                )
            )
        ).all()
        repositories = (
            await session.execute(
                select(
                    Repository.id,
                    Repository.provider,
                    Repository.full_name,
                    Repository.source_url,
                    Repository.archived,
                    Repository.updated_at,
                ).where(
                    Repository.workspace_id == workspace_id,
                    Repository.archived.is_(False),
                    or_(Repository.id.in_(uuid_tokens), Repository.full_name.in_(tokens)),
                )
            )
        ).all()
        connections = (
            await session.execute(
                select(
                    IntegrationConnection.id,
                    IntegrationConnection.provider,
                    IntegrationConnection.display_name,
                    IntegrationConnection.status,
                    IntegrationConnection.scopes,
                    IntegrationConnection.updated_at,
                ).where(
                    IntegrationConnection.workspace_id == workspace_id,
                    IntegrationConnection.id.in_(uuid_tokens),
                    IntegrationConnection.status.in_(ACTIVE_CONNECTION_STATUSES),
                )
            )
        ).all()
        evidence_rows = (
            await session.execute(
                select(
                    EvidenceRef.id,
                    SourceRecord.id.label("source_record_id"),
                    SourceRecord.provider,
                    SourceRecord.external_id,
                    SourceRecord.record_type,
                    SourceRecord.source_url,
                    SourceRecord.payload_hash,
                    SourceRecord.observed_at,
                    EvidenceRef.field_path,
                    EvidenceRef.confidence,
                    EvidenceRef.source_url.label("evidence_source_url"),
                    EvidenceRef.created_at.label("evidence_created_at"),
                    func.md5(func.coalesce(EvidenceRef.quote, "")).label("quote_hash"),
                )
                .join(SourceRecord, SourceRecord.id == EvidenceRef.source_record_id)
                .where(
                    EvidenceRef.workspace_id == workspace_id,
                    SourceRecord.workspace_id == workspace_id,
                    SourceRecord.is_deleted.is_(False),
                    EvidenceRef.id.in_(uuid_tokens),
                )
            )
        ).all()

    return {
        "source_by_id": {str(row.id): row for row in source_records},
        "source_by_external": {(row.provider, row.external_id): row for row in source_records},
        "repository_by_id": {str(row.id): row for row in repositories},
        "repository_by_name": {row.full_name: row for row in repositories},
        "connection_by_id": {str(row.id): row for row in connections},
        "evidence_by_id": {str(row.id): row for row in evidence_rows},
    }


def _resolve_direct_evidence(
    ref: Mapping[str, Any],
    resolver: Mapping[str, Any],
) -> ResolvedEvidence | None:
    if not _source_alias_is_supported(ref.get("source")):
        return None
    selector = _evidence_selector(ref)
    if selector is None:
        return None
    source_hint = _source_key(ref.get("source"))
    token = selector.token

    # An explicit EvidenceRef selector is exact-grain: if it is missing,
    # foreign, deleted, provider-mismatched, or contradicts a supplied source
    # record id, do not silently fall back to a looser ref/name.
    if selector.kind == "evidence_ref":
        row = resolver["evidence_by_id"].get(token)
        if row is None or not _provider_matches_source_hint(row.provider, source_hint):
            return None
        if selector.source_record_tokens and any(
            value != str(row.source_record_id) for value in selector.source_record_tokens
        ):
            return None
        return _resolved_source_record_evidence(row, evidence_ref=True)

    if selector.kind == "source_record":
        row = resolver["source_by_id"].get(token)
        if row is None or not _provider_matches_source_hint(row.provider, source_hint):
            return None
        return _resolved_source_record_evidence(row)

    if row := resolver["evidence_by_id"].get(token):
        if _provider_matches_source_hint(row.provider, source_hint):
            return _resolved_source_record_evidence(row, evidence_ref=True)
        return None
    if row := resolver["source_by_id"].get(token):
        if _provider_matches_source_hint(row.provider, source_hint):
            return _resolved_source_record_evidence(row)
        return None
    if source_hint and (row := resolver["source_by_external"].get((source_hint, token))):
        return _resolved_source_record_evidence(row)
    if row := resolver["repository_by_id"].get(token):
        if _provider_matches_source_hint(row.provider, source_hint):
            return _resolved_repository_evidence(row)
        return None
    if row := resolver["repository_by_name"].get(token):
        if _provider_matches_source_hint(row.provider, source_hint):
            return _resolved_repository_evidence(row)
        return None
    if row := resolver["connection_by_id"].get(token):
        if _provider_matches_source_hint(row.provider, source_hint):
            return _resolved_connection_evidence(row)
        return None
    return None


def _proposal_evidence_is_relevant(
    proposal: ActionProposal,
    resolved_refs: list[ResolvedEvidence],
) -> bool:
    """Require a GitHub action to cite its exact canonical repository target."""

    if proposal.target_provider != ACTION_TARGET_PROVIDER_GITHUB:
        return True
    payload = proposal.payload if isinstance(proposal.payload, Mapping) else {}
    repository_full_name = _clean_text(payload.get("repository_full_name"))
    if repository_full_name is None:
        return False
    return any(
        resolved.match_kind in {"repository", "repository_source_record"}
        and resolved.match_key is not None
        and resolved.match_key.casefold() == repository_full_name.casefold()
        for resolved in resolved_refs
    )


async def _read_company_world_projection(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    role: str,
) -> dict[str, Any]:
    return await build_workspace_company_map(
        session=session,
        workspace_id=workspace_id,
        limit=100,
        resolution_only=True,
        access_role=role,
    )


def _company_world_source_record_ids(row: Mapping[str, Any]) -> list[UUID]:
    record_ids: set[UUID] = set()
    for ref in _mapping_list(row.get("source_refs")):
        record_id = _uuid_or_none(ref.get("record_id"))
        if record_id is not None:
            record_ids.add(record_id)
    return sorted(record_ids, key=str)


async def _read_company_world_observed_at(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    company_world: Mapping[str, Any],
) -> dict[UUID, datetime]:
    people = company_world.get("people")
    people_projection = people if isinstance(people, Mapping) else {}
    rows = [
        *[
            row
            for row in _mapping_list(
                people_projection.get("external_candidates")
            )
        ],
        *[
            row
            for row in _mapping_list(company_world.get("organizations"))
        ],
    ]
    record_ids = {
        record_id
        for row in rows
        for record_id in _company_world_source_record_ids(row)
    }
    if not record_ids:
        return {}
    observed_rows = (
        await session.execute(
            select(SourceRecord.id, SourceRecord.observed_at).where(
                SourceRecord.workspace_id == workspace_id,
                SourceRecord.id.in_(record_ids),
                SourceRecord.is_deleted.is_(False),
            )
        )
    ).all()
    return {
        record_id: observed_at
        for record_id, observed_at in observed_rows
        if isinstance(observed_at, datetime)
    }


def _build_mission_candidates(
    *,
    verified_proposals: list[VerifiedProposal],
    sources: Mapping[str, Any],
    source_mission_evidence: Mapping[str, list[dict[str, Any]]],
    company_world: Mapping[str, Any] | None,
    company_world_observed_at: Mapping[UUID, datetime],
    briefing_count: int,
    latest_briefing: Briefing | None,
    capabilities: Mapping[str, bool],
    workspace_id: UUID,
) -> list[MissionCandidate]:
    candidates: list[MissionCandidate] = []
    for verified in verified_proposals:
        item = verified.trusted_briefing_item
        severity = _trusted_severity(item.severity if item is not None else None)
        score = 500 + SEVERITY_RANK.get(severity, 0)
        action_enabled = bool(capabilities["can_review_proposal"])
        proposal = verified.proposal
        proposal_version = action_proposal_version(proposal)
        proposal_source_keys = _evidence_source_keys(verified.evidence_refs)
        proposal_correlation = (
            "same_persisted_briefing_item_evidence"
            if item is not None and len(proposal_source_keys) > 1
            else None
        )
        candidates.append(
            MissionCandidate(
                mission=_mission(
                    identity=f"proposal:{proposal.id}",
                    kind="review_proposal",
                    reference_type="proposal",
                    reference_id=str(proposal.id),
                    title=_clean_text(proposal.title) or "Решение без названия",
                    summary=(
                        _clean_text(proposal.description)
                        or "Предложение ожидает решения основателя."
                    ),
                    why_now="Предложение ожидает решения и имеет проверяемое основание.",
                    status="proposed",
                    severity=severity,
                    confidence=(_bounded_confidence(item.confidence) if item is not None else None),
                    next_step="Открыть предложение, проверить доказательства и принять решение.",
                    source_keys=proposal_source_keys,
                    evidence_refs=verified.evidence_refs,
                    proposal_id=proposal.id,
                    action=_action(
                        kind="review_proposal",
                        label="Рассмотреть решение" if action_enabled else "Открыть решение",
                        target=f"/actions?proposal={proposal.id}&status=proposed",
                        enabled=action_enabled,
                        disabled_reason=(
                            None
                            if action_enabled
                            else "Для решения нужна роль администратора или владельца."
                        ),
                    ),
                    ranking_reason="verified_proposal",
                    proposal_version=proposal_version,
                    correlation_reason=proposal_correlation,
                    correlation_rule_version=(
                        HEADQUARTERS_CORRELATION_VERSION
                        if proposal_correlation is not None
                        else None
                    ),
                ),
                score=score,
                event_time=proposal.updated_at,
                observed_at=proposal.updated_at,
                change_kind="proposal",
            )
        )

    source_score = {"failed": 460, "partial": 450, "stale": 440, "no_data": 430}
    for source in sources["items"]:
        state = source["primary_state"]
        if source["configuration"] != "configured" or state not in source_score:
            continue
        evidence_refs = source_mission_evidence.get(source["key"], [])
        action = source["next_action"]
        candidates.append(
            MissionCandidate(
                mission=_mission(
                    identity=f"source:{source['key']}:{state}",
                    kind="source_attention",
                    reference_type="source",
                    reference_id=source["key"],
                    title=f"{source['name']} требует внимания",
                    summary=source["blocker"] or "Проверьте состояние источника.",
                    why_now="Без восстановления этого источника картина компании может быть неполной.",
                    status=state,
                    severity="high" if state == "failed" else "medium",
                    confidence=1.0,
                    next_step=action["label"],
                    source_keys=[source["key"]],
                    evidence_refs=evidence_refs,
                    action=action,
                    ranking_reason="configured_source_attention",
                ),
                score=source_score[state],
                event_time=source["last_attempt_at"] or source["last_success_at"],
                observed_at=_latest_datetime_value(
                    source["last_data_observed_at"],
                    source["last_attempt_at"],
                    source["last_success_at"],
                ),
                change_kind="source" if evidence_refs else None,
            )
        )

    candidates.extend(
        _world_mission_candidates(
            company_world=company_world,
            source_record_observed_at=company_world_observed_at,
            workspace_id=workspace_id,
            enabled=bool(capabilities["can_resolve_world"]),
        )
    )

    if sources["data_ready_count"] == 0 and sources["configured_count"] == 0:
        can_manage = bool(capabilities["can_manage_source"])
        aggregate_evidence = [
            _aggregate_evidence(
                identity=f"source_inventory:{workspace_id}:empty",
                label="В текущем снимке нет готовых канонических данных источников",
                target="/settings/integrations",
            )
        ]
        candidates.append(
            MissionCandidate(
                mission=_mission(
                    identity="setup:connect-source",
                    kind="connect_source",
                    reference_type="setup",
                    reference_id="connect-source",
                    title="Подключите первый источник",
                    summary="FounderOS нужен хотя бы один источник данных для полезной картины компании.",
                    why_now="Без данных платформа не может показать реальные решения и связи.",
                    status="setup",
                    severity="info",
                    confidence=1.0,
                    next_step="Открыть настройки и подключить первый источник.",
                    source_keys=[],
                    evidence_refs=aggregate_evidence,
                    action=_action(
                        kind="manage_source",
                        label="Настроить источник" if can_manage else "Открыть настройки",
                        target="/settings/integrations",
                        enabled=can_manage,
                        disabled_reason=(
                            None
                            if can_manage
                            else "Настройку источников выполняет администратор или владелец."
                        ),
                    ),
                    ranking_reason="source_setup_gap",
                ),
                score=250,
                event_time=None,
                observed_at=None,
                change_kind=None,
            )
        )
    elif sources["data_ready_count"] > 0 and briefing_count == 0:
        can_generate = bool(capabilities["can_generate_briefing"])
        aggregate_evidence = [
            _aggregate_evidence(
                identity=f"source_inventory:{workspace_id}:ready",
                label="В текущем снимке есть готовые канонические данные",
                target="/briefings",
            )
        ]
        candidates.append(
            MissionCandidate(
                mission=_mission(
                    identity="setup:create-briefing",
                    kind="create_briefing",
                    reference_type="setup",
                    reference_id="create-briefing",
                    title="Соберите первый брифинг",
                    summary="Данные уже готовы; теперь их можно превратить в краткий обзор.",
                    why_now="Первый брифинг проверит, что источники дают полезные сигналы.",
                    status="ready_to_generate",
                    severity="info",
                    confidence=1.0,
                    next_step="Сгенерировать детерминированный брифинг.",
                    source_keys=[
                        item["key"]
                        for item in sources["items"]
                        if item["data"] in {"available", "partial"}
                    ],
                    evidence_refs=aggregate_evidence,
                    action=_action(
                        kind="generate_briefing",
                        label="Создать брифинг" if can_generate else "Открыть брифинги",
                        target="/briefings",
                        enabled=can_generate,
                        disabled_reason=(
                            None
                            if can_generate
                            else "Для генерации нужна роль участника, администратора или владельца."
                        ),
                    ),
                    ranking_reason="briefing_setup_gap",
                ),
                score=200,
                event_time=(latest_briefing.created_at if latest_briefing else None),
                observed_at=(latest_briefing.created_at if latest_briefing else None),
                change_kind=None,
            )
        )
    return candidates


def _world_mission_candidates(
    *,
    company_world: Mapping[str, Any] | None,
    source_record_observed_at: Mapping[UUID, datetime],
    workspace_id: UUID,
    enabled: bool,
) -> list[MissionCandidate]:
    if company_world is None:
        return []
    rows: list[tuple[str, Mapping[str, Any]]] = [
        *[("person", row) for row in company_world["people"]["external_candidates"]],
        *[("organization", row) for row in company_world["organizations"]],
    ]
    candidates: list[MissionCandidate] = []
    for candidate_type, row in rows:
        raw_key = _clean_text(row.get("key"))
        version = _clean_text(row.get("candidate_version"))
        if raw_key is None or version is None:
            continue
        evidence_refs = _company_world_evidence(row.get("source_refs"), candidate_type)
        if not evidence_refs:
            continue
        source_keys = _evidence_source_keys(evidence_refs)
        world_correlation = "same_company_world_candidate_refs" if len(source_keys) > 1 else None
        opaque_selector = sha256(
            f"{workspace_id}:{candidate_type}:{raw_key}".encode("utf-8")
        ).hexdigest()[:32]
        identity = f"world:{candidate_type}:{opaque_selector}:{version}"
        if candidate_type == "person":
            display = _clean_text(row.get("display_name")) or _clean_text(row.get("email"))
            title = f"Уточните связь с {display or 'внешним контактом'}"
            summary = (
                "Контакт найден в подтверждённом соприкосновении, но его роль ещё не определена."
            )
        else:
            display = _clean_text(row.get("name")) or _clean_text(row.get("domain"))
            title = f"Уточните компанию {display or 'из нового контакта'}"
            summary = "Организация обнаружена по соприкосновениям, но её отношение к компании не подтверждено."
        action = _action(
            kind="resolve_world",
            label="Разобрать связь" if enabled else "Открыть карту",
            target=_company_world_profile_target(
                candidate_type=candidate_type,
                candidate_version=version,
            ),
            enabled=enabled,
            disabled_reason=(
                None if enabled else "Для подтверждения связи нужна роль участника или выше."
            ),
        )
        candidates.append(
            MissionCandidate(
                mission=_mission(
                    identity=identity,
                    kind="review_world",
                    reference_type="world",
                    reference_id=f"{candidate_type}:{opaque_selector}:{version}",
                    title=title,
                    summary=summary,
                    why_now="Связь подтверждается источником, но ещё не стала фактом Company World.",
                    status="unresolved",
                    severity="medium",
                    confidence=None,
                    next_step="Проверить профиль и подтвердить либо отклонить связь.",
                    source_keys=source_keys,
                    evidence_refs=evidence_refs,
                    action=action,
                    ranking_reason="evidence_backed_relationship",
                    correlation_reason=world_correlation,
                    correlation_rule_version=(
                        HEADQUARTERS_CORRELATION_VERSION if world_correlation is not None else None
                    ),
                ),
                score=350,
                event_time=_datetime_or_none(row.get("last_interaction_at")),
                observed_at=_latest_datetime_value(
                    *[
                        source_record_observed_at[record_id]
                        for record_id in _company_world_source_record_ids(row)
                        if record_id in source_record_observed_at
                    ]
                ),
                change_kind="relationship",
            )
        )
    return candidates


def _company_world_profile_target(
    *,
    candidate_type: str,
    candidate_version: str,
) -> str:
    selector_kind = "person-candidate" if candidate_type == "person" else "organization-candidate"
    query = urlencode({"profile": f"v1:{selector_kind}:{candidate_version}"})
    return f"/company-brain?{query}#company-world-profile"


def _build_pulse(
    *,
    verified_proposal_count: int,
    verified_proposal_count_is_lower_bound: bool,
    sources: Mapping[str, Any],
    company_world: Mapping[str, Any] | None,
    company_world_status: str,
    capabilities: Mapping[str, bool],
) -> list[dict[str, Any]]:
    sources_attention = int(sources["attention_count"])
    if company_world is None:
        relationship_value = None
        relationship_precision = "unavailable"
    else:
        relationship_value = len(company_world["people"]["external_candidates"]) + len(
            company_world["organizations"]
        )
        relationship_precision = "at_least" if company_world_status == "partial" else "exact"
    return [
        {
            "key": "waiting_decisions",
            "label": "Ждут решения",
            "value": verified_proposal_count,
            "precision": ("at_least" if verified_proposal_count_is_lower_bound else "exact"),
            "empty_state": (
                "Проверено только ограниченное окно решений; полный список откройте отдельно."
                if verified_proposal_count_is_lower_bound
                else "Нет предложений с проверяемыми доказательствами."
            ),
            "target": "/actions?status=proposed",
            "action": _action(
                kind="review_proposals",
                label="Открыть решения",
                target="/actions?status=proposed",
                enabled=True,
            ),
        },
        {
            "key": "sources_attention",
            "label": "Источники требуют внимания",
            "value": sources_attention,
            "precision": "exact",
            "empty_state": "Настроенные источники не требуют внимания.",
            "target": "/settings/integrations",
            "action": _action(
                kind="manage_sources",
                label="Открыть настройки",
                target="/settings/integrations",
                enabled=True,
            ),
        },
        {
            "key": "pending_relationships",
            "label": "Связи на проверку",
            "value": relationship_value,
            "precision": relationship_precision,
            "empty_state": "Нет подтверждённых источником связей на проверку.",
            "target": "/company-brain",
            "action": _action(
                kind="review_world",
                label="Открыть карту компании",
                target="/company-brain",
                enabled=True,
            ),
        },
    ]


def _temporal_candidate_fingerprint(candidate: MissionCandidate) -> str:
    mission = candidate.mission
    return _digest(
        {
            "id": mission["id"],
            "kind": candidate.change_kind,
            "title": mission["title"],
            "summary": mission["summary"],
            "event_time": candidate.event_time,
            "observed_at": candidate.observed_at,
            "confidence": mission["confidence"],
            "source_keys": mission["source_keys"],
            "evidence": [
                {
                    "id": ref["id"],
                    "reference_id": ref["reference_id"],
                    "reference_type": ref["reference_type"],
                }
                for ref in mission["evidence_refs"]
            ],
            "target": mission["action"]["target"],
        }
    )


def _temporal_candidate_sort_key(
    candidate: MissionCandidate,
) -> tuple[float, float, str]:
    observed_at = candidate.observed_at
    event_time = candidate.event_time
    observed_timestamp = (
        _as_utc(observed_at).timestamp()
        if isinstance(observed_at, datetime)
        else float("-inf")
    )
    event_timestamp = (
        _as_utc(event_time).timestamp()
        if isinstance(event_time, datetime)
        else float("-inf")
    )
    return (-observed_timestamp, -event_timestamp, candidate.mission["id"])


async def _build_resolved_memory_event_items(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    events: list[CompanyMemoryEvent],
) -> list[dict[str, Any]]:
    proposal_ids = {
        event.subject_id
        for event in events
        if event.subject_type == "action_proposal"
    }
    proposals: dict[UUID, ActionProposal] = {}
    if proposal_ids:
        rows = (
            await session.execute(
                select(ActionProposal).where(
                    ActionProposal.workspace_id == workspace_id,
                    ActionProposal.id.in_(proposal_ids),
                )
            )
        ).scalars()
        proposals = {proposal.id: proposal for proposal in rows}
    source_record_ids = {
        event.subject_id
        for event in events
        if event.subject_type == "source_record"
    }
    source_records: dict[UUID, SourceRecord] = {}
    if source_record_ids:
        rows = (
            await session.execute(
                select(SourceRecord).where(
                    SourceRecord.workspace_id == workspace_id,
                    SourceRecord.id.in_(source_record_ids),
                )
            )
        ).scalars()
        source_records = {source_record.id: source_record for source_record in rows}

    items: list[dict[str, Any]] = []
    for event in events:
        target = "/company-brain"
        kind = "relationship"
        change_type = "resolved"
        if event.event_type in {
            COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_APPROVED,
            COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_REJECTED,
        }:
            proposal = proposals.get(event.subject_id)
            proposal_title = (
                _clean_text(proposal.title) if proposal is not None else None
            ) or "Предложение действия"
            target = f"/actions?proposal={event.subject_id}"
            kind = "proposal"
            if event.event_type == COMPANY_MEMORY_EVENT_ACTION_PROPOSAL_APPROVED:
                title = f"Одобрено: {proposal_title}"
                summary = (
                    "Предложение одобрено локально. "
                    "Внешнее действие не запускалось."
                )
            else:
                title = f"Отклонено: {proposal_title}"
                summary = (
                    "Предложение отклонено и больше не ожидает решения."
            )
        elif event.event_type in {
            COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED,
            COMPANY_MEMORY_EVENT_COMPANY_WORLD_DISMISSED,
        }:
            is_person = event.subject_type == "external_person_candidate"
            if event.event_type == COMPANY_MEMORY_EVENT_COMPANY_WORLD_CONFIRMED:
                title = (
                    "Контакт подтверждён"
                    if is_person
                    else "Организация подтверждена"
                )
                summary = (
                    "Решение сохранено в канонической карте компании."
                )
            else:
                title = (
                    "Контакт отклонён"
                    if is_person
                    else "Организация отклонена"
                )
                summary = (
                    "Кандидат закрыт и больше не требует проверки."
                )
        elif event.event_type in {
            COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED,
            COMPANY_MEMORY_EVENT_SOURCE_RECORD_RESTORED,
        }:
            source_record = source_records.get(event.subject_id)
            label = _source_record_memory_label(source_record)
            target = (
                _safe_url(source_record.source_url)
                if source_record is not None
                else None
            ) or "/company-brain"
            kind = "source"
            if (
                event.event_type
                == COMPANY_MEMORY_EVENT_SOURCE_RECORD_DISAPPEARED
            ):
                title = f"Источник исчез: {label}"
                summary = (
                    "GitHub больше не возвращает объект в полном снимке "
                    "репозитория. Он скрыт из актуальной картины."
                )
            else:
                title = f"Источник вернулся: {label}"
                summary = (
                    "GitHub снова вернул объект; актуальная проекция "
                    "восстановлена."
                )
                change_type = "new_or_changed"
        else:
            continue
        items.append(
            {
                "id": f"memory-event:{event.id}",
                "kind": kind,
                "change_type": change_type,
                "title": title,
                "summary": summary,
                "event_time": event.occurred_at,
                "observed_at": event.observed_at,
                "confidence": event.confidence,
                "confidence_precision": "exact",
                "source_keys": [event.source_key],
                "evidence_refs": [
                    _memory_event_evidence(event=event, target=target)
                ],
                "target": target,
                "access_scope": event.access_scope,
                "retention": event.retention_policy,
            }
        )
    return items


def _source_record_memory_label(source_record: SourceRecord | None) -> str:
    if source_record is None:
        return "объект GitHub"
    record_type = {
        "issue": "issue",
        "pull_request": "pull request",
        "repository": "репозиторий",
    }.get(source_record.record_type, "объект")
    external_id = _clean_text(source_record.external_id)
    return f"{record_type} {external_id}" if external_id else record_type


def _change_item_sort_key(item: Mapping[str, Any]) -> tuple[float, float, str]:
    observed_at = item.get("observed_at")
    event_time = item.get("event_time")
    observed_timestamp = (
        _as_utc(observed_at).timestamp()
        if isinstance(observed_at, datetime)
        else float("-inf")
    )
    event_timestamp = (
        _as_utc(event_time).timestamp()
        if isinstance(event_time, datetime)
        else float("-inf")
    )
    return (-observed_timestamp, -event_timestamp, str(item.get("id") or ""))


def _checkpoint_event_cursor_valid(
    checkpoint: CompanyMemoryCheckpoint | None,
    *,
    current_sequence: int,
) -> bool:
    if checkpoint is None:
        return True
    return (
        checkpoint.checkpoint_version == COMPANY_MEMORY_CHECKPOINT_VERSION
        and isinstance(checkpoint.last_event_sequence, int)
        and not isinstance(checkpoint.last_event_sequence, bool)
        and 0 <= checkpoint.last_event_sequence <= current_sequence
    )


def _checkpoint_fingerprint_set(
    checkpoint: CompanyMemoryCheckpoint | None,
) -> tuple[set[str], bool]:
    if checkpoint is None:
        return set(), True
    raw = checkpoint.event_fingerprints
    if (
        not isinstance(raw, list)
        or len(raw) > HEADQUARTERS_CHECKPOINT_FINGERPRINT_LIMIT
        or any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in raw
        )
    ):
        return set(), False
    return set(raw), True


def company_memory_checkpoint_cursor(
    checkpoint: CompanyMemoryCheckpoint,
) -> str:
    return (
        "hqc2_"
        + _digest(
            {
                "checkpoint_version": checkpoint.checkpoint_version,
                "event_fingerprints": sorted(checkpoint.event_fingerprints),
                "last_event_sequence": checkpoint.last_event_sequence,
                "observed_through_at": checkpoint.observed_through_at,
                "source_snapshot_id": checkpoint.source_snapshot_id,
            }
        )
    )


def _build_changes(
    ranked: list[MissionCandidate],
    *,
    checkpoint: CompanyMemoryCheckpoint | None,
    partial: bool,
    resolved_items: list[dict[str, Any]],
    resolved_total: int,
    event_cursor_valid: bool,
) -> tuple[dict[str, Any], list[str], bool]:
    temporal_candidates = sorted(
        [
            candidate
            for candidate in ranked
            if candidate.change_kind is not None
            and candidate.observed_at is not None
            and candidate.mission["evidence_refs"]
        ],
        key=_temporal_candidate_sort_key,
    )
    fingerprinted = [
        (candidate, _temporal_candidate_fingerprint(candidate))
        for candidate in temporal_candidates
    ]
    current_fingerprints = sorted({fingerprint for _candidate, fingerprint in fingerprinted})
    if len(current_fingerprints) > HEADQUARTERS_CHECKPOINT_FINGERPRINT_LIMIT:
        raise RuntimeError("temporal checkpoint fingerprint limit exceeded")

    checkpoint_fingerprints, fingerprint_checkpoint_valid = (
        _checkpoint_fingerprint_set(checkpoint)
    )
    checkpoint_valid = fingerprint_checkpoint_valid and event_cursor_valid
    use_checkpoint = checkpoint is not None and checkpoint_valid
    selected = [
        (candidate, fingerprint)
        for candidate, fingerprint in fingerprinted
        if not use_checkpoint or fingerprint not in checkpoint_fingerprints
    ]
    current_items = [
        {
            "id": (
                f"event:{candidate.change_kind}:"
                f"{_digest({'mission_id': candidate.mission['id']})[:24]}"
            ),
            "kind": candidate.change_kind,
            "change_type": "new_or_changed" if use_checkpoint else "current",
            "title": candidate.mission["title"],
            "summary": candidate.mission["summary"],
            "event_time": candidate.event_time,
            "observed_at": candidate.observed_at,
            "confidence": candidate.mission["confidence"],
            "confidence_precision": candidate.mission["confidence_precision"],
            "source_keys": candidate.mission["source_keys"],
            "evidence_refs": candidate.mission["evidence_refs"],
            "target": candidate.mission["action"]["target"] or "/dashboard",
            "access_scope": "workspace",
            "retention": "source_bound",
        }
        for candidate, _fingerprint in selected
    ]
    combined_items = sorted(
        [
            *current_items,
            *(resolved_items if use_checkpoint else []),
        ],
        key=_change_item_sort_key,
    )
    items = combined_items[:HEADQUARTERS_TEMPORAL_EVENT_LIMIT]
    total_count = len(selected) + (resolved_total if use_checkpoint else 0)
    return (
        {
            "contract_version": HEADQUARTERS_TEMPORAL_MEMORY_VERSION,
            "items": items,
            "basis": "checkpoint" if use_checkpoint else "current_snapshot",
            "cursor": (
                company_memory_checkpoint_cursor(checkpoint)
                if use_checkpoint and checkpoint is not None
                else None
            ),
            "checkpointed_at": (
                checkpoint.observed_through_at
                if use_checkpoint and checkpoint is not None
                else None
            ),
            "since_checkpoint": use_checkpoint,
            "total_count": total_count,
            "count_precision": "at_least" if partial else "exact",
            "has_more": total_count > len(items),
        },
        current_fingerprints,
        checkpoint_valid,
    )


def _company_memory_watermark_material(
    *,
    checkpoint: CompanyMemoryCheckpoint | None,
    event_fingerprints: list[str],
    checkpoint_valid: bool,
    current_event_sequence: int,
    resolved_event_count: int,
) -> dict[str, Any]:
    return {
        "contract_version": HEADQUARTERS_TEMPORAL_MEMORY_VERSION,
        "checkpoint_version": (
            checkpoint.checkpoint_version if checkpoint is not None else None
        ),
        "checkpoint_valid": checkpoint_valid,
        "checkpoint_cursor": (
            company_memory_checkpoint_cursor(checkpoint)
            if checkpoint is not None and checkpoint_valid
            else None
        ),
        "current_event_count": len(event_fingerprints),
        "current_event_fingerprint": _digest(event_fingerprints),
        "current_lifecycle_event_sequence": current_event_sequence,
        "resolved_events_since_checkpoint": resolved_event_count,
    }


def _build_onboarding(
    *,
    member_count: int,
    configured_source_count: int | None,
    canonical_source_record_count: int | None,
    briefing_count: int,
    decided_proposal_count: int,
    company_world: Mapping[str, Any] | None,
    company_world_status: str,
    capabilities: Mapping[str, bool],
) -> dict[str, Any]:
    can_manage_team = bool(capabilities["can_manage_team"])
    can_manage_source = bool(capabilities["can_manage_source"])
    can_import_source = bool(capabilities["can_import_source"])
    company_map_summary = (
        company_world.get("summary")
        if company_world_status == "complete" and isinstance(company_world, Mapping)
        else None
    )
    company_map_people = _onboarding_summary_count(
        company_map_summary,
        "external_contacts_in_window",
        "confirmed_external_people",
    )
    company_map_organizations = _onboarding_summary_count(
        company_map_summary,
        "organizations_in_window",
        "confirmed_organizations",
    )
    company_map_touchpoints = _onboarding_summary_count(
        company_map_summary,
        "touchpoints_in_window",
    )
    context_known_complete = any(
        (
            member_count > 1,
            briefing_count > 0,
            decided_proposal_count > 0,
            (company_map_people or 0) > 0,
            (company_map_organizations or 0) > 0,
            (company_map_touchpoints or 0) > 0,
        )
    )
    if context_known_complete:
        context_state = "complete"
    elif company_world_status == "complete":
        context_state = "pending"
    else:
        context_state = "unknown"

    canonical_data_state = _onboarding_count_state(canonical_source_record_count)
    source_state = _onboarding_count_state(configured_source_count)
    steps = [
        {
            "key": "company",
            "requirement": "required",
            "label": "Компания создана",
            "state": "complete",
            "benefit": "Все данные и решения изолированы внутри вашей компании.",
            "evidence": [
                _onboarding_fact(
                    key="workspace_profile",
                    label="Профиль компании",
                    value=1,
                )
            ],
            "action": _action(
                kind="view_workspace",
                label="Открыть компанию",
                target="/dashboard",
                enabled=True,
            ),
        },
        {
            "key": "source",
            "requirement": "recommended",
            "label": "Источник подключён",
            "state": source_state,
            "benefit": "Подключение позволит регулярно обновлять картину компании.",
            "evidence": [
                _onboarding_fact(
                    key="configured_sources",
                    label="Подключённые источники",
                    value=configured_source_count,
                )
            ],
            "action": _action(
                kind="manage_source",
                label=(
                    "Управлять источниками" if source_state == "complete" else "Подключить источник"
                ),
                target="/settings/integrations",
                enabled=can_manage_source,
                disabled_reason=(
                    None
                    if can_manage_source
                    else "Источник настраивает администратор или владелец."
                ),
            ),
        },
        {
            "key": "canonical_data",
            "requirement": "required",
            "label": "Первые данные приняты",
            "state": canonical_data_state,
            "benefit": "FounderOS сможет показывать реальные сигналы, людей и работу.",
            "evidence": [
                _onboarding_fact(
                    key="canonical_records",
                    label="Канонические записи",
                    value=canonical_source_record_count,
                )
            ],
            "action": _action(
                kind=(
                    "view_canonical_data"
                    if canonical_data_state == "complete"
                    else "import_source_data"
                ),
                label=(
                    "Открыть данные"
                    if canonical_data_state == "complete"
                    else "Получить первые данные"
                ),
                target=(
                    "/company-brain"
                    if canonical_data_state == "complete"
                    else "/settings/integrations"
                ),
                enabled=(canonical_data_state == "complete" or can_import_source),
                disabled_reason=(
                    None
                    if canonical_data_state == "complete" or can_import_source
                    else "Импорт запускает администратор или владелец."
                ),
            ),
        },
        {
            "key": "context",
            "requirement": "recommended",
            "label": "Контекст компании наполнен",
            "state": context_state,
            "benefit": "Команда, карта, брифинги и решения делают рекомендации точнее.",
            "evidence": [
                _onboarding_fact(
                    key="team_members",
                    label="Участники команды",
                    value=member_count,
                    complete_at=2,
                ),
                _onboarding_fact(
                    key="company_map_people",
                    label="Люди на карте компании",
                    value=company_map_people,
                ),
                _onboarding_fact(
                    key="company_map_organizations",
                    label="Организации на карте компании",
                    value=company_map_organizations,
                ),
                _onboarding_fact(
                    key="company_map_touchpoints",
                    label="Касания на карте компании",
                    value=company_map_touchpoints,
                ),
                _onboarding_fact(
                    key="briefings",
                    label="Брифинги",
                    value=briefing_count,
                ),
                _onboarding_fact(
                    key="decisions",
                    label="Принятые решения",
                    value=decided_proposal_count,
                ),
            ],
            "action": _action(
                kind="manage_team" if can_manage_team else "view_company_map",
                label="Настроить команду" if can_manage_team else "Открыть карту компании",
                target="/settings" if can_manage_team else "/company-brain",
                enabled=True,
            ),
        },
        {
            "key": "headquarters",
            "requirement": "required",
            "label": "FounderOS готов",
            "state": "complete",
            "benefit": "FounderOS уже собрал согласованный снимок состояния компании.",
            "evidence": [
                _onboarding_fact(
                    key="headquarters_snapshot",
                    label="Актуальная картина компании",
                    value=1,
                )
            ],
            "action": _action(
                kind="view_headquarters",
                label="Открыть текущую картину",
                target="/dashboard",
                enabled=True,
            ),
        },
    ]
    required_steps = [step for step in steps if step["requirement"] == "required"]
    next_step = next(
        (step for step in required_steps if step["state"] != "complete"),
        None,
    )
    return {
        "contract_version": HEADQUARTERS_ONBOARDING_CONTRACT_VERSION,
        "readiness_version": HEADQUARTERS_ONBOARDING_READINESS_VERSION,
        "ready": all(step["state"] == "complete" for step in required_steps),
        "completed_count": sum(step["state"] == "complete" for step in steps),
        "total_count": len(steps),
        "completed_required": sum(step["state"] == "complete" for step in required_steps),
        "required_total": len(required_steps),
        "current_step_key": next_step["key"] if next_step is not None else None,
        "steps": steps,
        "next_action": next_step["action"] if next_step is not None else None,
    }


def _onboarding_summary_count(
    summary: Any,
    *keys: str,
) -> int | None:
    if not isinstance(summary, Mapping):
        return None
    values = [summary.get(key) for key in keys]
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in values
    ):
        return None
    return sum(values)


def _onboarding_count_state(value: int | None, *, complete_at: int = 1) -> str:
    if value is None:
        return "unknown"
    return "complete" if value >= complete_at else "pending"


def _onboarding_fact(
    *,
    key: str,
    label: str,
    value: int | None,
    complete_at: int = 1,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "state": _onboarding_count_state(value, complete_at=complete_at),
        "value": value,
        "precision": "exact" if value is not None else "unavailable",
    }


def _capabilities(role: str) -> dict[str, bool]:
    admin = role_allows(role, MEMBERSHIP_ROLE_ADMIN)
    member = role_allows(role, MEMBERSHIP_ROLE_MEMBER)
    return {
        "can_manage_team": admin,
        "can_manage_source": admin,
        "can_import_source": admin,
        "can_start_source_read": admin,
        "can_generate_briefing": member,
        "can_create_proposal": member,
        "can_review_proposal": admin,
        "can_execute_external": bool(
            admin and settings.enable_write_actions and settings.enable_real_connectors
        ),
        "can_resolve_world": member,
        # A checkpoint is private membership state, not a company mutation.
        "can_acknowledge_changes": True,
    }


def _source_action(
    *,
    provider: str,
    name: str,
    target: str | None,
    primary_state: str,
    enabled: bool,
) -> dict[str, Any]:
    label_by_state = {
        "failed": "Проверить ошибку",
        "partial": "Проверить неполные данные",
        "stale": "Обновить данные",
        "no_data": "Получить первые данные",
        "healthy": "Открыть источник",
        "setup": f"Настроить {name}",
    }
    return _action(
        kind=f"manage_{provider}",
        label=label_by_state[primary_state],
        target=target or "/settings/integrations",
        enabled=enabled,
        disabled_reason=(
            None if enabled else "Управление источником доступно администратору или владельцу."
        ),
    )


def _mission(
    *,
    identity: str,
    kind: str,
    reference_type: str,
    reference_id: str,
    title: str,
    summary: str,
    why_now: str,
    status: str,
    severity: str,
    confidence: float | None,
    next_step: str,
    source_keys: list[str],
    evidence_refs: list[dict[str, Any]],
    action: dict[str, Any],
    ranking_reason: str,
    proposal_id: UUID | None = None,
    proposal_version: str | None = None,
    correlation_reason: str | None = None,
    correlation_rule_version: str | None = None,
) -> dict[str, Any]:
    evidence_state = (
        "verified"
        if evidence_refs and all(ref["trust"] == "verified" for ref in evidence_refs)
        else "aggregate"
    )
    return {
        "id": identity,
        "kind": kind,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "title": title,
        "summary": summary,
        "why_now": why_now,
        "status": status,
        "severity": severity,
        "confidence": confidence,
        "confidence_precision": "exact" if confidence is not None else "unavailable",
        "due_at": None,
        "impact": None,
        "next_step": next_step,
        "owner_person_ids": [],
        "organization_id": None,
        "primary_person_id": None,
        "source_keys": sorted(set(source_keys)),
        "evidence_refs": evidence_refs,
        "proposal_id": proposal_id,
        "proposal_version": proposal_version,
        "evidence_state": evidence_state,
        "trust_class": ("aggregate" if evidence_state == "aggregate" else "verified_canonical"),
        "ranking_reason": ranking_reason,
        "fact_provenance": {
            "owner": [],
            "customer": [],
            "due": [],
            "impact": [],
            "severity": evidence_refs if severity != "unknown" else [],
            "confidence": evidence_refs if confidence is not None else [],
        },
        "action": action,
        "correlation_reason": correlation_reason,
        "correlation_rule_version": correlation_rule_version,
    }


def _action(
    *,
    kind: str,
    label: str,
    target: str | None,
    enabled: bool,
    disabled_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "target": target,
        "enabled": enabled,
        "disabled_reason": disabled_reason,
    }


def _resolved_source_record_evidence(
    row: Any,
    *,
    evidence_ref: bool = False,
) -> ResolvedEvidence:
    source_record_id = row.source_record_id if evidence_ref else row.id
    is_repository = (
        _source_key(row.provider) == "github"
        and (_clean_text(row.record_type) or "").casefold() == "repository"
    )
    version = {
        "kind": "evidence_ref" if evidence_ref else "source_record",
        "source_record_id": source_record_id,
        "provider": row.provider,
        "external_id": row.external_id,
        "record_type": row.record_type,
        "source_record_source_url": row.source_url,
        "payload_hash": row.payload_hash,
        "observed_at": row.observed_at,
    }
    if evidence_ref:
        version.update(
            {
                "evidence_ref_id": row.id,
                "field_path": row.field_path,
                "confidence": row.confidence,
                "evidence_source_url": row.evidence_source_url,
                "created_at": row.evidence_created_at,
                "quote_hash": row.quote_hash,
            }
        )
    return ResolvedEvidence(
        evidence=(_evidence_ref_evidence(row) if evidence_ref else _source_record_evidence(row)),
        version=version,
        match_kind="repository_source_record" if is_repository else "source_record",
        match_key=row.external_id if is_repository else str(source_record_id),
    )


def _resolved_repository_evidence(row: Any) -> ResolvedEvidence:
    return ResolvedEvidence(
        evidence=_repository_evidence(row),
        version={
            "kind": "repository",
            "id": row.id,
            "provider": row.provider,
            "full_name": row.full_name,
            "source_url": row.source_url,
            "archived": row.archived,
            "updated_at": row.updated_at,
        },
        match_kind="repository",
        match_key=row.full_name,
    )


def _resolved_connection_evidence(row: Any) -> ResolvedEvidence:
    return ResolvedEvidence(
        evidence=_connection_evidence(row),
        version={
            "kind": "integration_connection",
            "id": row.id,
            "provider": row.provider,
            "display_name": row.display_name,
            "status": row.status,
            "scopes": row.scopes,
            "updated_at": row.updated_at,
        },
        match_kind="integration_connection",
        match_key=str(row.id),
    )


def _source_record_evidence(row: Any) -> dict[str, Any]:
    return _evidence(
        identity=f"source_record:{row.source_record_id if hasattr(row, 'source_record_id') else row.id}",
        kind=_clean_text(row.record_type) or "source_record",
        source_key=_source_key(row.provider) or "internal",
        label=(_clean_text(row.external_id) or "Canonical source record")[:255],
        target=_safe_url(row.source_url),
        provenance="canonical_source_record",
    )


def _evidence_ref_evidence(row: Any) -> dict[str, Any]:
    return _evidence(
        identity=f"evidence_ref:{row.id}",
        kind=_clean_text(row.record_type) or "source_record",
        source_key=_source_key(row.provider) or "internal",
        label=(_clean_text(row.external_id) or "Canonical evidence")[:255],
        target=_safe_url(row.evidence_source_url) or _safe_url(row.source_url),
        provenance="canonical_evidence_ref",
    )


def _repository_evidence(row: Any) -> dict[str, Any]:
    return _evidence(
        identity=f"repository:{row.id}",
        kind="repository",
        source_key="github",
        label=row.full_name[:255],
        target=_safe_url(row.source_url),
        provenance="canonical_repository",
    )


def _connection_evidence(row: Any) -> dict[str, Any]:
    source_key = _source_key(row.provider) or "internal"
    return _evidence(
        identity=f"integration_connection:{row.id}",
        kind="integration_connection",
        source_key=source_key,
        label=(_clean_text(row.display_name) or f"{source_key} connection")[:255],
        target=(
            f"/settings/integrations?provider={source_key}"
            if source_key in KNOWN_SOURCE_KEYS
            else "/settings/integrations"
        ),
        provenance="integration_connection",
    )


def _memory_event_evidence(
    *,
    event: CompanyMemoryEvent,
    target: str,
) -> dict[str, Any]:
    return _evidence(
        identity=f"company_memory_event:{event.id}",
        kind=event.event_type,
        source_key=event.source_key,
        label="Каноническое событие памяти FounderOS",
        target=target,
        provenance="company_memory_event",
    )


def _company_world_evidence(value: Any, candidate_type: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for ref in _mapping_list(value):
        record_id = _uuid_or_none(ref.get("record_id"))
        if record_id is None:
            continue
        source_key = _source_key(ref.get("source")) or "internal"
        evidence.append(
            _evidence(
                identity=f"company_world:{candidate_type}:{record_id}",
                kind=_clean_text(ref.get("kind")) or "company_world_candidate",
                source_key=source_key,
                label=(
                    _clean_text(ref.get("label")) or f"{source_key} evidence for {candidate_type}"
                )[:255],
                target=_safe_url(ref.get("url")),
                provenance="company_world_projection",
            )
        )
    return _dedupe_evidence(evidence)


def _aggregate_evidence(
    *,
    identity: str,
    label: str,
    target: str,
    source_key: str = "internal",
) -> dict[str, Any]:
    return _evidence(
        identity=identity,
        kind="headquarters_aggregate",
        source_key=source_key,
        label=label,
        target=target,
        provenance="headquarters_aggregate",
        trust="aggregate",
    )


def _evidence(
    *,
    identity: str,
    kind: str,
    source_key: str,
    label: str,
    target: str | None,
    provenance: str,
    trust: str = "verified",
) -> dict[str, Any]:
    reference_type_by_prefix = {
        "briefing_item": "briefing_item",
        "evidence_ref": "evidence_ref",
        "source_record": "source_record",
        "repository": "repository",
        "integration_connection": "integration_connection",
        "sync_job": "sync_job",
        "company_world": "company_world_candidate",
        "company_memory_event": "company_memory_event",
        "source_inventory": "headquarters_snapshot",
    }
    identity_prefix, _, reference_id = identity.partition(":")
    return {
        "id": identity,
        "kind": kind,
        "source_key": source_key,
        "label": label,
        "target": target,
        "provenance": provenance,
        "trust": trust,
        "reference_type": reference_type_by_prefix.get(identity_prefix, "headquarters_snapshot"),
        "reference_id": reference_id or identity,
        "workspace_scoped": True,
    }


def _coverage(
    key: str,
    status: str,
    material: Any,
    warning: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "status": status,
        "watermark": f"sha256:{_digest(material)[:24]}",
        "warning": warning,
    }


def _company_world_watermark_material(
    company_world: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if company_world is None:
        return {"available": False}
    return {
        "available": True,
        "window": dict(company_world["window"]),
        "summary": dict(company_world["summary"]),
        "people": [
            {
                "version": row.get("candidate_version"),
                "last_interaction_at": row.get("last_interaction_at"),
            }
            for row in company_world["people"]["external_candidates"]
        ],
        "organizations": [
            {
                "version": row.get("candidate_version"),
                "last_interaction_at": row.get("last_interaction_at"),
            }
            for row in company_world["organizations"]
        ],
        "confirmed_people": [
            row.get("id") for row in company_world["people"]["confirmed_external"]
        ],
        "confirmed_organizations": [
            row.get("id") for row in company_world["confirmed_organizations"]
        ],
    }


def _evidence_material(refs: list[Mapping[str, Any]]) -> str:
    return _digest([dict(ref) for ref in refs])


def _evidence_tokens(ref: Mapping[str, Any]) -> list[str]:
    selector = _evidence_selector(ref)
    if selector is None:
        return []
    return list(dict.fromkeys((selector.token, *selector.source_record_tokens)))


def _evidence_selector(ref: Mapping[str, Any]) -> EvidenceSelector | None:
    evidence_ref_id = _clean_text(ref.get("evidence_ref_id"))
    source_record_tokens = tuple(
        dict.fromkeys(
            value
            for key in ("source_record_id", "record_id")
            if (value := _clean_text(ref.get(key))) is not None
        )
    )
    if evidence_ref_id is not None:
        return EvidenceSelector(
            kind="evidence_ref",
            token=evidence_ref_id,
            source_record_tokens=source_record_tokens,
        )
    if source_record_tokens:
        if len(source_record_tokens) != 1:
            return None
        return EvidenceSelector(kind="source_record", token=source_record_tokens[0])

    # `ref` is the canonical public selector used by current ingestion paths.
    # `id` is accepted only when no stronger selector was declared; a missing
    # explicit ref must never be repaired through a secondary id.
    external_ref = _clean_text(ref.get("ref"))
    if external_ref is not None:
        return EvidenceSelector(kind="external", token=external_ref)
    external_id = _clean_text(ref.get("id"))
    if external_id is not None:
        return EvidenceSelector(kind="external", token=external_id)
    return None


def _provider_matches_source_hint(provider: Any, source_hint: str | None) -> bool:
    return source_hint is None or _source_key(provider) == source_hint


def _dedupe_evidence(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for ref in refs:
        unique.setdefault(ref["id"], ref)
    return list(unique.values())


def _evidence_source_keys(refs: list[dict[str, Any]]) -> list[str]:
    return sorted({ref["source_key"] for ref in refs})


def _mission_sort_key(candidate: MissionCandidate) -> tuple[int, float, str]:
    event_time = candidate.event_time
    timestamp = (
        _as_utc(event_time).timestamp()
        if isinstance(event_time, datetime)
        else float("-inf")
    )
    return (-candidate.score, -timestamp, candidate.mission["id"])


def _trusted_severity(value: Any) -> str:
    severity = _clean_text(value)
    if severity and severity.lower() in KNOWN_SEVERITIES:
        return severity.lower()
    return "unknown"


def _bounded_confidence(value: Any) -> float | None:
    if not isinstance(value, int | float):
        return None
    return min(1.0, max(0.0, float(value)))


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _strict_evidence_refs(value: Any) -> list[Mapping[str, Any]] | None:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > ACTION_PROPOSAL_EVIDENCE_REFS_MAX_ITEMS
        or any(not isinstance(item, Mapping) for item in value)
    ):
        return None
    refs = list(value)
    if any(not _evidence_ref_matches_schema(item) for item in refs):
        return None
    return refs


def _evidence_ref_matches_schema(ref: Mapping[str, Any]) -> bool:
    return action_evidence_ref_matches_schema(ref) and _source_alias_is_supported(
        ref.get("source")
    )


def _source_key(value: Any) -> str | None:
    text_value = _clean_text(value)
    if text_value is None:
        return None
    return SOURCE_KEY_ALIASES.get(text_value.casefold())


def _source_alias_is_supported(value: Any) -> bool:
    text_value = _clean_text(value)
    if text_value is None:
        return True
    normalized = text_value.casefold()
    return normalized in SOURCE_KEY_ALIASES or normalized in GENERIC_SOURCE_ALIASES


def sanitize_headquarters_evidence_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if (
        len(value) > 1000
        or "\\" in value
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        return None
    try:
        parsed = urlsplit(value)
        # Accessing `.port` rejects malformed and out-of-range ports that a
        # browser URL parser would also refuse.
        parsed.port
        query_pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            max_num_fields=100,
        )
    except ValueError:
        return None
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    if any(
        key.casefold().replace("-", "_") in SENSITIVE_EVIDENCE_URL_QUERY_KEYS
        for key, _value in query_pairs
    ):
        return None
    return value


def _safe_url(value: Any) -> str | None:
    return sanitize_headquarters_evidence_url(value)


def _database_error_code(exc: DBAPIError) -> str | None:
    candidates = [exc, getattr(exc, "orig", None)]
    original = getattr(exc, "orig", None)
    candidates.extend(
        [
            getattr(original, "__cause__", None),
            getattr(original, "__context__", None),
        ]
    )
    for candidate in candidates:
        if candidate is None:
            continue
        code = getattr(candidate, "sqlstate", None) or getattr(candidate, "pgcode", None)
        if isinstance(code, str) and code:
            return code
    return None


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _uuid_or_none(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _datetime_or_none(value: Any) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _latest_datetime_value(*values: Any) -> datetime | None:
    timestamps = [
        _as_utc(value)
        for value in values
        if isinstance(value, datetime)
    ]
    return max(timestamps) if timestamps else None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _digest(value: Any) -> str:
    material = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=_json_default,
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"unsupported headquarters snapshot value: {type(value).__name__}")
