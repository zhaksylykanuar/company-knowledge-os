from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.github_repository_read_service as github_repository_read_service
from app.db.integration_models import (
    INTEGRATION_PROVIDER_GITHUB,
    SYNC_JOB_STATUS_FAILED,
    SYNC_JOB_STATUS_QUEUED,
    SYNC_JOB_STATUS_RUNNING,
    SyncJob,
)
from app.services.company_brain_github_read_service import build_workspace_company_brain
from app.services.github_connection_service import get_github_connection_status

BRIEFING_TITLE = "Founder Briefing"
BRIEFING_PERSISTENCE_TRANSIENT = "transient"
NO_EVIDENCE_WARNING = "No evidence refs available for this briefing item."
NO_LLM_WARNING = "Founder Briefing v0 is deterministic and does not use an LLM."


@dataclass(frozen=True)
class FounderBriefingOptions:
    focus: list[str] = field(default_factory=lambda: ["github", "sync", "repositories"])
    include_github: bool = True
    include_connections: bool = True
    include_sync_jobs: bool = True
    include_repository_inventory: bool = True
    limit: int = 20


async def generate_manual_founder_briefing(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    options: FounderBriefingOptions,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    warnings = [NO_LLM_WARNING]
    github_signals = {
        "connection_status": "not_requested",
        "repository_count": 0,
        "queued_sync_jobs": 0,
        "latest_sync_job_status": None,
    }
    coverage_signals = _empty_coverage_signals()

    if not options.include_github:
        warnings.append("GitHub briefing signals were disabled by request.")
    else:
        if options.include_connections:
            connection_item, connection_status = await _github_connection_item(
                session,
                workspace_id=workspace_id,
            )
            github_signals["connection_status"] = connection_status
            items.append(connection_item)

        if options.include_repository_inventory:
            repository_item, repository_count, repository_warnings = (
                await _github_repository_item(
                    session,
                    workspace_id=workspace_id,
                    limit=options.limit,
                )
            )
            github_signals["repository_count"] = repository_count
            items.append(repository_item)
            warnings.extend(repository_warnings)

            coverage_item, coverage_signals = await _source_coverage_item(
                session,
                workspace_id=workspace_id,
                limit=options.limit,
            )
            github_signals["repository_count"] = max(
                int(github_signals["repository_count"]),
                int(coverage_signals["canonical_repositories"]),
            )
            items.append(coverage_item)

        if options.include_sync_jobs:
            sync_items, sync_signals = await _github_sync_items(
                session,
                workspace_id=workspace_id,
                limit=options.limit,
            )
            github_signals["queued_sync_jobs"] = sync_signals["queued_sync_jobs"]
            github_signals["latest_sync_job_status"] = sync_signals[
                "latest_sync_job_status"
            ]
            items.extend(sync_items)

    warnings.extend(
        item_warning
        for item in items
        for item_warning in item.get("warnings", [])
        if isinstance(item_warning, str)
    )
    summary = _summary(github_signals, coverage_signals)
    return {
        "briefing": {
            "title": BRIEFING_TITLE,
            "summary": summary,
            "generated_at": generated_at,
            "workspace_id": workspace_id,
            "is_live": False,
            "llm_used": False,
            "persistence": BRIEFING_PERSISTENCE_TRANSIENT,
            "items": items,
            "signals": {"github": github_signals, "coverage": coverage_signals},
            "warnings": _dedupe_warnings(warnings),
        }
    }


async def _github_connection_item(
    session: AsyncSession,
    *,
    workspace_id: UUID,
) -> tuple[dict[str, Any], str]:
    status_payload = await get_github_connection_status(
        session,
        workspace_id=workspace_id,
    )
    status = str(status_payload["status"])
    if not status_payload.get("has_connection_record"):
        return (
            _item(
                item_id="github-connection",
                category="next_step",
                title="GitHub is not product-connected yet",
                summary=(
                    "No GitHub IntegrationConnection exists; create a provider-token "
                    "connection before product sync."
                ),
                severity="medium",
                confidence=0.6,
                evidence_refs=[],
                recommended_next_step="Connect GitHub using the provider-token bridge.",
                warnings=["no connection record"],
            ),
            status,
        )

    evidence_refs = [
        {
            "kind": "integration_connection",
            "source": "local_db",
            "ref": str(status_payload["connection_id"]),
            "url": None,
        }
    ]
    severity = "high" if status in {"error", "revoked", "disabled"} else "low"
    return (
        _item(
            item_id="github-connection",
            category="status",
            title="GitHub connection record exists",
            summary=(
                f"GitHub connection status is {status}; "
                f"has_access_token={bool(status_payload['has_valid_token_record'])}."
            ),
            severity=severity,
            confidence=1.0,
            evidence_refs=evidence_refs,
            recommended_next_step=(
                "Fix or reconnect GitHub before sync."
                if severity == "high"
                else "Use the connection for manual sync when needed."
            ),
            warnings=list(status_payload.get("warnings") or []),
        ),
        status,
    )


async def _github_repository_item(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int,
) -> tuple[dict[str, Any], int, list[str]]:
    result = await github_repository_read_service.list_workspace_github_repositories(
        session=session,
        workspace_id=workspace_id,
        filters=github_repository_read_service.GitHubRepositoryFilters(limit=limit),
    )
    repositories = result.repositories
    if not repositories:
        return (
            _item(
                item_id="github-repositories",
                category="next_step",
                title="No local GitHub repositories available",
                summary="No repositories were found in local GitHub inventory.",
                severity="medium",
                confidence=0.6,
                evidence_refs=[],
                recommended_next_step="Create a manual sync job and run local normalization.",
                warnings=[
                    "no local GitHub repository inventory",
                    *result.warnings,
                ],
            ),
            0,
            list(result.warnings),
        )

    evidence_refs = _collect_repo_evidence_refs(repositories)
    repo_names = ", ".join(
        str(repo.get("full_name") or repo.get("name"))
        for repo in repositories[: min(3, len(repositories))]
        if repo.get("full_name") or repo.get("name")
    )
    summary = f"{len(repositories)} GitHub repositories are available locally."
    if repo_names:
        summary = f"{summary} Top observed repositories: {repo_names}."
    return (
        _item(
            item_id="github-repositories",
            category="update",
            title="Local GitHub repository inventory is available",
            summary=summary,
            severity="low",
            confidence=0.8,
            evidence_refs=evidence_refs,
            related_entities=[
                str(repo.get("full_name") or repo.get("name"))
                for repo in repositories[: min(5, len(repositories))]
                if repo.get("full_name") or repo.get("name")
            ],
            recommended_next_step=(
                "Use repository evidence as briefing context."
                if evidence_refs
                else "Add source-event or discovery evidence refs for repository inventory."
            ),
            warnings=list(result.warnings),
        ),
        len(repositories),
        list(result.warnings),
    )


async def _source_coverage_item(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    brain = await build_workspace_company_brain(
        session=session,
        workspace_id=workspace_id,
        limit=limit,
    )
    summary = brain.get("summary") if isinstance(brain.get("summary"), Mapping) else {}
    capabilities = (
        brain.get("capabilities") if isinstance(brain.get("capabilities"), Mapping) else {}
    )
    repositories = brain.get("repositories") if isinstance(brain.get("repositories"), list) else []
    evidence = brain.get("evidence") if isinstance(brain.get("evidence"), list) else []

    repository_count = int(summary.get("repositories") or 0)
    open_issues = int(summary.get("open_issues") or 0)
    open_pull_requests = int(summary.get("open_pull_requests") or 0)
    evidence_refs = _coverage_evidence_refs(evidence, repositories)
    coverage_signals = {
        "canonical_repositories": repository_count,
        "open_issues": open_issues,
        "open_pull_requests": open_pull_requests,
        "evidence_refs": len(evidence_refs),
        "is_live": bool(brain.get("is_live")),
        "llm_used": bool(brain.get("llm_used")),
        "live_provider_sync": bool(capabilities.get("live_provider_sync")),
        "local_sync": bool(capabilities.get("local_sync")),
    }

    has_coverage = repository_count + open_issues + open_pull_requests > 0
    related_entities = [
        str(repo.get("full_name") or repo.get("name"))
        for repo in repositories[: min(5, len(repositories))]
        if isinstance(repo, Mapping) and (repo.get("full_name") or repo.get("name"))
    ]
    if not has_coverage:
        return (
            _item(
                item_id="source-coverage",
                category="next_step",
                title="Source coverage is still empty",
                summary=(
                    "Company Brain has no canonical repositories, open issues, "
                    "or open pull requests for this workspace yet."
                ),
                severity="medium",
                confidence=0.8,
                evidence_refs=[],
                recommended_next_step=(
                    "Prepare local source coverage or approve a scoped read-only "
                    "provider sync later."
                ),
                warnings=["source coverage empty"],
            ),
            coverage_signals,
        )

    work_summary = (
        f"open_issues={open_issues}, open_pull_requests={open_pull_requests}"
    )
    return (
        _item(
            item_id="source-coverage",
            category="status",
            title="Canonical source coverage is available",
            summary=(
                "Company Brain coverage is local and deterministic: "
                f"repositories={repository_count}, {work_summary}, "
                f"evidence_refs={len(evidence_refs)}, "
                f"live_provider_sync={coverage_signals['live_provider_sync']}, "
                f"llm_used={coverage_signals['llm_used']}."
            ),
            severity="low",
            confidence=1.0,
            evidence_refs=evidence_refs,
            related_entities=related_entities,
            recommended_next_step=(
                "Use this coverage to review deterministic briefing items; "
                "run live provider reads only after explicit approval."
            ),
            warnings=[] if evidence_refs else ["source coverage has no evidence refs"],
        ),
        coverage_signals,
    )


async def _github_sync_items(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    jobs = (
        (
            await session.execute(
                select(SyncJob)
                .where(SyncJob.workspace_id == workspace_id)
                .where(SyncJob.provider == INTEGRATION_PROVIDER_GITHUB)
                .order_by(SyncJob.created_at.desc(), SyncJob.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not jobs:
        return (
            [
                _item(
                    item_id="github-sync-jobs",
                    category="next_step",
                    title="No GitHub sync jobs exist yet",
                    summary="No manual GitHub SyncJob rows are available for this workspace.",
                    severity="medium",
                    confidence=0.6,
                    evidence_refs=[],
                    recommended_next_step="Create a manual GitHub sync job.",
                    warnings=["no GitHub sync jobs"],
                )
            ],
            {"queued_sync_jobs": 0, "latest_sync_job_status": None},
        )

    latest = jobs[0]
    queued_count = sum(1 for job in jobs if job.status == SYNC_JOB_STATUS_QUEUED)
    items = [_sync_job_item(latest, queued_count=queued_count)]
    normalization_item = _normalization_item_from_jobs(jobs)
    if normalization_item is not None:
        items.append(normalization_item)
    else:
        items.append(
            _item(
                item_id="github-normalization",
                category="next_step",
                title="Local GitHub normalization has not run yet",
                summary="No local_normalization log was found in recent GitHub SyncJobs.",
                severity="medium",
                confidence=0.6,
                evidence_refs=[_sync_job_ref(latest)],
                recommended_next_step="Run local normalization for a queued manual SyncJob.",
                warnings=["local normalization not performed"],
            )
        )
    return (
        items,
        {
            "queued_sync_jobs": queued_count,
            "latest_sync_job_status": latest.status,
        },
    )


def _sync_job_item(sync_job: SyncJob, *, queued_count: int) -> dict[str, Any]:
    if sync_job.status == SYNC_JOB_STATUS_FAILED:
        category = "risk"
        severity = "high"
        next_step = "Inspect the failed SyncJob and retry with local-only normalization."
    elif sync_job.status in {SYNC_JOB_STATUS_QUEUED, SYNC_JOB_STATUS_RUNNING}:
        category = "status"
        severity = "medium"
        next_step = "Run local normalization for queued jobs." if queued_count else None
    else:
        category = "status"
        severity = "low"
        next_step = None
    return _item(
        item_id="github-sync-jobs",
        category=category,
        title=f"Latest GitHub SyncJob status is {sync_job.status}",
        summary=(
            f"Latest GitHub SyncJob status={sync_job.status}; "
            f"queued_jobs={queued_count}; records_seen={sync_job.records_seen}."
        ),
        severity=severity,
        confidence=1.0,
        evidence_refs=[_sync_job_ref(sync_job)],
        recommended_next_step=next_step,
        warnings=[sync_job.error_message] if sync_job.error_message else [],
    )


def _normalization_item_from_jobs(jobs: list[SyncJob]) -> dict[str, Any] | None:
    for job in jobs:
        for log in reversed(list(job.logs or [])):
            if not isinstance(log, Mapping):
                continue
            normalization = log.get("local_normalization")
            if not isinstance(normalization, Mapping) or not normalization.get("performed"):
                continue
            counts = normalization.get("counts")
            count_summary = counts if isinstance(counts, Mapping) else {}
            warnings = [
                str(warning)
                for warning in normalization.get("warnings", [])
                if isinstance(warning, str)
            ]
            issue_pr_unavailable = any(
                "issues were not available" in warning
                or "pull requests were not available" in warning
                for warning in warnings
            )
            return _item(
                item_id="github-normalization",
                category="update",
                title="Local GitHub normalization has run",
                summary=(
                    "Latest local normalization counts: "
                    f"repositories={int(count_summary.get('repositories') or 0)}, "
                    f"issues={int(count_summary.get('issues') or 0)}, "
                    f"pull_requests={int(count_summary.get('pull_requests') or 0)}."
                ),
                severity="low",
                confidence=1.0,
                evidence_refs=[_sync_job_ref(job)],
                recommended_next_step=(
                    "Use normalized repository projection for briefing context."
                ),
                warnings=warnings
                + (
                    ["issues/PRs unavailable in local source"]
                    if issue_pr_unavailable
                    else []
                ),
            )
    return None


def _item(
    *,
    item_id: str,
    category: str,
    title: str,
    summary: str,
    severity: str,
    confidence: float,
    evidence_refs: list[dict[str, Any]],
    related_entities: list[str] | None = None,
    recommended_next_step: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    item_warnings = list(warnings or [])
    if not evidence_refs and NO_EVIDENCE_WARNING not in item_warnings:
        item_warnings.append(NO_EVIDENCE_WARNING)
    return {
        "id": item_id,
        "category": category,
        "title": title,
        "summary": summary,
        "severity": severity,
        "confidence": max(0.0, min(1.0, confidence)),
        "evidence_refs": evidence_refs,
        "related_entities": related_entities or [],
        "recommended_next_step": recommended_next_step,
        "warnings": _dedupe_warnings(item_warnings),
    }


def _sync_job_ref(sync_job: SyncJob) -> dict[str, Any]:
    return {
        "kind": "sync_job",
        "source": "local_db",
        "ref": str(sync_job.id),
        "url": None,
    }


def _collect_repo_evidence_refs(repositories: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for repo in repositories:
        raw_refs = repo.get("evidence_refs")
        if not isinstance(raw_refs, list):
            continue
        for raw_ref in raw_refs:
            if not isinstance(raw_ref, Mapping):
                continue
            ref = {
                "kind": _safe_text(raw_ref.get("kind")) or "repository_inventory",
                "source": _safe_text(raw_ref.get("source")) or "unknown",
                "ref": _safe_text(raw_ref.get("ref")),
                "url": _safe_url(raw_ref.get("url")),
            }
            if ref["ref"] and ref not in refs:
                refs.append(ref)
    return refs[:20]


def _empty_coverage_signals() -> dict[str, Any]:
    return {
        "canonical_repositories": 0,
        "open_issues": 0,
        "open_pull_requests": 0,
        "evidence_refs": 0,
        "is_live": False,
        "llm_used": False,
        "live_provider_sync": False,
        "local_sync": False,
    }


def _coverage_evidence_refs(
    evidence: list[Any],
    repositories: list[Any],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for raw_ref in evidence:
        if not isinstance(raw_ref, Mapping):
            continue
        ref = {
            "kind": _safe_text(raw_ref.get("kind")) or "company_brain_evidence",
            "source": _safe_text(raw_ref.get("source")) or "company_brain",
            "ref": _safe_text(raw_ref.get("label")) or _safe_text(raw_ref.get("id")),
            "url": _safe_url(raw_ref.get("url")),
        }
        if ref["ref"] and ref not in refs:
            refs.append(ref)

    if refs:
        return refs[:20]

    for raw_repo in repositories:
        if not isinstance(raw_repo, Mapping):
            continue
        ref_text = _safe_text(raw_repo.get("full_name")) or _safe_text(
            raw_repo.get("id")
        )
        ref = {
            "kind": "canonical_repository",
            "source": "local_db",
            "ref": ref_text,
            "url": _safe_url(raw_repo.get("source_url")),
        }
        if ref["ref"] and ref not in refs:
            refs.append(ref)
    return refs[:20]


def _summary(
    github_signals: Mapping[str, Any],
    coverage_signals: Mapping[str, Any],
) -> str:
    coverage_suffix = ""
    if coverage_signals:
        coverage_suffix = (
            f" open_issues={coverage_signals.get('open_issues')}, "
            f"open_pull_requests={coverage_signals.get('open_pull_requests')}, "
            f"evidence_refs={coverage_signals.get('evidence_refs')}, "
            f"mode={'live' if coverage_signals.get('is_live') else 'local_db'}."
        )
    return (
        "GitHub signals: "
        f"connection={github_signals.get('connection_status')}, "
        f"repositories={github_signals.get('repository_count')}, "
        f"queued_sync_jobs={github_signals.get('queued_sync_jobs')}, "
        f"latest_sync_job={github_signals.get('latest_sync_job_status')}."
        f"{coverage_suffix}"
    )


def _safe_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _safe_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text and "@" not in text:
        return text
    return None


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    deduped: list[str] = []
    for warning in warnings:
        if warning and warning not in deduped:
            deduped.append(warning)
    return deduped
