from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select

from app.api.auth import settings
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import (
    EvidenceRef,
    PullRequest,
    Repository,
    SourceRecord,
    Task,
)
from app.db.document_models import Document, DocumentVersion
from app.db.identity_models import Membership, User, Workspace
from app.db.repository_intelligence_models import (
    RepositoryAnalysisJob,
    RepositoryAuditFinding,
    RepositoryAuditRun,
    RepositoryContradiction,
    RepositoryEvidenceLink,
    RepositoryFact,
    RepositoryRelationshipRecord,
)
from app.main import app
from app.services.repository_intelligence.contracts import RepositoryIntelligenceV1
from app.services.repository_intelligence.persistence import (
    RepositoryAnalysisRequestV1,
    RepositoryArtifactManifestItemV1,
    RepositoryCoverageV1,
    claim_repository_analysis_job,
    enqueue_repository_analysis_job,
    persist_repository_intelligence_result,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "repository_intelligence"
TEST_EPOCH = datetime.now(timezone.utc).replace(
    hour=0,
    minute=0,
    second=0,
    microsecond=0,
) + timedelta(days=1)


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_workspace(
    marker: str,
) -> tuple[User, Workspace, Repository, Repository]:
    async with AsyncSessionLocal() as session:
        owner = User(
            email=f"ri-read-owner-{marker}@example.test",
            name="RI Read Owner",
        )
        session.add(owner)
        await session.flush()
        workspace = Workspace(
            name=f"RI Read {marker}",
            slug=f"ri-read-{marker}",
            created_by_user_id=owner.id,
        )
        session.add(workspace)
        await session.flush()
        session.add(
            Membership(
                workspace_id=workspace.id,
                user_id=owner.id,
                role="owner",
            )
        )
        source = Repository(
            workspace_id=workspace.id,
            provider="github",
            external_id=f"source-{marker}",
            name=f"source-{marker}",
            full_name=f"synthetic-company/source-{marker}",
            default_branch="main",
            visibility="private",
            archived=False,
            source_url=f"https://github.com/synthetic-company/source-{marker}",
        )
        target = Repository(
            workspace_id=workspace.id,
            provider="github",
            external_id=f"target-{marker}",
            name=f"target-{marker}",
            full_name=f"synthetic-company/target-{marker}",
            default_branch="main",
            visibility="internal",
            archived=False,
            source_url=f"https://github.com/synthetic-company/target-{marker}",
        )
        session.add_all([source, target])
        await session.commit()
        return owner, workspace, source, target


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"ri-read-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"ri-read-%-{marker}@example.test")
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
                DocumentVersion,
                Document,
                PullRequest,
                Task,
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
    source: Repository,
    target: Repository,
    commit_sha: str,
) -> RepositoryIntelligenceV1:
    material = json.loads(
        (FIXTURE_ROOT / "valid/backend_l1.json").read_text(encoding="utf-8")
    )
    material["workspace_id"] = str(workspace_id)
    material["repository_id"] = str(source.id)
    material["repository"] = {
        "provider": "github",
        "external_id": source.external_id,
        "full_name": source.full_name,
        "default_branch": "main",
        "source_url": None,
    }
    material["analysis_target"]["commit_sha"] = commit_sha
    for claim in [
        material["result"]["purpose"],
        *material["result"]["responsibilities"],
        *material["result"]["interfaces_provided"],
        *material["result"]["dependencies_consumed"],
        *material["result"]["deployment_units"],
        *material["result"]["ownership_candidates"],
        *material["result"]["findings"],
        *material["result"]["unknowns"],
    ]:
        claim["workspace_id"] = str(workspace_id)

    owner_candidate = copy.deepcopy(material["result"]["responsibilities"][0])
    owner_candidate.update(
        {
            "workspace_id": str(workspace_id),
            "status": "inferred",
            "confidence": 0.64,
            "claim_id": "owner.platform-team",
            "claim_type": "owner_candidate",
            "summary": "Synthetic platform team may own this repository.",
            "details": ["Inferred from the synthetic ownership fixture."],
        }
    )
    material["result"]["ownership_candidates"] = [owner_candidate]

    relationship = material["result"]["relationship_candidates"][0]
    relationship["workspace_id"] = str(workspace_id)
    relationship["status"] = "inferred"
    relationship["from_repository"] = {
        "workspace_id": str(workspace_id),
        "repository_id": str(source.id),
        "provider": "github",
        "external_id": source.external_id,
        "full_name": source.full_name,
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
    return RepositoryIntelligenceV1.model_validate(material)


def _request(
    payload: RepositoryIntelligenceV1,
    *,
    idempotency_key: str,
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
    )


def _coverage() -> RepositoryCoverageV1:
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


async def _persist_run(
    *,
    owner: User,
    payload: RepositoryIntelligenceV1,
    marker: str,
) -> UUID:
    completed_at = TEST_EPOCH + timedelta(minutes=1)
    worker_id = f"worker-{marker}"
    async with AsyncSessionLocal() as session:
        job = await enqueue_repository_analysis_job(
            session,
            request=_request(payload, idempotency_key=f"ri-read-{marker}"),
            requested_by_user_id=owner.id,
        )
        job.next_attempt_at = TEST_EPOCH
        claimed = await claim_repository_analysis_job(
            session,
            workspace_id=payload.workspace_id,
            job_id=job.id,
            worker_id=worker_id,
            now=TEST_EPOCH,
        )
        assert claimed is not None
        run = await persist_repository_intelligence_result(
            session,
            job_id=job.id,
            worker_id=worker_id,
            payload=payload,
            coverage=_coverage(),
            artifact_manifest=[
                RepositoryArtifactManifestItemV1(
                    artifact_type="report",
                    storage_ref=(
                        "repository-intelligence/synthetic/read-api/"
                        "private-report.json"
                    ),
                    content_hash="f" * 64,
                    size_bytes=512,
                )
            ],
            started_at=completed_at - timedelta(seconds=20),
            completed_at=completed_at,
        )
        evidence_ref = await session.scalar(
            select(EvidenceRef)
            .join(
                RepositoryEvidenceLink,
                RepositoryEvidenceLink.evidence_ref_id == EvidenceRef.id,
            )
            .where(RepositoryEvidenceLink.workspace_id == payload.workspace_id)
            .limit(1)
        )
        assert evidence_ref is not None
        evidence_ref.quote = "private synthetic source body must not be returned"
        evidence_ref.source_url = (
            f"https://github.com/{payload.repository.full_name}/blob/"
            f"{payload.analysis_target.commit_sha}/README.md"
        )
        await session.commit()
        return run.id


async def _ri_counts(workspace_id: UUID) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        return {
            model.__tablename__: int(
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.workspace_id == workspace_id)
                )
                or 0
            )
            for model in (
                RepositoryAnalysisJob,
                RepositoryAuditRun,
                RepositoryFact,
                RepositoryRelationshipRecord,
                RepositoryAuditFinding,
                RepositoryContradiction,
                RepositoryEvidenceLink,
                PullRequest,
                Task,
                Document,
                SourceRecord,
            )
        }


def _claim_set(
    *,
    repository: Repository,
    expected_value: str,
    summary: str,
    fact_type: str = "purpose",
    claim_id: str = "purpose.primary",
    field: str = "repository_type",
) -> dict:
    return {
        "schema_version": "repository_cross_source_claim_set.v1",
        "claims": [
            {
                "schema_version": "repository_cross_source_claim.v1",
                "repository_id": str(repository.id),
                "repository_full_name": repository.full_name,
                "fact_type": fact_type,
                "claim_id": claim_id,
                "field": field,
                "expected_value": expected_value,
                "summary": summary,
                "confidence": 0.8,
            }
        ],
    }


async def _seed_cross_source_records(
    *,
    workspace: Workspace,
    source: Repository,
    foreign_repository: Repository,
) -> None:
    async with AsyncSessionLocal() as session:
        source_records = [
            SourceRecord(
                workspace_id=workspace.id,
                provider=provider,
                external_id=external_id,
                record_type=record_type,
                source_url=source_url,
                payload={"synthetic": True},
                payload_hash=f"hash-{external_id}",
                observed_at=TEST_EPOCH,
                source_updated_at=TEST_EPOCH,
            )
            for provider, external_id, record_type, source_url in (
                (
                    "github",
                    "github-agreement",
                    "issue",
                    "https://github.com/synthetic-company/source/issues/1",
                ),
                (
                    "jira",
                    "FOS-42",
                    "issue",
                    "https://jira.example/browse/FOS-42",
                ),
                (
                    "jira",
                    "FOS-43",
                    "issue",
                    "https://jira.example/browse/FOS-43",
                ),
                (
                    "github",
                    "github-pr-agreement",
                    "pull_request",
                    "https://github.com/synthetic-company/source/pull/7",
                ),
            )
        ]
        session.add_all(source_records)
        await session.flush()
        session.add_all(
            [
                Task(
                    workspace_id=workspace.id,
                    source_provider="github",
                    source_record_id=source_records[0].id,
                    external_id="github-agreement",
                    title="Structured GitHub agreement",
                    status="open",
                    source_url=source_records[0].source_url,
                    source_updated_at=TEST_EPOCH,
                    task_metadata={
                        "github_object_type": "issue",
                        "repository_intelligence_claims": _claim_set(
                            repository=source,
                            expected_value="backend_service",
                            summary="GitHub agrees this is a backend service.",
                        ),
                    },
                ),
                Task(
                    workspace_id=workspace.id,
                    source_provider="jira",
                    source_record_id=source_records[1].id,
                    external_id="FOS-42",
                    title="Structured Jira contradiction",
                    status="open",
                    source_url=source_records[1].source_url,
                    source_updated_at=TEST_EPOCH,
                    task_metadata={
                        "jira_object_type": "issue",
                        "repository_intelligence_claims": _claim_set(
                            repository=source,
                            expected_value="frontend_application",
                            summary="Jira says this is a frontend application.",
                        ),
                    },
                ),
                Task(
                    workspace_id=workspace.id,
                    source_provider="jira",
                    source_record_id=source_records[2].id,
                    external_id="FOS-43",
                    title="Foreign repository claim",
                    status="open",
                    source_url=source_records[2].source_url,
                    source_updated_at=TEST_EPOCH,
                    task_metadata={
                        "jira_object_type": "issue",
                        "repository_intelligence_claims": _claim_set(
                            repository=foreign_repository,
                            expected_value="backend_service",
                            summary="This exact claim belongs to another repository.",
                        ),
                    },
                ),
            ]
        )
        session.add(
            PullRequest(
                workspace_id=workspace.id,
                repository_id=source.id,
                source_record_id=source_records[3].id,
                external_id="github-pr-agreement",
                number=7,
                title="Structured PR responsibility agreement",
                state="open",
                source_url=source_records[3].source_url,
                created_at_source=TEST_EPOCH,
                updated_at_source=TEST_EPOCH,
                pr_metadata={
                    "github_object_type": "pull_request",
                    "repository_intelligence_claims": _claim_set(
                        repository=source,
                        expected_value="owns",
                        summary="The PR agrees this repository owns the order API.",
                        fact_type="responsibility",
                        claim_id="responsibility.orders",
                        field="claim_type",
                    ),
                },
            )
        )
        missing_fact_document = Document(
            workspace_id=workspace.id,
            title="Structured dependency note",
            body_markdown=json.dumps(
                _claim_set(
                    repository=source,
                    expected_value="redis",
                    summary="The document declares a Redis dependency.",
                    fact_type="dependency_consumed",
                    claim_id="dependency.cache",
                    field="claim_type",
                ),
                separators=(",", ":"),
            ),
            body_text="synthetic structured claim",
            tags=["repository-intelligence"],
            status="published",
        )
        malformed_document = Document(
            workspace_id=workspace.id,
            title="Malformed structured note",
            body_markdown="{not-json",
            body_text="private raw document body should not be returned",
            tags=["repository-intelligence"],
            status="published",
        )
        untagged_document = Document(
            workspace_id=workspace.id,
            title="Free text must not create a contradiction",
            body_markdown=(
                "This repository is definitely a frontend application."
            ),
            body_text=(
                "This repository is definitely a frontend application."
            ),
            tags=[],
            status="published",
        )
        session.add_all(
            [missing_fact_document, malformed_document, untagged_document]
        )
        await session.commit()


async def test_repository_intelligence_read_apis_project_bounded_safe_state(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:12]
    await _cleanup(marker)
    _set_auth(monkeypatch)
    try:
        owner, workspace, source, target = await _seed_workspace(marker)
        payload = _payload(
            workspace_id=workspace.id,
            source=source,
            target=target,
            commit_sha="1" * 40,
        )
        run_id = await _persist_run(owner=owner, payload=payload, marker=marker)
        await _seed_cross_source_records(
            workspace=workspace,
            source=source,
            foreign_repository=target,
        )
        before = await _ri_counts(workspace.id)
        params = {"owner_email": owner.email}
        base = f"/api/v1/workspaces/{workspace.id}/repository-intelligence"

        async with _async_client() as client:
            portfolio_response = await client.get(
                base,
                headers=_headers(),
                params=params,
            )
            detail_response = await client.get(
                f"{base}/repositories/{source.id}",
                headers=_headers(),
                params=params,
            )
            history_response = await client.get(
                f"{base}/repositories/{source.id}/history",
                headers=_headers(),
                params=params,
            )
            graph_response = await client.get(
                f"{base}/graph",
                headers=_headers(),
                params=params,
            )

        assert portfolio_response.status_code == 200, portfolio_response.text
        assert detail_response.status_code == 200, detail_response.text
        assert history_response.status_code == 200, history_response.text
        assert graph_response.status_code == 200, graph_response.text

        portfolio = portfolio_response.json()
        assert portfolio["summary"] == {
            "repositories": 2,
            "analyzed_repositories": 1,
            "repositories_with_open_findings": 1,
            "repositories_with_stale_intelligence": 0,
            "current_relationships": 1,
            "blocking_unknowns": 1,
            "pending_confirmations": 2,
        }
        source_row = next(
            row for row in portfolio["repositories"] if row["id"] == str(source.id)
        )
        assert source_row["purpose_summary"] == (
            "Synthetic backend service for order processing."
        )
        assert source_row["repository_type"] == "backend_service"
        assert source_row["owner_candidates"] == [
            "Synthetic platform team may own this repository."
        ]
        assert source_row["open_findings"] == {
            "critical": 0,
            "high": 0,
            "medium": 1,
            "low": 0,
            "info": 0,
        }
        assert source_row["latest_audit"]["id"] == str(run_id)

        detail = detail_response.json()
        assert detail["repository"]["id"] == str(source.id)
        assert detail["purpose"]["value"]["repository_type"] == "backend_service"
        assert detail["unknowns"][0]["value"]["question"] == (
            "Who owns the synthetic service?"
        )
        assert {row["kind"] for row in detail["confirmation_queue"]} == {
            "fact",
            "relationship",
        }
        assert detail["relationships"][0]["claim_status"] == "inferred"
        assert detail["relationships"][0]["direction"] == "outbound"
        assert detail["relationships"][0]["to_repository"]["id"] == str(target.id)
        assert detail["findings"][0]["severity"] == "medium"
        assert detail["cross_source"]["summary"] == {
            "sources_considered": 6,
            "comparisons": 4,
            "agreements": 2,
            "contradictions": 1,
            "insufficient_evidence": 1,
            "rejected_claim_sets": 2,
        }
        comparisons = detail["cross_source"]["comparisons"]
        agreements = [
            row for row in comparisons if row["status"] == "agreement"
        ]
        contradiction = next(
            row for row in comparisons if row["status"] == "contradiction"
        )
        insufficient = next(
            row
            for row in comparisons
            if row["status"] == "insufficient_evidence"
        )
        assert {row["source"]["source_type"] for row in agreements} == {
            "task",
            "pull_request",
        }
        assert {row["source"]["provider"] for row in agreements} == {"github"}
        assert contradiction["source"]["provider"] == "jira"
        assert (
            contradiction["repository_fact"]["actual_value"]
            == "backend_service"
        )
        assert (
            insufficient["source"]["source_type"] == "document"
        )
        assert {
            row["error_code"]
            for row in detail["cross_source"]["rejected_claim_sets"]
        } == {
            "claim_set_invalid_json",
            "repository_identity_mismatch",
        }
        assert detail["cross_source"]["contract"] == {
            "claim_set_schema": "repository_cross_source_claim_set.v1",
            "claim_schema": "repository_cross_source_claim.v1",
            "exact_repository_identity_required": True,
            "free_text_inference": False,
            "fuzzy_matching": False,
            "persistence_write": False,
        }
        assert detail["capabilities"] == {
            "provider_calls": False,
            "repository_reads": False,
            "target_execution": False,
            "external_writes": False,
            "llm_used": False,
            "human_resolution_writes": False,
        }
        evidence = next(
            item
            for row in [
                *detail["facts"],
                *detail["relationships"],
                *detail["findings"],
            ]
            for item in row["evidence"]
            if item["url"] is not None
        )
        assert evidence["ref"]
        assert evidence["url"].startswith("https://github.com/")

        history = history_response.json()
        assert history["runs"][0]["id"] == str(run_id)
        assert history["runs"][0]["coverage_status"] == "complete"
        assert history["runs"][0]["artifact_count"] == 1
        assert history["runs"][0]["artifact_status"] == "retained"

        graph = graph_response.json()
        assert graph["summary"] == {
            "nodes": 2,
            "edges": 1,
            "observed_edges": 0,
            "inferred_edges": 1,
            "candidate_edges": 0,
        }
        assert graph["edges"][0]["from_repository_id"] == str(source.id)
        assert graph["edges"][0]["to_repository_id"] == str(target.id)

        response_text = "\n".join(
            response.text
            for response in (
                portfolio_response,
                detail_response,
                history_response,
                graph_response,
            )
        )
        assert "private synthetic source body" not in response_text
        assert "private-report.json" not in response_text
        assert "artifact_manifest" not in response_text
        assert "source_record" not in response_text
        assert "private raw document body" not in response_text
        assert "definitely a frontend application" not in response_text
        assert await _ri_counts(workspace.id) == before
    finally:
        await _cleanup(marker)


async def test_repository_intelligence_read_apis_enforce_workspace_isolation_and_bounds(
    monkeypatch,
) -> None:
    marker = uuid4().hex[:12]
    other_marker = uuid4().hex[:12]
    await _cleanup(marker)
    await _cleanup(other_marker)
    _set_auth(monkeypatch)
    try:
        owner, workspace, source, target = await _seed_workspace(marker)
        other_owner, other_workspace, _other_source, _other_target = (
            await _seed_workspace(other_marker)
        )
        await _persist_run(
            owner=owner,
            payload=_payload(
                workspace_id=workspace.id,
                source=source,
                target=target,
                commit_sha="2" * 40,
            ),
            marker=marker,
        )
        base = f"/api/v1/workspaces/{workspace.id}/repository-intelligence"
        other_base = (
            f"/api/v1/workspaces/{other_workspace.id}/repository-intelligence"
        )
        async with _async_client() as client:
            limited = await client.get(
                base,
                headers=_headers(),
                params={"owner_email": owner.email, "limit": 1},
            )
            invalid_limit = await client.get(
                base,
                headers=_headers(),
                params={"owner_email": owner.email, "limit": 201},
            )
            foreign_detail = await client.get(
                f"{other_base}/repositories/{source.id}",
                headers=_headers(),
                params={"owner_email": other_owner.email},
            )
            wrong_actor = await client.get(
                base,
                headers=_headers(),
                params={"owner_email": other_owner.email},
            )
            unauthenticated = await client.get(base)

        assert limited.status_code == 200
        assert limited.json()["limits"]["repositories"] == 1
        assert limited.json()["truncated"] is True
        assert len(limited.json()["repositories"]) == 1
        assert invalid_limit.status_code == 422
        assert foreign_detail.status_code == 404
        assert wrong_actor.status_code == 404
        assert unauthenticated.status_code == 401
    finally:
        await _cleanup(marker)
        await _cleanup(other_marker)
