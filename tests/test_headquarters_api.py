from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

import app.services.company_map_read_service as company_map_service
import app.services.headquarters_read_service as headquarters_service
import app.services.github_app_token_service as github_app_token_service
import app.services.github_selected_issue_sync_service as github_issue_sync_service
import app.services.github_selected_pr_sync_service as github_pr_sync_service
import app.services.secret_encryption as secret_encryption
from app.api.auth import settings
from app.api.headquarters import (
    HeadquartersActionRead,
    HeadquartersEvidenceRefRead,
    HeadquartersOnboardingRead,
    HeadquartersPulseMetricRead,
)
from app.db.action_models import (
    ACTION_CREATED_BY_SYSTEM,
    ACTION_CREATED_BY_USER,
    ACTION_PROPOSAL_STATUS_APPROVED,
    ACTION_TARGET_PROVIDER_INTERNAL,
    ACTION_TYPE_INTERNAL_TODO,
    ActionProposal,
)
from app.db.base import AsyncSessionLocal
from app.db.briefing_models import Briefing, BriefingItem
from app.db.canonical_models import EvidenceRef, Repository, SourceRecord
from app.db.company_world_models import (
    RESOLUTION_CANDIDATE_EXTERNAL_PERSON,
    RESOLUTION_CANDIDATE_ORGANIZATION,
    RESOLUTION_DECISION_DISMISSED,
    CompanyWorldResolution,
    Organization,
)
from app.db.identity_models import (
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_VIEWER,
    Membership,
    User,
    Workspace,
)
from app.db.integration_models import (
    INTEGRATION_CONNECTION_STATUS_CONNECTED,
    INTEGRATION_CONNECTION_STATUS_DISABLED,
    INTEGRATION_CONNECTION_STATUS_REVOKED,
    SYNC_JOB_STATUS_FAILED,
    SYNC_JOB_STATUS_SUCCEEDED,
    IntegrationConnection,
    SyncJob,
)
from app.main import app
from app.services.session_service import create_session


def _headers() -> dict[str, str]:
    return {"X-FounderOS-API-Key": "test-api-key"}


def _set_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_auth_enabled", True)
    monkeypatch.setattr(settings, "api_auth_key", SecretStr("test-api-key"))
    monkeypatch.setattr(settings, "api_auth_header_name", "X-FounderOS-API-Key")
    monkeypatch.setattr(settings, "enable_write_actions", False)
    monkeypatch.setattr(settings, "enable_real_connectors", False)


def _client(*, raise_app_exceptions: bool = True) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(
            app=app,
            raise_app_exceptions=raise_app_exceptions,
        ),
        base_url="http://test",
    )


async def _seed_workspace(
    marker: str,
    *,
    suffix: str = "",
    role: str = MEMBERSHIP_ROLE_OWNER,
) -> tuple[User, Workspace]:
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"headquarters-{marker}{suffix}@example.test",
            name=f"Headquarters {role}",
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name=f"Headquarters {marker}{suffix}",
            slug=f"headquarters-{marker}{suffix}",
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()
        session.add(Membership(workspace_id=workspace.id, user_id=user.id, role=role))
        await session.commit()
        return user, workspace


async def _add_member(
    *,
    workspace_id: UUID,
    marker: str,
    role: str,
) -> User:
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"headquarters-{marker}-{role}@example.test",
            name=f"Headquarters {role}",
        )
        session.add(user)
        await session.flush()
        session.add(Membership(workspace_id=workspace_id, user_id=user.id, role=role))
        await session.commit()
        return user


async def _get_headquarters(
    *,
    workspace_id: UUID,
    email: str,
    raise_app_exceptions: bool = True,
) -> tuple[int, dict, dict[str, str]]:
    async with _client(raise_app_exceptions=raise_app_exceptions) as client:
        response = await client.get(
            f"/api/v1/workspaces/{workspace_id}/headquarters",
            headers=_headers(),
            params={"owner_email": email},
        )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    return response.status_code, body, dict(response.headers)


async def _get_headquarters_onboarding(
    *,
    workspace_id: UUID,
    email: str,
) -> tuple[int, dict, dict[str, str]]:
    async with _client() as client:
        response = await client.get(
            f"/api/v1/workspaces/{workspace_id}/headquarters/onboarding",
            headers=_headers(),
            params={"owner_email": email},
        )
    return response.status_code, response.json(), dict(response.headers)


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(Workspace.slug.like(f"headquarters-{marker}%"))
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(User.email.like(f"headquarters-{marker}%@example.test"))
                )
            ).scalars()
        )
        if workspace_ids:
            briefing_ids = list(
                (
                    await session.execute(
                        select(Briefing.id).where(Briefing.workspace_id.in_(workspace_ids))
                    )
                ).scalars()
            )
            await session.execute(
                delete(ActionProposal).where(ActionProposal.workspace_id.in_(workspace_ids))
            )
            if briefing_ids:
                await session.execute(
                    delete(BriefingItem).where(BriefingItem.briefing_id.in_(briefing_ids))
                )
            await session.execute(delete(Briefing).where(Briefing.workspace_id.in_(workspace_ids)))
            await session.execute(
                delete(EvidenceRef).where(EvidenceRef.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Repository).where(Repository.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(CompanyWorldResolution).where(
                    CompanyWorldResolution.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Organization).where(Organization.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(SourceRecord).where(SourceRecord.workspace_id.in_(workspace_ids))
            )
            await session.execute(delete(SyncJob).where(SyncJob.workspace_id.in_(workspace_ids)))
            await session.execute(
                delete(IntegrationConnection).where(
                    IntegrationConnection.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Membership).where(Membership.workspace_id.in_(workspace_ids))
            )
            await session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        if user_ids:
            await session.execute(delete(Membership).where(Membership.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


def _proposal_payload(
    *,
    ref: str,
    severity: str = "critical",
    target_ref: str | None = None,
) -> dict:
    return {
        "target_provider": "github",
        "action_type": "create_github_issue",
        "title": f"Review {ref}",
        "description": "Caller-authored proposal.",
        "payload": {
            "repository_full_name": target_ref or ref,
            "title": "Caller title",
            "severity": severity,
        },
        "evidence_refs": [
            {
                "kind": "repository",
                "source": "github",
                "ref": ref,
                "url": None,
            }
        ],
        "created_by": "user",
    }


def test_contract_rejects_inconsistent_action_and_metric_states() -> None:
    with pytest.raises(ValidationError, match="disabled action requires"):
        HeadquartersActionRead(
            kind="review",
            label="Review",
            target="/actions",
            enabled=False,
        )
    with pytest.raises(ValidationError, match="unavailable metric cannot have"):
        HeadquartersPulseMetricRead(
            key="waiting_decisions",
            label="Waiting",
            value=1,
            precision="unavailable",
            empty_state="Empty",
            target="/actions",
            action={
                "kind": "open",
                "label": "Open",
                "target": "/actions",
                "enabled": True,
                "disabled_reason": None,
            },
        )


def test_onboarding_contract_preserves_unknown_and_required_readiness() -> None:
    payload = headquarters_service._build_onboarding(
        member_count=1,
        configured_source_count=None,
        canonical_source_record_count=None,
        briefing_count=0,
        decided_proposal_count=0,
        company_world=None,
        company_world_status="unavailable",
        capabilities={
            "can_manage_team": False,
            "can_manage_source": False,
            "can_import_source": False,
        },
    )

    result = HeadquartersOnboardingRead.model_validate(payload)
    steps = {step.key: step for step in result.steps}
    assert result.contract_version == "onboarding.v1"
    assert result.readiness_version == "onboarding-readiness.v1"
    assert result.ready is False
    assert result.completed_count == 2
    assert result.total_count == 5
    assert result.completed_required == 2
    assert result.required_total == 3
    assert result.current_step_key == "canonical_data"
    assert result.next_action == steps["canonical_data"].action
    assert steps["source"].state == "unknown"
    assert steps["source"].requirement == "recommended"
    assert steps["canonical_data"].state == "unknown"
    assert steps["context"].state == "unknown"
    assert all(
        fact.precision == "unavailable" and fact.value is None
        for fact in steps["canonical_data"].evidence
    )

    with pytest.raises(ValidationError, match="ready must match"):
        HeadquartersOnboardingRead.model_validate({**payload, "ready": True})

    inconsistent = json.loads(json.dumps(payload))
    inconsistent["steps"][2]["state"] = "complete"
    with pytest.raises(ValidationError, match="step state must match its evidence"):
        HeadquartersOnboardingRead.model_validate(inconsistent)


@pytest.mark.parametrize(
    "target",
    (
        "//evil.example/path",
        "/\\evil.example/path",
        "https://evidence.example/item/1",
    ),
)
def test_action_targets_are_internal_but_evidence_can_link_to_web(
    target: str,
) -> None:
    with pytest.raises(ValidationError, match="safe internal path"):
        HeadquartersActionRead(
            kind="open",
            label="Open",
            target=target,
            enabled=True,
        )

    evidence = HeadquartersEvidenceRefRead(
        id="repository:1",
        kind="repository",
        source_key="github",
        label="Evidence",
        target="https://evidence.example/item/1",
        provenance="canonical_repository",
        trust="verified",
        reference_type="repository",
        reference_id="1",
        workspace_scoped=True,
    )
    assert evidence.target == "https://evidence.example/item/1"

    for invalid_target in (
        "https://evidence.example:99999/item/1",
        "https://evidence.example/item/1?access_token=do-not-render",
    ):
        with pytest.raises(ValidationError, match="safe internal path or web URL"):
            HeadquartersEvidenceRefRead(
                id="repository:invalid-url",
                kind="repository",
                source_key="github",
                label="Invalid evidence",
                target=invalid_target,
                provenance="canonical_repository",
                trust="verified",
                reference_type="repository",
                reference_id="invalid-url",
                workspace_scoped=True,
            )


def test_source_aliases_and_correlation_are_explicit_and_deterministic() -> None:
    assert headquarters_service._source_key("github") == "github"
    assert headquarters_service._source_key("canonical_github_company_brain") == "github"
    assert headquarters_service._source_key("github-jira") is None
    assert headquarters_service._source_alias_is_supported("github-jira") is False

    aggregate = headquarters_service._aggregate_evidence(
        identity="source_inventory:test:ready",
        label="Test aggregate",
        target="/connectors",
    )
    mission = headquarters_service._mission(
        identity="setup:test",
        kind="connect_source",
        reference_type="setup",
        reference_id="test",
        title="Test",
        summary="Test",
        why_now="Test",
        status="setup",
        severity="info",
        confidence=1.0,
        next_step="Test",
        source_keys=["github", "jira"],
        evidence_refs=[aggregate],
        action=headquarters_service._action(
            kind="open",
            label="Open",
            target="/connectors",
            enabled=True,
        ),
        ranking_reason="source_setup_gap",
    )
    assert mission["correlation_reason"] is None
    assert mission["correlation_rule_version"] is None


async def test_empty_headquarters_is_deterministic_and_read_only(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)

        first_status, first, first_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        second_status, second, _second_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        onboarding_status, onboarding, onboarding_headers = await _get_headquarters_onboarding(
            workspace_id=workspace.id,
            email=owner.email,
        )

        assert first_status == second_status == onboarding_status == 200
        assert first["contract_version"] == "headquarters.v2"
        assert first["ranking_version"] == "headquarters-ranking.v1"
        assert first["snapshot"]["id"] == second["snapshot"]["id"]
        assert first["snapshot"]["as_of"] != second["snapshot"]["as_of"]
        assert first_headers["etag"] == f'"{first["snapshot"]["id"]}"'
        assert first_headers["cache-control"] == "private, no-store"
        assert set(onboarding) == {
            "contract_version",
            "snapshot",
            "workspace",
            "onboarding",
            "capabilities",
            "boundary",
        }
        assert onboarding["snapshot"]["id"] == first["snapshot"]["id"]
        assert onboarding["workspace"] == first["workspace"]
        assert onboarding["onboarding"] == first["onboarding"]
        assert onboarding["capabilities"] == first["capabilities"]
        assert onboarding["boundary"] == first["boundary"]
        assert onboarding_headers["etag"] == f'"{first["snapshot"]["id"]}"'
        assert onboarding_headers["cache-control"] == "private, no-store"
        assert [metric["key"] for metric in first["pulse"]] == [
            "waiting_decisions",
            "sources_attention",
            "pending_relationships",
        ]
        assert first["pulse"][0]["value"] == 0
        assert first["pulse"][0]["precision"] == "exact"
        assert first["priority"]["id"] == "setup:connect-source"
        assert first["priority"]["evidence_state"] == "aggregate"
        onboarding_steps = {step["key"]: step for step in first["onboarding"]["steps"]}
        assert first["onboarding"]["contract_version"] == "onboarding.v1"
        assert first["onboarding"]["readiness_version"] == "onboarding-readiness.v1"
        assert first["onboarding"]["ready"] is False
        assert first["onboarding"]["completed_count"] == 2
        assert first["onboarding"]["total_count"] == 5
        assert first["onboarding"]["completed_required"] == 2
        assert first["onboarding"]["required_total"] == 3
        assert first["onboarding"]["current_step_key"] == "canonical_data"
        assert first["onboarding"]["next_action"]["target"] == "/connectors"
        assert list(onboarding_steps) == [
            "company",
            "source",
            "canonical_data",
            "context",
            "headquarters",
        ]
        assert onboarding_steps["company"]["requirement"] == "required"
        assert onboarding_steps["company"]["state"] == "complete"
        assert onboarding_steps["source"]["requirement"] == "recommended"
        assert onboarding_steps["source"]["state"] == "pending"
        assert onboarding_steps["canonical_data"]["requirement"] == "required"
        assert onboarding_steps["canonical_data"]["state"] == "pending"
        assert onboarding_steps["headquarters"]["requirement"] == "required"
        assert onboarding_steps["headquarters"]["state"] == "complete"
        assert onboarding_steps["context"]["requirement"] == "recommended"
        assert onboarding_steps["context"]["state"] == "pending"
        assert onboarding_steps["context"]["action"]["target"] == "/settings"
        assert len(first["queue"]) <= 2
        assert len(first["changes"]["items"]) <= 3
        assert first["changes"] == {
            "items": [],
            "basis": "current_snapshot",
            "cursor": None,
            "since_checkpoint": False,
        }
        assert first["boundary"] == {
            "provider_calls": False,
            "external_writes": False,
            "llm": False,
            "reads_secrets": False,
            "transaction": "repeatable_read_read_only",
        }
    finally:
        await _cleanup(marker)


async def test_ranking_uses_workspace_verified_evidence_and_trusted_severity(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        other_owner, other_workspace = await _seed_workspace(marker, suffix="-other")
        repository_name = f"founderos/headquarters-{marker}"
        unrelated_repository_name = f"founderos/unrelated-{marker}"
        foreign_repository_name = f"foreign/headquarters-{marker}"
        evidence = [
            {
                "kind": "repository",
                "source": "github",
                "ref": repository_name,
                "url": None,
            }
        ]
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            session.add_all(
                [
                    Repository(
                        workspace_id=workspace.id,
                        provider="github",
                        external_id=f"repo-{marker}",
                        name=f"headquarters-{marker}",
                        full_name=repository_name,
                        visibility="private",
                    ),
                    Repository(
                        workspace_id=other_workspace.id,
                        provider="github",
                        external_id=f"foreign-{marker}",
                        name=f"foreign-{marker}",
                        full_name=foreign_repository_name,
                        visibility="private",
                    ),
                    Repository(
                        workspace_id=workspace.id,
                        provider="github",
                        external_id=f"unrelated-{marker}",
                        name=f"unrelated-{marker}",
                        full_name=unrelated_repository_name,
                        visibility="private",
                    ),
                ]
            )
            briefing = Briefing(
                workspace_id=workspace.id,
                created_by_user_id=owner.id,
                generated_by="deterministic_v0",
                title="Trusted briefing",
                summary="Trusted summary",
                as_of=now,
                signals={},
                warnings=[],
            )
            session.add(briefing)
            await session.flush()
            item = BriefingItem(
                briefing_id=briefing.id,
                position=0,
                item_key="trusted-action",
                category="risk",
                title="Trusted action",
                summary="Trusted briefing item",
                severity="high",
                confidence=0.9,
                recommended_next_step="Review it",
                evidence_refs=evidence,
                related_entities=[],
                warnings=[],
            )
            session.add(item)
            await session.flush()
            trusted_item_id = item.id
            session.add(
                ActionProposal(
                    workspace_id=workspace.id,
                    briefing_item_id=item.id,
                    target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
                    action_type=ACTION_TYPE_INTERNAL_TODO,
                    title="Trusted system proposal",
                    description="Created from the persisted briefing item.",
                    payload={"severity": "low"},
                    evidence_refs=evidence,
                    created_by=ACTION_CREATED_BY_SYSTEM,
                    created_by_user_id=None,
                )
            )
            unresolved_evidence = [
                {
                    "kind": "repository",
                    "source": "github",
                    "ref": f"unresolved-system/{marker}",
                    "url": None,
                }
            ]
            unresolved_item = BriefingItem(
                briefing_id=briefing.id,
                position=1,
                item_key="unresolved-system-action",
                category="risk",
                title="Unresolved system action",
                summary="A matching briefing item is not sufficient evidence.",
                severity="critical",
                confidence=0.99,
                recommended_next_step="Do not rank it",
                evidence_refs=unresolved_evidence,
                related_entities=[],
                warnings=[],
            )
            session.add(unresolved_item)
            await session.flush()
            session.add(
                ActionProposal(
                    workspace_id=workspace.id,
                    briefing_item_id=unresolved_item.id,
                    target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
                    action_type=ACTION_TYPE_INTERNAL_TODO,
                    title="Unresolved critical system proposal",
                    description="Its matching evidence ref does not resolve canonically.",
                    payload={},
                    evidence_refs=unresolved_evidence,
                    created_by=ACTION_CREATED_BY_SYSTEM,
                    created_by_user_id=None,
                )
            )
            deleted_source = SourceRecord(
                workspace_id=workspace.id,
                provider="github",
                external_id=f"deleted-{marker}",
                record_type="repository",
                source_url=None,
                payload={},
                payload_hash=f"deleted-payload-{marker}",
                observed_at=now,
                source_updated_at=now,
                is_deleted=True,
            )
            session.add(deleted_source)
            await session.flush()
            deleted_evidence = EvidenceRef(
                workspace_id=workspace.id,
                source_record_id=deleted_source.id,
                source_url=None,
            )
            session.add(deleted_evidence)
            await session.flush()
            deleted_evidence_id = deleted_evidence.id
            await session.commit()

        async with _client() as client:
            valid = await client.post(
                f"/api/v1/workspaces/{workspace.id}/actions/proposals",
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_proposal_payload(ref=repository_name, severity="critical"),
            )
            missing = await client.post(
                f"/api/v1/workspaces/{workspace.id}/actions/proposals",
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_proposal_payload(ref=f"missing/{marker}"),
            )
            foreign = await client.post(
                f"/api/v1/workspaces/{workspace.id}/actions/proposals",
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_proposal_payload(ref=foreign_repository_name),
            )
            unrelated = await client.post(
                f"/api/v1/workspaces/{workspace.id}/actions/proposals",
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_proposal_payload(
                    ref=repository_name,
                    target_ref=unrelated_repository_name,
                ),
            )
            deleted = await client.post(
                f"/api/v1/workspaces/{workspace.id}/actions/proposals",
                headers=_headers(),
                params={"owner_email": owner.email},
                json=_proposal_payload(ref=str(deleted_evidence_id)),
            )
            provider_mismatch_payload = _proposal_payload(ref=repository_name)
            provider_mismatch_payload["evidence_refs"][0]["source"] = "jira"
            provider_mismatch = await client.post(
                f"/api/v1/workspaces/{workspace.id}/actions/proposals",
                headers=_headers(),
                params={"owner_email": owner.email},
                json=provider_mismatch_payload,
            )
            missing_explicit_payload = _proposal_payload(ref=repository_name)
            missing_explicit_payload["evidence_refs"][0]["evidence_ref_id"] = str(uuid4())
            missing_explicit = await client.post(
                f"/api/v1/workspaces/{workspace.id}/actions/proposals",
                headers=_headers(),
                params={"owner_email": owner.email},
                json=missing_explicit_payload,
            )
            spoofed_origin_payload = _proposal_payload(ref=repository_name)
            spoofed_origin_payload["created_by"] = "ai"
            spoofed_origin = await client.post(
                f"/api/v1/workspaces/{workspace.id}/actions/proposals",
                headers=_headers(),
                params={"owner_email": owner.email},
                json=spoofed_origin_payload,
            )

        assert (
            valid.status_code
            == missing.status_code
            == foreign.status_code
            == unrelated.status_code
            == deleted.status_code
            == provider_mismatch.status_code
            == missing_explicit.status_code
            == 201
        )
        assert spoofed_origin.status_code == 422

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert status_code == 200
        assert body["priority"]["title"] == "Trusted system proposal"
        assert body["priority"]["severity"] == "high"
        assert body["priority"]["proposal_version"].startswith("ap1_")
        assert body["priority"]["ranking_reason"] == "verified_proposal"
        assert body["priority"]["action"]["target"] == (
            f"/actions?proposal={body['priority']['proposal_id']}&status=proposed"
        )
        assert body["pulse"][0]["value"] == 2
        assert body["queue"][0]["id"] == f"proposal:{valid.json()['proposal']['id']}"
        assert body["queue"][0]["severity"] == "unknown"
        assert body["queue"][0]["action"]["target"] == (
            f"/actions?proposal={body['queue'][0]['proposal_id']}&status=proposed"
        )
        assert "critical" not in body["queue"][0]["fact_provenance"]
        assert "Unresolved critical system proposal" not in str(body)
        assert any(
            warning == "proposals_excluded_unverified_or_unrelated_evidence:7"
            for warning in body["snapshot"]["warnings"]
        )
        assert f"proposal:{unrelated.json()['proposal']['id']}" not in str(body)
        assert f"proposal:{provider_mismatch.json()['proposal']['id']}" not in str(body)
        assert f"proposal:{missing_explicit.json()['proposal']['id']}" not in str(body)
        assert other_owner.email not in str(body)
        assert foreign_repository_name not in str(body)

        trusted_version = body["priority"]["proposal_version"]
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(BriefingItem)
                .where(BriefingItem.id == trusted_item_id)
                .values(severity="critical", confidence=0.8)
            )
            await session.commit()

        changed_status, changed, _changed_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert changed_status == 200
        assert changed["priority"]["severity"] == "critical"
        assert changed["priority"]["confidence"] == 0.8
        assert changed["priority"]["proposal_version"] != trusted_version
    finally:
        await _cleanup(marker)


async def test_proposal_version_binds_exact_evidence_and_full_action_content(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        repository_name = f"founderos/source-record-{marker}"
        observed_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            source_record = SourceRecord(
                workspace_id=workspace.id,
                provider="github",
                external_id=repository_name,
                record_type="repository",
                source_url=None,
                payload={},
                payload_hash=f"payload-v1-{marker}",
                observed_at=observed_at,
                source_updated_at=observed_at,
            )
            session.add(source_record)
            await session.flush()
            evidence_ref = EvidenceRef(
                workspace_id=workspace.id,
                source_record_id=source_record.id,
                quote="Exact field evidence",
                field_path="repository.full_name",
                source_url=None,
            )
            session.add(evidence_ref)
            await session.flush()
            proposal = ActionProposal(
                workspace_id=workspace.id,
                target_provider="github",
                action_type="create_github_issue",
                title="Create a bounded follow-up",
                description="EvidenceRef-backed proposal.",
                payload={
                    "repository_full_name": repository_name,
                    "title": "First title",
                },
                evidence_refs=[
                    {
                        "kind": "repository",
                        "source": "github",
                        "evidence_ref_id": str(evidence_ref.id),
                    }
                ],
                created_by=ACTION_CREATED_BY_USER,
                created_by_user_id=owner.id,
            )
            session.add(proposal)
            await session.commit()
            proposal_id = proposal.id
            evidence_ref_id = evidence_ref.id
            source_record_id = source_record.id

        first_status, first, _first_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert first_status == 200
        first_mission = first["priority"]
        assert first_mission["proposal_id"] == str(proposal_id)
        assert first_mission["evidence_refs"][0]["id"] == (f"evidence_ref:{evidence_ref_id}")
        assert first_mission["evidence_refs"][0]["reference_type"] == "evidence_ref"
        first_version = first_mission["proposal_version"]

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(SourceRecord)
                .where(SourceRecord.id == source_record_id)
                .values(payload_hash=f"payload-v2-{marker}")
            )
            await session.commit()

        second_status, second, _second_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert second_status == 200
        second_version = second["priority"]["proposal_version"]
        assert second_version != first_version

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(SourceRecord)
                .where(SourceRecord.id == source_record_id)
                .values(source_url="https://evidence.example/ malformed")
            )
            await session.commit()

        third_status, third, _third_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert third_status == 200
        third_version = third["priority"]["proposal_version"]
        assert third_version != second_version
        assert third["priority"]["evidence_refs"][0]["target"] is None

        async with AsyncSessionLocal() as session:
            original_updated_at = await session.scalar(
                select(ActionProposal.updated_at).where(ActionProposal.id == proposal_id)
            )
            await session.execute(
                update(ActionProposal)
                .where(ActionProposal.id == proposal_id)
                .values(
                    payload={
                        "repository_full_name": repository_name,
                        "title": "Changed title with same row timestamp",
                    },
                    updated_at=original_updated_at,
                )
            )
            await session.commit()

        fourth_status, fourth, _fourth_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert fourth_status == 200
        assert fourth["priority"]["proposal_version"] != third_version
    finally:
        await _cleanup(marker)


async def test_company_world_mission_uses_opaque_selector(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        external_email = f"buyer-{marker}@customer.test"
        observed_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            session.add(
                SourceRecord(
                    workspace_id=workspace.id,
                    provider="gmail",
                    external_id=f"message-{marker}",
                    record_type="message",
                    source_url=None,
                    payload={
                        "normalized_message": {
                            "message_id": f"message-{marker}",
                            "subject": "Customer kickoff",
                            "from_address": owner.email,
                            "to_addresses": [external_email],
                            "received_at": observed_at.isoformat(),
                        },
                        "evidence_refs": [
                            {
                                "kind": "gmail_message",
                                "source": "gmail",
                                "ref": f"message-{marker}",
                                "url": None,
                            }
                        ],
                    },
                    payload_hash=f"payload-{marker}",
                    observed_at=observed_at,
                    source_updated_at=observed_at,
                )
            )
            await session.commit()

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )

        assert status_code == 200
        assert body["priority"]["kind"] == "review_world"
        assert body["priority"]["id"].startswith("world:")
        assert "@" not in body["priority"]["id"]
        assert external_email not in body["priority"]["id"]
        assert "customer.test" not in body["priority"]["reference_id"]
        candidate_type = body["priority"]["id"].split(":", maxsplit=2)[1]
        selector_kind = (
            "person-candidate" if candidate_type == "person" else "organization-candidate"
        )
        candidate_version = body["priority"]["reference_id"].rsplit(":", maxsplit=1)[1]
        assert body["priority"]["action"]["target"] == (
            "/company-brain?"
            f"profile=v1%3A{selector_kind}%3A{candidate_version}"
            "#company-world-profile"
        )
        assert body["pulse"][2]["value"] == 2
        gmail = next(item for item in body["sources"]["items"] if item["key"] == "gmail")
        assert gmail["configuration"] == "disconnected"
        assert gmail["data"] == "available"
        assert gmail["last_success_at"] is None
        assert gmail["last_data_observed_at"] is not None
        assert gmail["freshness_policy_version"] == "source-health.v1"
        assert gmail["connection_count"] == 0
        assert gmail["record_count"] == 1
        assert gmail["record_count_precision"] == "exact"
    finally:
        await _cleanup(marker)


async def test_headquarters_company_world_uses_resolution_only_projection(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        external_email = f"resolved-{marker}@customer.test"
        durable_email = f"confirmed-{marker}@durable.test"
        observed_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            source_record = SourceRecord(
                workspace_id=workspace.id,
                provider="gmail",
                external_id=f"resolved-message-{marker}",
                record_type="message",
                source_url=None,
                payload={
                    "normalized_message": {
                        "message_id": f"resolved-message-{marker}",
                        "subject": "Resolved customer",
                        "from_address": owner.email,
                        "to_addresses": [external_email, durable_email],
                        "received_at": observed_at.isoformat(),
                    }
                },
                payload_hash=f"resolved-payload-{marker}",
                observed_at=observed_at,
                source_updated_at=observed_at,
            )
            session.add(source_record)
            await session.commit()
            await session.refresh(source_record)

            unresolved = await company_map_service.build_workspace_company_map(
                session=session,
                workspace_id=workspace.id,
                limit=100,
                include_durable=False,
                access_role=MEMBERSHIP_ROLE_OWNER,
            )
            person_candidates = unresolved["people"]["external_candidates"]
            person_candidate = next(
                row for row in person_candidates if row["email"] == external_email
            )
            durable_person_candidate = next(
                row for row in person_candidates if row["email"] == durable_email
            )
            organization_candidate = next(
                row for row in unresolved["organizations"] if row["domain"] == "customer.test"
            )
            durable_organization_candidate = next(
                row for row in unresolved["organizations"] if row["domain"] == "durable.test"
            )
            session.add_all(
                [
                    CompanyWorldResolution(
                        workspace_id=workspace.id,
                        candidate_type=RESOLUTION_CANDIDATE_EXTERNAL_PERSON,
                        candidate_key=person_candidate["key"],
                        candidate_version=person_candidate["candidate_version"],
                        decision=RESOLUTION_DECISION_DISMISSED,
                        idempotency_key=f"resolved-person-{marker}",
                        request_hash="a" * 64,
                        actor_user_id=owner.id,
                        source_record_id=source_record.id,
                    ),
                    CompanyWorldResolution(
                        workspace_id=workspace.id,
                        candidate_type=RESOLUTION_CANDIDATE_EXTERNAL_PERSON,
                        candidate_key=durable_person_candidate["key"],
                        candidate_version=durable_person_candidate["candidate_version"],
                        decision=RESOLUTION_DECISION_DISMISSED,
                        idempotency_key=f"durable-person-{marker}",
                        request_hash="c" * 64,
                        actor_user_id=owner.id,
                        source_record_id=source_record.id,
                    ),
                    CompanyWorldResolution(
                        workspace_id=workspace.id,
                        candidate_type=RESOLUTION_CANDIDATE_ORGANIZATION,
                        candidate_key=organization_candidate["key"],
                        candidate_version=organization_candidate["candidate_version"],
                        decision=RESOLUTION_DECISION_DISMISSED,
                        idempotency_key=f"resolved-organization-{marker}",
                        request_hash="b" * 64,
                        actor_user_id=owner.id,
                        source_record_id=source_record.id,
                    ),
                    Organization(
                        workspace_id=workspace.id,
                        canonical_key=durable_organization_candidate["key"],
                        normalized_domain="durable.test",
                        display_name="Durable customer",
                        confirmed_by_user_id=owner.id,
                        confirmed_at=observed_at,
                    ),
                ]
            )
            await session.commit()

        async def forbidden_full_durable_read(**_kwargs):
            raise AssertionError("HQ must not materialize the full durable company world")

        monkeypatch.setattr(
            company_map_service,
            "_durable_company_world_rows",
            forbidden_full_durable_read,
        )
        async with AsyncSessionLocal() as session:
            projection = await headquarters_service._read_company_world_projection(
                session=session,
                workspace_id=workspace.id,
                role=MEMBERSHIP_ROLE_OWNER,
            )

        assert projection["window"]["gmail_messages_considered"] == 1
        assert projection["people"]["external_candidates"] == []
        assert projection["organizations"] == []
        assert projection["people"]["confirmed_external"] == []
        assert projection["confirmed_organizations"] == []
        assert projection["summary"]["external_contacts_in_window"] == 0
        assert projection["summary"]["organizations_in_window"] == 0
    finally:
        await _cleanup(marker)


async def test_headquarters_company_world_uses_bounded_gmail_window_without_full_brain(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        started_at = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
        async with AsyncSessionLocal() as session:
            session.add_all(
                [
                    SourceRecord(
                        workspace_id=workspace.id,
                        provider="gmail",
                        external_id=f"bounded-message-{marker}-{index}",
                        record_type="message",
                        source_url=None,
                        payload={
                            "normalized_message": {
                                "message_id": f"bounded-message-{marker}-{index}",
                                "subject": f"Bounded message {index}",
                                "from_address": f"contact-{index}@customer.test",
                                "to_addresses": [owner.email],
                            },
                            "evidence_refs": [
                                {
                                    "kind": "gmail_message",
                                    "source": "github" if index % 2 else "jira",
                                    "ref": f"spoofed-source-{marker}-{index}",
                                }
                            ],
                        },
                        payload_hash=f"bounded-payload-{marker}-{index}",
                        observed_at=started_at + timedelta(minutes=index),
                        source_updated_at=started_at + timedelta(minutes=index),
                    )
                    for index in range(101)
                ]
            )
            await session.commit()

        async def forbidden_full_brain(**_kwargs):
            raise AssertionError("HQ must not build the full company brain")

        async def forbidden_full_membership_read(*_args, **_kwargs):
            raise AssertionError("HQ must not materialize all workspace members")

        monkeypatch.setattr(
            company_map_service,
            "build_workspace_company_brain",
            forbidden_full_brain,
        )
        monkeypatch.setattr(
            company_map_service,
            "list_workspace_members",
            forbidden_full_membership_read,
        )
        async with AsyncSessionLocal() as session:
            projection = await headquarters_service._read_company_world_projection(
                session=session,
                workspace_id=workspace.id,
                role=MEMBERSHIP_ROLE_OWNER,
            )

        assert projection["window"] == {
            "gmail_messages_available": 101,
            "gmail_messages_considered": 100,
            "message_limit": 100,
            "truncated": True,
            "order": "newest_first",
        }
        assert projection["summary"]["external_contacts_in_window"] == 100
        assert projection["summary"]["organizations_in_window"] == 1
        assert projection["summary"]["touchpoints_in_window"] == 100
        assert {ref["source"] for ref in projection["organizations"][0]["source_refs"]} == {"gmail"}
        subjects = {row["subject"] for row in projection["touchpoints"]}
        assert "Bounded message 100" in subjects
        assert "Bounded message 1" in subjects
        assert "Bounded message 0" not in subjects

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert status_code == 200
        company_world_coverage = next(
            item for item in body["snapshot"]["coverage"] if item["key"] == "company_world"
        )
        assert company_world_coverage["status"] == "partial"
        assert company_world_coverage["warning"] == "company_world_window_truncated"
        assert body["pulse"][2]["value"] == 101
        assert body["pulse"][2]["precision"] == "at_least"
    finally:
        await _cleanup(marker)


async def test_onboarding_ready_uses_required_canonical_data_only(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        observed_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            session.add(
                SourceRecord(
                    workspace_id=workspace.id,
                    provider="internal",
                    external_id=f"internal-{marker}",
                    record_type="document",
                    source_url=None,
                    payload={},
                    payload_hash=f"internal-payload-{marker}",
                    observed_at=observed_at,
                    source_updated_at=observed_at,
                )
            )
            session.add(
                ActionProposal(
                    workspace_id=workspace.id,
                    target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
                    action_type=ACTION_TYPE_INTERNAL_TODO,
                    title="Completed local decision",
                    description=None,
                    payload={},
                    evidence_refs=[],
                    status=ACTION_PROPOSAL_STATUS_APPROVED,
                    created_by=ACTION_CREATED_BY_USER,
                    created_by_user_id=owner.id,
                )
            )
            await session.commit()

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )

        assert status_code == 200
        steps = {step["key"]: step for step in body["onboarding"]["steps"]}
        assert body["sources"]["data_ready_count"] == 0
        assert body["onboarding"]["ready"] is True
        assert body["onboarding"]["completed_required"] == 3
        assert body["onboarding"]["required_total"] == 3
        assert body["onboarding"]["current_step_key"] is None
        assert body["onboarding"]["next_action"] is None
        assert steps["source"]["state"] == "pending"
        assert steps["source"]["requirement"] == "recommended"
        assert steps["canonical_data"]["state"] == "complete"
        assert steps["canonical_data"]["requirement"] == "required"
        assert steps["context"]["state"] == "complete"
        assert steps["context"]["requirement"] == "recommended"
        context_facts = {fact["key"]: fact for fact in steps["context"]["evidence"]}
        assert context_facts["decisions"]["state"] == "complete"
        assert context_facts["decisions"]["value"] == 1
    finally:
        await _cleanup(marker)


async def test_configured_source_without_data_is_exact_attention(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        async with AsyncSessionLocal() as session:
            session.add(
                IntegrationConnection(
                    workspace_id=workspace.id,
                    provider="jira",
                    status="error",
                    display_name="Jira workspace",
                    scopes=["project:read"],
                )
            )
            await session.commit()

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )

        assert status_code == 200
        jira = next(item for item in body["sources"]["items"] if item["key"] == "jira")
        assert jira["configuration"] == "configured"
        assert jira["read"] == "failed"
        assert jira["data"] == "empty"
        assert jira["freshness"] == "unknown"
        assert jira["primary_state"] == "failed"
        assert jira["connection_count"] == 1
        assert jira["record_count"] == 0
        assert body["sources"]["attention_count"] == 1
        assert body["pulse"][1]["value"] == 1
        assert body["pulse"][1]["precision"] == "exact"
        assert body["priority"]["kind"] == "source_attention"
        assert body["priority"]["evidence_state"] == "aggregate"
        assert body["priority"]["trust_class"] == "aggregate"
        assert {ref["reference_type"] for ref in body["priority"]["evidence_refs"]} == {
            "headquarters_snapshot"
        }
        assert body["snapshot"]["partial"] is False
        sources_coverage = next(
            item for item in body["snapshot"]["coverage"] if item["key"] == "sources"
        )
        assert sources_coverage["status"] == "complete"
        assert "source_projection_partial" not in body["snapshot"]["warnings"]
    finally:
        await _cleanup(marker)


async def test_inactive_connections_and_old_failed_jobs_do_not_drive_current_health(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        async with AsyncSessionLocal() as session:
            disabled = IntegrationConnection(
                workspace_id=workspace.id,
                provider="jira",
                status=INTEGRATION_CONNECTION_STATUS_DISABLED,
                display_name="Disabled Jira",
                scopes=["project:read"],
            )
            revoked = IntegrationConnection(
                workspace_id=workspace.id,
                provider="jira",
                status=INTEGRATION_CONNECTION_STATUS_REVOKED,
                display_name="Revoked Jira",
                scopes=["project:read"],
            )
            github = IntegrationConnection(
                workspace_id=workspace.id,
                provider="github",
                status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
                display_name="Active GitHub",
                scopes=["repo:read"],
            )
            session.add_all([disabled, revoked, github])
            await session.flush()
            session.add_all(
                [
                    SyncJob(
                        workspace_id=workspace.id,
                        connection_id=disabled.id,
                        provider="jira",
                        status=SYNC_JOB_STATUS_FAILED,
                    ),
                    SyncJob(
                        workspace_id=workspace.id,
                        connection_id=revoked.id,
                        provider="jira",
                        status=SYNC_JOB_STATUS_FAILED,
                    ),
                    SyncJob(
                        workspace_id=workspace.id,
                        connection_id=github.id,
                        provider="jira",
                        status=SYNC_JOB_STATUS_FAILED,
                    ),
                    ActionProposal(
                        workspace_id=workspace.id,
                        target_provider=ACTION_TARGET_PROVIDER_INTERNAL,
                        action_type=ACTION_TYPE_INTERNAL_TODO,
                        title="Do not trust inactive connection evidence",
                        description=None,
                        payload={},
                        evidence_refs=[
                            {
                                "kind": "integration_connection",
                                "source": "jira",
                                "ref": str(disabled.id),
                            }
                        ],
                        created_by=ACTION_CREATED_BY_USER,
                        created_by_user_id=owner.id,
                    ),
                ]
            )
            await session.commit()

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert status_code == 200
        jira = next(item for item in body["sources"]["items"] if item["key"] == "jira")
        assert jira["configuration"] == "disconnected"
        assert jira["connection_count"] == 0
        assert jira["read"] == "idle"
        assert jira["primary_state"] == "setup"
        assert jira["last_attempt_at"] is None
        assert jira["safe_debug_id"] is None
        github_health = next(item for item in body["sources"]["items"] if item["key"] == "github")
        assert github_health["configuration"] == "configured"
        assert github_health["read"] == "idle"
        assert github_health["primary_state"] == "no_data"
        assert body["sources"]["attention_count"] == 1
        assert body["priority"]["reference_id"] == "github"
        assert body["priority"]["trust_class"] == "aggregate"
        assert body["pulse"][0]["value"] == 0
        assert "Do not trust inactive connection evidence" not in str(body)
    finally:
        await _cleanup(marker)


async def test_multi_connection_error_mission_uses_exact_aggregate_provenance(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            errored = IntegrationConnection(
                workspace_id=workspace.id,
                provider="jira",
                status="error",
                display_name="Errored Jira",
                scopes=["project:read"],
            )
            connected = IntegrationConnection(
                workspace_id=workspace.id,
                provider="jira",
                status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
                display_name="Newest connected Jira",
                scopes=["project:read"],
            )
            session.add_all([errored, connected])
            await session.flush()
            await session.execute(
                update(IntegrationConnection)
                .where(IntegrationConnection.id == errored.id)
                .values(updated_at=now)
            )
            await session.execute(
                update(IntegrationConnection)
                .where(IntegrationConnection.id == connected.id)
                .values(updated_at=now + timedelta(seconds=1))
            )
            await session.commit()

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert status_code == 200
        jira = next(item for item in body["sources"]["items"] if item["key"] == "jira")
        assert jira["connection_count"] == 2
        assert jira["read"] == "failed"
        assert jira["primary_state"] == "failed"
        assert body["priority"]["kind"] == "source_attention"
        assert body["priority"]["trust_class"] == "aggregate"
        assert len(body["priority"]["evidence_refs"]) == 1
        assert body["priority"]["evidence_refs"][0]["trust"] == "aggregate"
        assert body["priority"]["evidence_refs"][0]["source_key"] == "jira"
    finally:
        await _cleanup(marker)


async def test_large_source_history_uses_bounded_aggregate_material(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            connection = IntegrationConnection(
                workspace_id=workspace.id,
                provider="jira",
                status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
                display_name="Large Jira",
                scopes=["project:read"],
                last_sync_at=now,
            )
            session.add(connection)
            await session.flush()
            jobs = [
                SyncJob(
                    workspace_id=workspace.id,
                    connection_id=connection.id,
                    provider="jira",
                    status=SYNC_JOB_STATUS_SUCCEEDED,
                    started_at=now - timedelta(minutes=index + 1),
                    finished_at=now - timedelta(minutes=index),
                    records_seen=index,
                )
                for index in range(120)
            ]
            records = [
                SourceRecord(
                    workspace_id=workspace.id,
                    provider="jira",
                    connection_id=connection.id,
                    external_id=f"LARGE-{marker}-{index}",
                    record_type="issue",
                    payload={},
                    payload_hash=f"large-hash-{marker}-{index}",
                    observed_at=now - timedelta(seconds=index),
                    source_updated_at=now - timedelta(seconds=index),
                )
                for index in range(150)
            ]
            session.add_all([*jobs, *records])
            await session.commit()

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert status_code == 200
        jira = next(item for item in body["sources"]["items"] if item["key"] == "jira")
        assert jira["connection_count"] == 1
        assert jira["record_count"] == 150
        assert jira["record_count_precision"] == "exact"

        async with AsyncSessionLocal() as session:
            (
                sources,
                _evidence,
                material,
                canonical_count,
            ) = await headquarters_service._read_sources(
                session=session,
                workspace_id=workspace.id,
                role=MEMBERSHIP_ROLE_OWNER,
                as_of=now,
            )
        assert sources["count_precision"] == "exact"
        assert canonical_count == 150
        assert len(material["connections"]) == 1
        assert len(material["jobs"]) == 1
        assert material["jobs"][0]["job_count"] == 120
        assert len(material["records"]) == 1
        assert material["records"][0]["record_count"] == 150
    finally:
        await _cleanup(marker)


async def test_bounded_proposal_window_reports_lower_bound_and_partial(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(headquarters_service, "HEADQUARTERS_PROPOSAL_SCAN_LIMIT", 2)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        repository_name = f"founderos/bounded-{marker}"
        async with AsyncSessionLocal() as session:
            session.add(
                Repository(
                    workspace_id=workspace.id,
                    provider="github",
                    external_id=f"bounded-{marker}",
                    name=f"bounded-{marker}",
                    full_name=repository_name,
                    visibility="private",
                )
            )
            session.add_all(
                [
                    ActionProposal(
                        workspace_id=workspace.id,
                        target_provider="github",
                        action_type="create_github_issue",
                        title=f"Bounded proposal {index}",
                        description=None,
                        payload={"repository_full_name": repository_name},
                        evidence_refs=[
                            {
                                "kind": "repository",
                                "source": "github",
                                "ref": repository_name,
                            }
                        ],
                        created_by=ACTION_CREATED_BY_USER,
                        created_by_user_id=owner.id,
                    )
                    for index in range(3)
                ]
            )
            await session.commit()

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert status_code == 200
        assert body["pulse"][0]["value"] == 2
        assert body["pulse"][0]["precision"] == "at_least"
        assert body["snapshot"]["partial"] is True
        decisions_coverage = next(
            item for item in body["snapshot"]["coverage"] if item["key"] == "decisions"
        )
        assert decisions_coverage["status"] == "partial"
        assert decisions_coverage["warning"] == "decision_window_truncated"
        assert "decision_window_truncated:3:2" in body["snapshot"]["warnings"]
    finally:
        await _cleanup(marker)


async def test_oversized_legacy_proposal_json_is_counted_but_not_materialized(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(
        headquarters_service,
        "ACTION_PROPOSAL_PAYLOAD_MAX_BYTES",
        256,
    )
    monkeypatch.setattr(
        headquarters_service,
        "ACTION_PROPOSAL_EVIDENCE_REFS_MAX_BYTES",
        256,
    )
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        repository_name = f"founderos/oversized-{marker}"
        evidence = [
            {
                "kind": "repository",
                "source": "github",
                "ref": repository_name,
            }
        ]
        async with AsyncSessionLocal() as session:
            session.add(
                Repository(
                    workspace_id=workspace.id,
                    provider="github",
                    external_id=f"oversized-{marker}",
                    name=f"oversized-{marker}",
                    full_name=repository_name,
                    visibility="private",
                )
            )
            session.add_all(
                [
                    ActionProposal(
                        workspace_id=workspace.id,
                        target_provider="github",
                        action_type="create_github_issue",
                        title="Safe proposal",
                        description=None,
                        payload={"repository_full_name": repository_name},
                        evidence_refs=evidence,
                        created_by=ACTION_CREATED_BY_USER,
                        created_by_user_id=owner.id,
                    ),
                    ActionProposal(
                        workspace_id=workspace.id,
                        target_provider="github",
                        action_type="create_github_issue",
                        title="Legacy oversized payload",
                        description=None,
                        payload={
                            "repository_full_name": repository_name,
                            "legacy_blob": "x" * 400,
                        },
                        evidence_refs=evidence,
                        created_by=ACTION_CREATED_BY_USER,
                        created_by_user_id=owner.id,
                    ),
                    ActionProposal(
                        workspace_id=workspace.id,
                        target_provider="github",
                        action_type="create_github_issue",
                        title="Legacy oversized evidence",
                        description=None,
                        payload={"repository_full_name": repository_name},
                        evidence_refs=[{**evidence[0], "legacy_blob": "x" * 400}],
                        created_by=ACTION_CREATED_BY_USER,
                        created_by_user_id=owner.id,
                    ),
                ]
            )
            await session.commit()

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert status_code == 200
        assert body["pulse"][0]["value"] == 1
        assert body["pulse"][0]["precision"] == "at_least"
        assert body["snapshot"]["partial"] is True
        decisions_coverage = next(
            item for item in body["snapshot"]["coverage"] if item["key"] == "decisions"
        )
        assert decisions_coverage["status"] == "partial"
        assert decisions_coverage["warning"] == "decision_oversized_json_excluded"
        assert "decision_oversized_json_excluded:2" in body["snapshot"]["warnings"]
        assert not any(
            warning.startswith("decision_window_truncated:")
            for warning in body["snapshot"]["warnings"]
        )
    finally:
        await _cleanup(marker)


@pytest.mark.parametrize(
    ("role", "expected"),
    (
        (
            MEMBERSHIP_ROLE_OWNER,
            {"manage": True, "member": True, "review": True},
        ),
        (
            MEMBERSHIP_ROLE_ADMIN,
            {"manage": True, "member": True, "review": True},
        ),
        (
            MEMBERSHIP_ROLE_MEMBER,
            {"manage": False, "member": True, "review": False},
        ),
        (
            MEMBERSHIP_ROLE_VIEWER,
            {"manage": False, "member": False, "review": False},
        ),
    ),
)
async def test_headquarters_capabilities_follow_in_transaction_role(
    monkeypatch,
    role: str,
    expected: dict[str, bool],
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        actor = (
            owner
            if role == MEMBERSHIP_ROLE_OWNER
            else await _add_member(
                workspace_id=workspace.id,
                marker=marker,
                role=role,
            )
        )

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=actor.email,
        )

        assert status_code == 200
        assert body["workspace"]["role"] == role
        capabilities = body["capabilities"]
        assert capabilities["can_manage_team"] is expected["manage"]
        assert capabilities["can_manage_source"] is expected["manage"]
        assert capabilities["can_import_source"] is expected["manage"]
        assert capabilities["can_start_source_read"] is expected["manage"]
        assert capabilities["can_generate_briefing"] is expected["member"]
        assert capabilities["can_create_proposal"] is expected["member"]
        assert capabilities["can_resolve_world"] is expected["member"]
        assert capabilities["can_review_proposal"] is expected["review"]
        assert capabilities["can_execute_external"] is False
        assert capabilities["can_acknowledge_changes"] is False
        onboarding_steps = {step["key"]: step for step in body["onboarding"]["steps"]}
        assert onboarding_steps["source"]["action"]["enabled"] is expected["manage"]
        assert onboarding_steps["canonical_data"]["action"]["enabled"] is expected["manage"]
        assert onboarding_steps["context"]["action"]["target"] == (
            "/settings" if expected["manage"] else "/company-brain"
        )
        assert onboarding_steps["context"]["action"]["enabled"] is True
    finally:
        await _cleanup(marker)


async def test_truncated_company_world_is_lower_bound_partial_with_window_watermark(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        window_state = {"available": 101}

        async def truncated_company_world(**_kwargs):
            return {
                "window": {
                    "gmail_messages_available": window_state["available"],
                    "gmail_messages_considered": 100,
                    "message_limit": 100,
                    "truncated": True,
                    "order": "newest_first",
                },
                "summary": {
                    "internal_people": 1,
                    "external_contacts_in_window": 0,
                    "organizations_in_window": 0,
                    "touchpoints_in_window": 0,
                    "confirmed_external_people": 0,
                    "confirmed_organizations": 0,
                },
                "people": {
                    "external_candidates": [],
                    "confirmed_external": [],
                },
                "organizations": [],
                "confirmed_organizations": [],
            }

        monkeypatch.setattr(
            headquarters_service,
            "_read_company_world_projection",
            truncated_company_world,
        )
        first_status, first, _first_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        window_state["available"] = 102
        second_status, second, _second_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )

        assert first_status == second_status == 200
        assert first["snapshot"]["partial"] is True
        assert first["pulse"][2]["value"] == 0
        assert first["pulse"][2]["precision"] == "at_least"
        assert "company_world_window_truncated" in first["snapshot"]["warnings"]
        first_coverage = next(
            item for item in first["snapshot"]["coverage"] if item["key"] == "company_world"
        )
        second_coverage = next(
            item for item in second["snapshot"]["coverage"] if item["key"] == "company_world"
        )
        assert first_coverage["status"] == "partial"
        assert first_coverage["warning"] == "company_world_window_truncated"
        assert first_coverage["watermark"].startswith("sha256:")
        assert first_coverage["watermark"] != second_coverage["watermark"]
        context_step = next(
            step for step in first["onboarding"]["steps"] if step["key"] == "context"
        )
        assert context_step["state"] == "unknown"
        map_facts = [
            fact for fact in context_step["evidence"] if fact["key"].startswith("company_map_")
        ]
        assert map_facts
        assert all(
            fact["state"] == "unknown"
            and fact["value"] is None
            and fact["precision"] == "unavailable"
            for fact in map_facts
        )
    finally:
        await _cleanup(marker)


async def test_typed_company_world_unavailability_is_partial_but_unknown_error_fails(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)

        async def typed_unavailable(**_kwargs):
            raise headquarters_service.HeadquartersSubprojectionUnavailable(
                key="company_world",
                code="projection_timeout",
            )

        monkeypatch.setattr(
            headquarters_service,
            "_read_company_world_projection",
            typed_unavailable,
        )
        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert status_code == 200
        assert body["snapshot"]["partial"] is True
        company_world_coverage = next(
            item for item in body["snapshot"]["coverage"] if item["key"] == "company_world"
        )
        assert company_world_coverage["status"] == "unavailable"
        assert body["pulse"][2]["precision"] == "unavailable"
        assert body["pulse"][2]["value"] is None
        onboarding_steps = {step["key"]: step for step in body["onboarding"]["steps"]}
        assert onboarding_steps["context"]["state"] == "unknown"
        assert body["onboarding"]["ready"] is False
        assert body["onboarding"]["current_step_key"] == "canonical_data"

        async def database_timeout(*, session, **_kwargs):
            await session.execute(text("SET LOCAL statement_timeout = '1ms'"))
            await session.execute(text("SELECT pg_sleep(0.05)"))
            raise AssertionError("statement timeout did not cancel the projection")

        monkeypatch.setattr(
            headquarters_service,
            "_read_company_world_projection",
            database_timeout,
        )
        timeout_status, timeout_body, _timeout_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
        )
        assert timeout_status == 200
        timeout_coverage = next(
            item for item in timeout_body["snapshot"]["coverage"] if item["key"] == "company_world"
        )
        assert timeout_coverage["status"] == "unavailable"
        assert timeout_coverage["warning"] == ("company_world_unavailable:statement_timeout")

        async def unknown_error(**_kwargs):
            raise RuntimeError("unknown projection failure")

        monkeypatch.setattr(
            headquarters_service,
            "_read_company_world_projection",
            unknown_error,
        )
        failed_status, _failed_body, _failed_headers = await _get_headquarters(
            workspace_id=workspace.id,
            email=owner.email,
            raise_app_exceptions=False,
        )
        assert failed_status == 500
    finally:
        await _cleanup(marker)


async def test_session_auth_path_does_not_read_secrets_or_call_provider_clients(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    monkeypatch.setattr(settings, "enable_llm", True)
    monkeypatch.setattr(settings, "enable_real_connectors", True)
    monkeypatch.setattr(settings, "enable_write_actions", True)
    monkeypatch.setattr(settings, "openai_api_key", f"openai-secret-{marker}")
    monkeypatch.setattr(
        settings,
        "github_app_private_key",
        SecretStr(f"github-private-key-{marker}"),
    )
    monkeypatch.setattr(
        settings,
        "secret_encryption_key",
        SecretStr(f"encryption-secret-{marker}"),
    )

    def forbidden_client(*_args, **_kwargs):
        raise AssertionError("headquarters must not call provider/secret clients")

    monkeypatch.setattr(secret_encryption, "decrypt_secret", forbidden_client)
    monkeypatch.setattr(
        github_app_token_service,
        "mint_installation_access_token",
        forbidden_client,
    )
    monkeypatch.setattr(
        github_issue_sync_service,
        "sync_selected_repository_issues",
        forbidden_client,
    )
    monkeypatch.setattr(
        github_pr_sync_service,
        "sync_selected_repository_pull_requests",
        forbidden_client,
    )

    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        other_owner, _other_workspace = await _seed_workspace(marker, suffix="-other")
        encrypted_marker = f"encrypted-provider-token-{marker}"
        async with AsyncSessionLocal() as session:
            raw_session_token, _stored_session = await create_session(session, owner.id)
            session.add(
                IntegrationConnection(
                    workspace_id=workspace.id,
                    provider="github",
                    status=INTEGRATION_CONNECTION_STATUS_CONNECTED,
                    display_name="Session GitHub",
                    scopes=["repo:read"],
                    encrypted_access_token=encrypted_marker,
                    encrypted_refresh_token=f"refresh-{encrypted_marker}",
                )
            )
            await session.commit()

        async with _client() as client:
            client.cookies.set(settings.session_cookie_name, raw_session_token)
            response = await client.get(
                f"/api/v1/workspaces/{workspace.id}/headquarters",
                params={"owner_email": other_owner.email},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["workspace"]["id"] == str(workspace.id)
        assert body["workspace"]["role"] == MEMBERSHIP_ROLE_OWNER
        assert body["capabilities"]["can_execute_external"] is True
        assert body["boundary"]["provider_calls"] is False
        assert body["boundary"]["llm"] is False
        assert body["boundary"]["reads_secrets"] is False
        serialized = str(body)
        assert encrypted_marker not in serialized
        assert other_owner.email not in serialized
        assert marker not in str(body["snapshot"]["warnings"])
    finally:
        await _cleanup(marker)


async def test_read_transaction_sets_timeout_and_rejects_accidental_write(
    monkeypatch,
) -> None:
    marker = uuid4().hex
    await _cleanup(marker)
    observed: dict[str, str] = {}
    try:
        owner, workspace = await _seed_workspace(marker)

        async def write_probe(*, session, workspace_id, **_kwargs):
            observed["statement_timeout"] = str(
                await session.scalar(text("SHOW statement_timeout"))
            )
            await session.execute(
                text("UPDATE workspaces SET name = name WHERE id = :workspace_id"),
                {"workspace_id": workspace_id},
            )
            raise AssertionError("READ ONLY transaction unexpectedly allowed a write")

        monkeypatch.setattr(
            headquarters_service,
            "_build_headquarters_snapshot",
            write_probe,
        )
        with pytest.raises(DBAPIError):
            await headquarters_service.read_workspace_headquarters(
                workspace_id=workspace.id,
                user_id=owner.id,
            )

        assert observed["statement_timeout"] in {"5s", "5000ms"}
    finally:
        await _cleanup(marker)


async def test_headquarters_rejects_cross_workspace_access(monkeypatch) -> None:
    marker = uuid4().hex
    _set_auth(monkeypatch)
    await _cleanup(marker)
    try:
        owner, workspace = await _seed_workspace(marker)
        other_owner, _other_workspace = await _seed_workspace(marker, suffix="-other")

        status_code, body, _headers_result = await _get_headquarters(
            workspace_id=workspace.id,
            email=other_owner.email,
        )
        (
            onboarding_status,
            onboarding_body,
            _onboarding_headers,
        ) = await _get_headquarters_onboarding(
            workspace_id=workspace.id,
            email=other_owner.email,
        )
        assert status_code == 404
        assert body == {"detail": "workspace not found"}
        assert onboarding_status == 404
        assert onboarding_body == {"detail": "workspace not found"}
        assert owner.email not in str(body)
    finally:
        await _cleanup(marker)
