from __future__ import annotations

import copy
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import AsyncSessionLocal
from app.db.canonical_models import EvidenceRef, Repository, SourceRecord
from app.db.identity_models import (
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.repository_intelligence_models import (
    REPOSITORY_ANALYSIS_JOB_STATUS_CANCELLED,
    REPOSITORY_ANALYSIS_JOB_STATUS_QUEUED,
    REPOSITORY_ANALYSIS_JOB_STATUS_RUNNING,
    REPOSITORY_ANALYSIS_JOB_STATUS_SUCCEEDED,
    REPOSITORY_CONTRADICTION_STATUS_CURRENT,
    REPOSITORY_FINDING_STATUS_ACCEPTED_RISK,
    REPOSITORY_FINDING_STATUS_REGRESSED,
    REPOSITORY_FINDING_STATUS_RESOLVED,
    REPOSITORY_LIFECYCLE_STATUS_CURRENT,
    REPOSITORY_LIFECYCLE_STATUS_STALE,
    RepositoryAnalysisJob,
    RepositoryAuditFinding,
    RepositoryAuditRun,
    RepositoryContradiction,
    RepositoryEvidenceLink,
    RepositoryFact,
    RepositoryRelationshipRecord,
)
from app.services.repository_intelligence.contracts import (
    RepositoryIntelligenceV1,
)
from app.services.repository_intelligence.persistence import (
    RepositoryAnalysisRequestV1,
    RepositoryArtifactManifestItemV1,
    RepositoryCoverageV1,
    RepositoryIntelligenceConflictError,
    RepositoryIntelligenceStateError,
    claim_repository_analysis_job,
    confirm_repository_artifacts_deleted,
    delete_repository_intelligence_records,
    enqueue_repository_analysis_job,
    fail_repository_analysis_job,
    list_expired_repository_artifacts,
    persist_repository_intelligence_result,
    request_repository_analysis_cancellation,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "repository_intelligence"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "11c7b724c929_add_repository_intelligence_persistence.py"
)

# Tests inject one synthetic run clock safely after the insert wall clock.
# Newly enqueued jobs use the database clock for ``next_attempt_at``, so each
# initial claim explicitly aligns that field before exercising claim behavior.
_TEST_EPOCH = datetime.now(timezone.utc).replace(
    hour=0, minute=0, second=0, microsecond=0
) + timedelta(days=1)


def _migration_module():
    spec = importlib.util.spec_from_file_location("ri006_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _seed_workspace(
    marker: str,
) -> tuple[User, User, Workspace, Repository, Repository]:
    async with AsyncSessionLocal() as session:
        owner = User(
            email=f"ri-persistence-owner-{marker}@example.test",
            name="RI Persistence Owner",
        )
        viewer = User(
            email=f"ri-persistence-viewer-{marker}@example.test",
            name="RI Persistence Viewer",
        )
        session.add_all([owner, viewer])
        await session.flush()
        workspace = Workspace(
            name=f"RI Persistence {marker}",
            slug=f"ri-persistence-{marker}",
            created_by_user_id=owner.id,
        )
        session.add(workspace)
        await session.flush()
        session.add_all(
            [
                Membership(
                    workspace_id=workspace.id,
                    user_id=owner.id,
                    role=MEMBERSHIP_ROLE_OWNER,
                ),
                Membership(
                    workspace_id=workspace.id,
                    user_id=viewer.id,
                    role=MEMBERSHIP_ROLE_VIEWER,
                ),
            ]
        )
        repository = Repository(
            workspace_id=workspace.id,
            external_id=f"source-{marker}",
            name=f"source-{marker}",
            full_name=f"synthetic-company/source-{marker}",
            visibility="private",
        )
        target = Repository(
            workspace_id=workspace.id,
            external_id=f"target-{marker}",
            name=f"target-{marker}",
            full_name=f"synthetic-company/target-{marker}",
            visibility="private",
        )
        session.add_all([repository, target])
        await session.commit()
        return owner, viewer, workspace, repository, target


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"ri-persistence-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"ri-persistence-%-{marker}@example.test")
                    )
                )
            ).scalars()
        )
        if workspace_ids:
            for model in (
                RepositoryEvidenceLink,
                RepositoryContradiction,
                RepositoryRelationshipRecord,
                RepositoryFact,
                RepositoryAuditFinding,
                RepositoryAuditRun,
                RepositoryAnalysisJob,
                EvidenceRef,
                SourceRecord,
                Repository,
                Membership,
            ):
                await session.execute(
                    delete(model).where(model.workspace_id.in_(workspace_ids))
                )
            await session.execute(
                delete(Workspace).where(Workspace.id.in_(workspace_ids))
            )
        if user_ids:
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


def _payload(
    *,
    workspace_id: UUID,
    repository: Repository,
    target: Repository,
    commit_sha: str,
    include_responsibility: bool = True,
    include_relationship: bool = True,
    include_finding: bool = True,
    include_contradiction: bool = False,
) -> RepositoryIntelligenceV1:
    source = json.loads(
        (
            FIXTURE_ROOT
            / (
                "valid/contradiction_l1.json"
                if include_contradiction
                else "valid/backend_l1.json"
            )
        ).read_text(encoding="utf-8")
    )
    source["workspace_id"] = str(workspace_id)
    source["repository_id"] = str(repository.id)
    source["repository"] = {
        "provider": "github",
        "external_id": repository.external_id,
        "full_name": repository.full_name,
        "default_branch": "main",
        "source_url": None,
    }
    source["analysis_target"]["commit_sha"] = commit_sha
    for claim in [
        source["result"]["purpose"],
        *source["result"]["responsibilities"],
        *source["result"]["interfaces_provided"],
        *source["result"]["dependencies_consumed"],
        *source["result"]["deployment_units"],
        *source["result"]["ownership_candidates"],
        *source["result"]["findings"],
        *source["result"]["contradictions"],
        *source["result"]["unknowns"],
    ]:
        claim["workspace_id"] = str(workspace_id)
    if not include_responsibility:
        source["result"]["responsibilities"] = []
        source["result"]["contradictions"] = []
    if include_relationship:
        if not source["result"]["relationship_candidates"]:
            source["result"]["relationship_candidates"] = [
                copy.deepcopy(
                    json.loads(
                        (
                            FIXTURE_ROOT / "valid/backend_l1.json"
                        ).read_text(encoding="utf-8")
                    )["result"]["relationship_candidates"][0]
                )
            ]
        relationship = source["result"]["relationship_candidates"][0]
        relationship["workspace_id"] = str(workspace_id)
        relationship["from_repository"] = {
            "workspace_id": str(workspace_id),
            "repository_id": str(repository.id),
            "provider": "github",
            "external_id": repository.external_id,
            "full_name": repository.full_name,
            "resolution_status": "canonical",
        }
        relationship["to_repository"] = {
            "workspace_id": str(workspace_id),
            "repository_id": str(target.id),
            "provider": "github",
            "external_id": target.external_id,
            "full_name": target.full_name,
            "resolution_status": "canonical",
        }
    else:
        source["result"]["relationship_candidates"] = []
    if not include_finding:
        source["result"]["findings"] = []
    return RepositoryIntelligenceV1.model_validate(source)


def _request(
    payload: RepositoryIntelligenceV1,
    *,
    idempotency_key: str,
    max_attempts: int = 3,
) -> RepositoryAnalysisRequestV1:
    return RepositoryAnalysisRequestV1(
        workspace_id=payload.workspace_id,
        repository_id=payload.repository_id,
        idempotency_key=idempotency_key,
        audit_level=payload.audit_level,
        analysis_target=payload.analysis_target,
        profile=payload.profile,
        policy_hash=payload.policy_hash,
        engine_version=payload.engine_version,
        max_attempts=max_attempts,
    )


def _complete_coverage() -> RepositoryCoverageV1:
    return RepositoryCoverageV1(
        completed_checks=[
            "manifest",
            "entrypoint",
            "dependency",
            "interface",
            "deployment",
            "test_ci",
            "documentation",
            "migration",
            "relationship",
        ]
    )


def _artifact() -> RepositoryArtifactManifestItemV1:
    return RepositoryArtifactManifestItemV1(
        artifact_type="collector_result",
        storage_ref="repository-intelligence/synthetic/run/collector.json",
        content_hash="f" * 64,
        size_bytes=512,
    )


async def _enqueue_claim_persist(
    *,
    owner: User,
    payload: RepositoryIntelligenceV1,
    idempotency_key: str,
    coverage: RepositoryCoverageV1,
    completed_at: datetime,
) -> tuple[UUID, UUID]:
    async with AsyncSessionLocal() as session:
        job = await enqueue_repository_analysis_job(
            session,
            request=_request(payload, idempotency_key=idempotency_key),
            requested_by_user_id=owner.id,
        )
        claim_time = completed_at - timedelta(minutes=1)
        job.next_attempt_at = claim_time
        claimed = await claim_repository_analysis_job(
            session,
            workspace_id=payload.workspace_id,
            job_id=job.id,
            worker_id=f"worker-{idempotency_key}"[:64],
            now=claim_time,
        )
        assert claimed is not None
        run = await persist_repository_intelligence_result(
            session,
            job_id=job.id,
            worker_id=f"worker-{idempotency_key}"[:64],
            payload=payload,
            coverage=coverage,
            artifact_manifest=[_artifact()],
            started_at=completed_at - timedelta(seconds=20),
            completed_at=completed_at,
        )
        await session.commit()
        return job.id, run.id


async def test_job_enqueuing_is_idempotent_rbac_scoped_and_retryable() -> None:
    marker = uuid4().hex[:12]
    await _cleanup(marker)
    try:
        owner, viewer, workspace, repository, target = await _seed_workspace(marker)
        payload = _payload(
            workspace_id=workspace.id,
            repository=repository,
            target=target,
            commit_sha="1" * 40,
        )
        now = _TEST_EPOCH + timedelta(hours=10)
        async with AsyncSessionLocal() as session:
            with pytest.raises(
                RepositoryIntelligenceStateError,
                match="owner or admin",
            ):
                await enqueue_repository_analysis_job(
                    session,
                    request=_request(payload, idempotency_key="viewer-denied"),
                    requested_by_user_id=viewer.id,
                )
            first = await enqueue_repository_analysis_job(
                session,
                request=_request(
                    payload,
                    idempotency_key="retry-safe",
                    max_attempts=2,
                ),
                requested_by_user_id=owner.id,
            )
            replay = await enqueue_repository_analysis_job(
                session,
                request=_request(
                    payload,
                    idempotency_key="retry-safe",
                    max_attempts=2,
                ),
                requested_by_user_id=owner.id,
            )
            assert replay.id == first.id
            conflicting = _request(
                payload,
                idempotency_key="retry-safe",
                max_attempts=2,
            ).model_copy(update={"engine_version": "different-engine"})
            with pytest.raises(
                RepositoryIntelligenceConflictError,
                match="different input",
            ):
                await enqueue_repository_analysis_job(
                    session,
                    request=conflicting,
                    requested_by_user_id=owner.id,
                )

            first.next_attempt_at = now
            claimed = await claim_repository_analysis_job(
                session,
                workspace_id=workspace.id,
                job_id=first.id,
                worker_id="synthetic-worker",
                now=now,
            )
            assert claimed is not None
            assert claimed.status == REPOSITORY_ANALYSIS_JOB_STATUS_RUNNING
            assert (
                await claim_repository_analysis_job(
                    session,
                    workspace_id=workspace.id,
                    job_id=first.id,
                    worker_id="second-worker",
                    now=now + timedelta(seconds=10),
                )
                is None
            )
            failed = await fail_repository_analysis_job(
                session,
                workspace_id=workspace.id,
                job_id=first.id,
                worker_id="synthetic-worker",
                error_code="synthetic_timeout",
                retryable=True,
                now=now,
                retry_delay_seconds=30,
            )
            assert failed.status == REPOSITORY_ANALYSIS_JOB_STATUS_QUEUED
            assert failed.error_code == "synthetic_timeout"
            assert (
                await claim_repository_analysis_job(
                    session,
                    workspace_id=workspace.id,
                    job_id=first.id,
                    worker_id="early-worker",
                    now=now + timedelta(seconds=20),
                )
                is None
            )
            resumed = await claim_repository_analysis_job(
                session,
                workspace_id=workspace.id,
                job_id=first.id,
                worker_id="resumed-worker",
                now=now + timedelta(seconds=31),
            )
            assert resumed is not None
            assert resumed.attempt_count == 2
            await session.rollback()
    finally:
        await _cleanup(marker)


async def test_job_cancellation_requires_admin_and_blocks_late_result() -> None:
    marker = uuid4().hex[:12]
    await _cleanup(marker)
    try:
        owner, viewer, workspace, repository, target = await _seed_workspace(marker)
        payload = _payload(
            workspace_id=workspace.id,
            repository=repository,
            target=target,
            commit_sha="0" * 40,
        )
        now = _TEST_EPOCH + timedelta(hours=10, minutes=30)
        async with AsyncSessionLocal() as session:
            job = await enqueue_repository_analysis_job(
                session,
                request=_request(payload, idempotency_key="cancel-running"),
                requested_by_user_id=owner.id,
            )
            job.next_attempt_at = now
            claimed = await claim_repository_analysis_job(
                session,
                workspace_id=workspace.id,
                job_id=job.id,
                worker_id="cancel-worker",
                now=now,
            )
            assert claimed is not None
            assert claimed.status == REPOSITORY_ANALYSIS_JOB_STATUS_RUNNING
            with pytest.raises(
                RepositoryIntelligenceStateError,
                match="owner or admin",
            ):
                await request_repository_analysis_cancellation(
                    session,
                    workspace_id=workspace.id,
                    job_id=job.id,
                    requested_by_user_id=viewer.id,
                    now=now + timedelta(seconds=1),
                )
            cancelled = await request_repository_analysis_cancellation(
                session,
                workspace_id=workspace.id,
                job_id=job.id,
                requested_by_user_id=owner.id,
                now=now + timedelta(seconds=2),
            )
            assert cancelled.cancel_requested_at is not None
            with pytest.raises(
                RepositoryIntelligenceStateError,
                match="cancelled analysis result",
            ):
                await persist_repository_intelligence_result(
                    session,
                    job_id=job.id,
                    worker_id="cancel-worker",
                    payload=payload,
                    coverage=_complete_coverage(),
                    started_at=now,
                    completed_at=now + timedelta(seconds=30),
                )
            assert job.status == REPOSITORY_ANALYSIS_JOB_STATUS_CANCELLED
            assert job.lease_owner is None
            await session.rollback()
    finally:
        await _cleanup(marker)


async def test_complete_run_persists_source_record_evidence_and_replays() -> None:
    marker = uuid4().hex[:12]
    await _cleanup(marker)
    try:
        owner, _viewer, workspace, repository, target = await _seed_workspace(marker)
        payload = _payload(
            workspace_id=workspace.id,
            repository=repository,
            target=target,
            commit_sha="2" * 40,
            include_contradiction=True,
            include_relationship=True,
            include_finding=False,
        )
        completed = _TEST_EPOCH + timedelta(hours=11)
        async with AsyncSessionLocal() as session:
            job = await enqueue_repository_analysis_job(
                session,
                request=_request(payload, idempotency_key="complete-run"),
                requested_by_user_id=owner.id,
            )
            claim_time = completed - timedelta(minutes=1)
            job.next_attempt_at = claim_time
            claimed = await claim_repository_analysis_job(
                session,
                workspace_id=workspace.id,
                job_id=job.id,
                worker_id="complete-worker",
                now=claim_time,
            )
            assert claimed is not None
            run = await persist_repository_intelligence_result(
                session,
                job_id=job.id,
                worker_id="complete-worker",
                payload=payload,
                coverage=_complete_coverage(),
                artifact_manifest=[_artifact()],
                started_at=completed - timedelta(seconds=30),
                completed_at=completed,
            )
            replay = await persist_repository_intelligence_result(
                session,
                job_id=job.id,
                worker_id="complete-worker",
                payload=payload,
                coverage=_complete_coverage(),
                artifact_manifest=[_artifact()],
                started_at=completed - timedelta(seconds=30),
                completed_at=completed,
            )
            assert replay.id == run.id
            await session.commit()

        async with AsyncSessionLocal() as session:
            stored_job = await session.get(RepositoryAnalysisJob, job.id)
            stored_run = await session.get(RepositoryAuditRun, run.id)
            source_record = await session.get(SourceRecord, stored_run.source_record_id)
            facts = list(
                (
                    await session.execute(
                        select(RepositoryFact).where(
                            RepositoryFact.workspace_id == workspace.id,
                            RepositoryFact.repository_id == repository.id,
                        )
                    )
                ).scalars()
            )
            contradictions = list(
                (
                    await session.execute(
                        select(RepositoryContradiction).where(
                            RepositoryContradiction.workspace_id == workspace.id
                        )
                    )
                ).scalars()
            )
            evidence_count = await session.scalar(
                select(func.count())
                .select_from(RepositoryEvidenceLink)
                .where(RepositoryEvidenceLink.workspace_id == workspace.id)
            )
            source_count = await session.scalar(
                select(func.count())
                .select_from(SourceRecord)
                .where(
                    SourceRecord.workspace_id == workspace.id,
                    SourceRecord.record_type == "repository_intelligence_run",
                )
            )

        assert stored_job.status == REPOSITORY_ANALYSIS_JOB_STATUS_SUCCEEDED
        assert stored_run.reconciliation_applied is True
        assert source_record.payload["artifact_count"] == 1
        assert "Synthetic public API" not in json.dumps(source_record.payload)
        assert {fact.claim_id for fact in facts} >= {
            "purpose.primary",
            "responsibility.worker",
        }
        assert len(contradictions) == 1
        assert contradictions[0].status == REPOSITORY_CONTRADICTION_STATUS_CURRENT
        assert int(evidence_count or 0) > 0
        assert int(source_count or 0) == 1
    finally:
        await _cleanup(marker)


async def test_same_target_can_have_multiple_job_runs_but_replay_conflicts_fail() -> None:
    marker = uuid4().hex[:12]
    await _cleanup(marker)
    try:
        owner, _viewer, workspace, repository, target = await _seed_workspace(marker)
        payload = _payload(
            workspace_id=workspace.id,
            repository=repository,
            target=target,
            commit_sha="c" * 40,
        )
        completed = _TEST_EPOCH + timedelta(hours=11, minutes=30)
        _first_job, first_run = await _enqueue_claim_persist(
            owner=owner,
            payload=payload,
            idempotency_key="same-target-first",
            coverage=_complete_coverage(),
            completed_at=completed,
        )
        _second_job, second_run = await _enqueue_claim_persist(
            owner=owner,
            payload=payload,
            idempotency_key="same-target-second",
            coverage=_complete_coverage(),
            completed_at=completed + timedelta(minutes=1),
        )
        assert first_run != second_run
        async with AsyncSessionLocal() as session:
            runs = int(
                await session.scalar(
                    select(func.count())
                    .select_from(RepositoryAuditRun)
                    .where(
                        RepositoryAuditRun.workspace_id == workspace.id,
                        RepositoryAuditRun.repository_id == repository.id,
                    )
                )
                or 0
            )
            assert runs == 2

            job = await enqueue_repository_analysis_job(
                session,
                request=_request(payload, idempotency_key="replay-conflict"),
                requested_by_user_id=owner.id,
            )
            claim_time = completed + timedelta(minutes=2)
            job.next_attempt_at = claim_time
            claimed = await claim_repository_analysis_job(
                session,
                workspace_id=workspace.id,
                job_id=job.id,
                worker_id="replay-worker",
                now=claim_time,
            )
            assert claimed is not None
            await persist_repository_intelligence_result(
                session,
                job_id=job.id,
                worker_id="replay-worker",
                payload=payload,
                coverage=_complete_coverage(),
                artifact_manifest=[_artifact()],
                started_at=completed + timedelta(minutes=2),
                completed_at=completed + timedelta(minutes=2, seconds=20),
            )
            changed = payload.model_copy(
                update={
                    "result": payload.result.model_copy(
                        update={
                            "limitations": [
                                "Different result for the same job replay."
                            ]
                        }
                    )
                }
            )
            with pytest.raises(
                RepositoryIntelligenceConflictError,
                match="different result",
            ):
                await persist_repository_intelligence_result(
                    session,
                    job_id=job.id,
                    worker_id="replay-worker",
                    payload=changed,
                    coverage=_complete_coverage(),
                    artifact_manifest=[_artifact()],
                    started_at=completed + timedelta(minutes=2),
                    completed_at=completed + timedelta(minutes=2, seconds=20),
                )
            await session.rollback()
    finally:
        await _cleanup(marker)


async def test_partial_run_never_resolves_prior_records_and_complete_run_does() -> None:
    marker = uuid4().hex[:12]
    await _cleanup(marker)
    try:
        owner, _viewer, workspace, repository, target = await _seed_workspace(marker)
        first_payload = _payload(
            workspace_id=workspace.id,
            repository=repository,
            target=target,
            commit_sha="3" * 40,
            include_responsibility=True,
            include_relationship=True,
            include_finding=True,
        )
        second_payload = _payload(
            workspace_id=workspace.id,
            repository=repository,
            target=target,
            commit_sha="4" * 40,
            include_responsibility=False,
            include_relationship=False,
            include_finding=False,
        )
        first_time = _TEST_EPOCH + timedelta(hours=12)
        await _enqueue_claim_persist(
            owner=owner,
            payload=first_payload,
            idempotency_key="first-complete",
            coverage=_complete_coverage(),
            completed_at=first_time,
        )
        await _enqueue_claim_persist(
            owner=owner,
            payload=second_payload,
            idempotency_key="second-partial",
            coverage=RepositoryCoverageV1(
                completed_checks=["manifest"],
                failed_checks=["relationship"],
            ),
            completed_at=first_time + timedelta(hours=1),
        )

        async with AsyncSessionLocal() as session:
            responsibility = await session.scalar(
                select(RepositoryFact).where(
                    RepositoryFact.workspace_id == workspace.id,
                    RepositoryFact.repository_id == repository.id,
                    RepositoryFact.claim_id == "responsibility.orders",
                )
            )
            relationship = await session.scalar(
                select(RepositoryRelationshipRecord).where(
                    RepositoryRelationshipRecord.workspace_id == workspace.id,
                    RepositoryRelationshipRecord.from_repository_id == repository.id,
                )
            )
            finding = await session.scalar(
                select(RepositoryAuditFinding).where(
                    RepositoryAuditFinding.workspace_id == workspace.id,
                    RepositoryAuditFinding.repository_id == repository.id,
                )
            )
        assert responsibility.lifecycle_status == REPOSITORY_LIFECYCLE_STATUS_CURRENT
        assert relationship.lifecycle_status == REPOSITORY_LIFECYCLE_STATUS_CURRENT
        assert finding.status == "new"

        await _enqueue_claim_persist(
            owner=owner,
            payload=second_payload.model_copy(
                update={
                    "analysis_target": second_payload.analysis_target.model_copy(
                        update={"commit_sha": "5" * 40}
                    )
                }
            ),
            idempotency_key="third-complete",
            coverage=_complete_coverage(),
            completed_at=first_time + timedelta(hours=2),
        )
        async with AsyncSessionLocal() as session:
            responsibility = await session.scalar(
                select(RepositoryFact).where(
                    RepositoryFact.workspace_id == workspace.id,
                    RepositoryFact.repository_id == repository.id,
                    RepositoryFact.claim_id == "responsibility.orders",
                )
            )
            relationship = await session.scalar(
                select(RepositoryRelationshipRecord).where(
                    RepositoryRelationshipRecord.workspace_id == workspace.id,
                    RepositoryRelationshipRecord.from_repository_id == repository.id,
                )
            )
            finding = await session.scalar(
                select(RepositoryAuditFinding).where(
                    RepositoryAuditFinding.workspace_id == workspace.id,
                    RepositoryAuditFinding.repository_id == repository.id,
                )
            )
        assert responsibility.lifecycle_status == REPOSITORY_LIFECYCLE_STATUS_STALE
        assert relationship.lifecycle_status == REPOSITORY_LIFECYCLE_STATUS_STALE
        assert finding.status == REPOSITORY_FINDING_STATUS_RESOLVED
    finally:
        await _cleanup(marker)


async def test_resolved_finding_regresses_and_accepted_risk_is_preserved() -> None:
    marker = uuid4().hex[:12]
    await _cleanup(marker)
    try:
        owner, _viewer, workspace, repository, target = await _seed_workspace(marker)
        with_finding = _payload(
            workspace_id=workspace.id,
            repository=repository,
            target=target,
            commit_sha="6" * 40,
            include_finding=True,
        )
        without_finding = _payload(
            workspace_id=workspace.id,
            repository=repository,
            target=target,
            commit_sha="7" * 40,
            include_finding=False,
        )
        base_time = _TEST_EPOCH + timedelta(hours=13)
        await _enqueue_claim_persist(
            owner=owner,
            payload=with_finding,
            idempotency_key="finding-first",
            coverage=_complete_coverage(),
            completed_at=base_time,
        )
        await _enqueue_claim_persist(
            owner=owner,
            payload=without_finding,
            idempotency_key="finding-resolved",
            coverage=_complete_coverage(),
            completed_at=base_time + timedelta(hours=1),
        )
        await _enqueue_claim_persist(
            owner=owner,
            payload=with_finding.model_copy(
                update={
                    "analysis_target": with_finding.analysis_target.model_copy(
                        update={"commit_sha": "8" * 40}
                    )
                }
            ),
            idempotency_key="finding-regressed",
            coverage=_complete_coverage(),
            completed_at=base_time + timedelta(hours=2),
        )
        async with AsyncSessionLocal() as session:
            finding = await session.scalar(
                select(RepositoryAuditFinding).where(
                    RepositoryAuditFinding.workspace_id == workspace.id,
                    RepositoryAuditFinding.repository_id == repository.id,
                )
            )
            assert finding.status == REPOSITORY_FINDING_STATUS_REGRESSED
            finding.status = REPOSITORY_FINDING_STATUS_ACCEPTED_RISK
            finding.decided_by_user_id = owner.id
            finding.decided_at = base_time + timedelta(hours=2, minutes=5)
            await session.commit()

        accepted_payload = with_finding.model_copy(
            update={
                "analysis_target": with_finding.analysis_target.model_copy(
                    update={"commit_sha": "9" * 40}
                )
            }
        )
        await _enqueue_claim_persist(
            owner=owner,
            payload=accepted_payload,
            idempotency_key="finding-accepted",
            coverage=_complete_coverage(),
            completed_at=base_time + timedelta(hours=3),
        )
        async with AsyncSessionLocal() as session:
            finding = await session.scalar(
                select(RepositoryAuditFinding).where(
                    RepositoryAuditFinding.workspace_id == workspace.id,
                    RepositoryAuditFinding.repository_id == repository.id,
                )
            )
        assert finding.status == REPOSITORY_FINDING_STATUS_ACCEPTED_RISK
        assert finding.decided_by_user_id == owner.id
    finally:
        await _cleanup(marker)


async def test_workspace_composite_fks_reject_cross_workspace_rows() -> None:
    marker_a = f"{uuid4().hex[:8]}-a"
    marker_b = f"{uuid4().hex[:8]}-b"
    await _cleanup(marker_a)
    await _cleanup(marker_b)
    try:
        owner_a, _viewer_a, workspace_a, repository_a, target_a = (
            await _seed_workspace(marker_a)
        )
        _owner_b, _viewer_b, workspace_b, repository_b, _target_b = (
            await _seed_workspace(marker_b)
        )
        payload = _payload(
            workspace_id=workspace_a.id,
            repository=repository_a,
            target=target_a,
            commit_sha="a" * 40,
        )
        job_id, run_id = await _enqueue_claim_persist(
            owner=owner_a,
            payload=payload,
            idempotency_key="workspace-isolation",
            coverage=_complete_coverage(),
            completed_at=_TEST_EPOCH + timedelta(hours=14),
        )
        del job_id
        async with AsyncSessionLocal() as session:
            session.add(
                RepositoryFact(
                    workspace_id=workspace_a.id,
                    repository_id=repository_b.id,
                    fingerprint="b" * 64,
                    claim_id="cross.workspace",
                    fact_type="purpose",
                    value={"summary": "invalid"},
                    claim_status="observed",
                    confidence=1.0,
                    first_seen_run_id=run_id,
                    last_seen_run_id=run_id,
                )
            )
            with pytest.raises(
                IntegrityError,
                match="fk_repository_facts_workspace_repository",
            ):
                await session.commit()
            await session.rollback()

            relationship = await session.scalar(
                select(RepositoryRelationshipRecord).where(
                    RepositoryRelationshipRecord.workspace_id == workspace_a.id,
                    RepositoryRelationshipRecord.from_repository_id
                    == repository_a.id,
                )
            )
            relationship.to_repository_id = repository_b.id
            with pytest.raises(
                IntegrityError,
                match="fk_repository_relationships_workspace_to_repository",
            ):
                await session.commit()
            await session.rollback()
    finally:
        await _cleanup(marker_a)
        await _cleanup(marker_b)


async def test_artifact_retention_and_repository_deletion_are_explicit() -> None:
    marker = uuid4().hex[:12]
    await _cleanup(marker)
    try:
        owner, _viewer, workspace, repository, target = await _seed_workspace(marker)
        payload = _payload(
            workspace_id=workspace.id,
            repository=repository,
            target=target,
            commit_sha="b" * 40,
        )
        completed = _TEST_EPOCH + timedelta(hours=15)
        _job_id, run_id = await _enqueue_claim_persist(
            owner=owner,
            payload=payload,
            idempotency_key="retention",
            coverage=_complete_coverage(),
            completed_at=completed,
        )
        async with AsyncSessionLocal() as session:
            assert await list_expired_repository_artifacts(
                session,
                workspace_id=workspace.id,
                now=completed + timedelta(days=29),
            ) == []
            receipts = await list_expired_repository_artifacts(
                session,
                workspace_id=workspace.id,
                now=completed + timedelta(days=31),
            )
            assert [receipt.run_id for receipt in receipts] == [run_id]
            with pytest.raises(
                RepositoryIntelligenceStateError,
                match="not past retention",
            ):
                await confirm_repository_artifacts_deleted(
                    session,
                    workspace_id=workspace.id,
                    run_id=run_id,
                    now=completed + timedelta(days=29),
                )
            purged = await confirm_repository_artifacts_deleted(
                session,
                workspace_id=workspace.id,
                run_id=run_id,
                now=completed + timedelta(days=31),
            )
            assert purged.artifact_manifest == []
            await session.commit()

        async with AsyncSessionLocal() as session:
            with pytest.raises(
                RepositoryIntelligenceStateError,
                match="owner or admin",
            ):
                await delete_repository_intelligence_records(
                    session,
                    workspace_id=workspace.id,
                    repository_id=repository.id,
                    requested_by_user_id=uuid4(),
                )
            deleted = await delete_repository_intelligence_records(
                session,
                workspace_id=workspace.id,
                repository_id=repository.id,
                requested_by_user_id=owner.id,
            )
            await session.commit()
        assert deleted.runs_deleted == 1
        assert deleted.jobs_deleted == 1
        assert deleted.source_records_deleted == 1
        assert deleted.facts_deleted > 0
    finally:
        await _cleanup(marker)


def test_coverage_and_artifact_contracts_fail_closed() -> None:
    with pytest.raises(ValidationError):
        RepositoryCoverageV1(
            completed_checks=["manifest"],
            failed_checks=["manifest"],
        )
    with pytest.raises(ValidationError):
        RepositoryArtifactManifestItemV1(
            artifact_type="collector_result",
            storage_ref="../private-source.json",
            content_hash="a" * 64,
            size_bytes=1,
        )


def test_repository_intelligence_downgrade_refuses_non_empty_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration_module()

    class _Result:
        @staticmethod
        def scalar_one() -> bool:
            return True

    class _Bind:
        @staticmethod
        def execute(_statement: object) -> _Result:
            return _Result()

    monkeypatch.setattr(migration.op, "get_bind", lambda: _Bind())
    with pytest.raises(
        RuntimeError,
        match="refusing to downgrade non-empty Repository Intelligence tables",
    ):
        migration.downgrade()


async def test_repository_intelligence_migration_contract_exists() -> None:
    async with AsyncSessionLocal() as session:
        tables = set(
            (
                await session.execute(
                    text(
                        """
                        select table_name from information_schema.tables
                        where table_schema = 'public'
                        and table_name in (
                          'repository_analysis_jobs',
                          'repository_audit_runs',
                          'repository_facts',
                          'repository_relationships',
                          'repository_audit_findings',
                          'repository_contradictions',
                          'repository_evidence_links'
                        )
                        """
                    )
                )
            ).scalars()
        )
        constraints = set(
            (
                await session.execute(
                    text(
                        """
                        select conname from pg_constraint
                        where conname in (
                          'fk_repository_analysis_jobs_workspace_repository',
                          'uq_repository_analysis_jobs_workspace_idempotency_key',
                          'fk_repository_audit_runs_workspace_repository_job',
                          'fk_repository_facts_workspace_repository_first_run',
                          'fk_repository_relationships_workspace_to_repository',
                          'fk_repository_audit_findings_workspace_repository',
                          'fk_repository_contradictions_workspace_repository_left_fact',
                          'fk_repository_evidence_links_workspace_evidence',
                          'ck_repository_evidence_links_one_parent',
                          'ck_evidence_refs_kind',
                          'ck_evidence_refs_source'
                        )
                        """
                    )
                )
            ).scalars()
        )

    assert tables == {
        "repository_analysis_jobs",
        "repository_audit_runs",
        "repository_facts",
        "repository_relationships",
        "repository_audit_findings",
        "repository_contradictions",
        "repository_evidence_links",
    }
    assert constraints == {
        "fk_repository_analysis_jobs_workspace_repository",
        "uq_repository_analysis_jobs_workspace_idempotency_key",
        "fk_repository_audit_runs_workspace_repository_job",
        "fk_repository_facts_workspace_repository_first_run",
        "fk_repository_relationships_workspace_to_repository",
        "fk_repository_audit_findings_workspace_repository",
        "fk_repository_contradictions_workspace_repository_left_fact",
        "fk_repository_evidence_links_workspace_evidence",
        "ck_repository_evidence_links_one_parent",
        "ck_evidence_refs_kind",
        "ck_evidence_refs_source",
    }
