from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

import app.services.repository_intelligence.l0 as l0_service
from app.db.base import AsyncSessionLocal
from app.db.canonical_models import Repository, SourceRecord
from app.db.identity_models import User, Workspace
from app.services.repository_intelligence.l0 import (
    REPOSITORY_INTELLIGENCE_L0_ENGINE_VERSION,
    RepositoryIntelligenceL0Error,
    REPOSITORY_INTELLIGENCE_L0_POLICY_HASH,
    build_workspace_repository_intelligence_l0,
)


async def _seed_workspace(marker: str, *, suffix: str = "") -> tuple[UUID, UUID]:
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"ri-l0-{marker}{suffix}@example.test",
            name="RI L0 Synthetic Owner",
        )
        session.add(user)
        await session.flush()
        workspace = Workspace(
            name=f"RI L0 Synthetic {marker}{suffix}",
            slug=f"ri-l0-{marker}{suffix}",
            created_by_user_id=user.id,
        )
        session.add(workspace)
        await session.flush()
        await session.commit()
        return user.id, workspace.id


async def _seed_repository(
    *,
    workspace_id: UUID,
    marker: str,
    name: str,
    external_id: str | None = None,
    repository_type_candidate: str | None = None,
    archived: bool = False,
    default_branch: str | None = "main",
    with_source_record: bool = True,
    source_deleted: bool = False,
    source_full_name: str | None = None,
    source_url: str | None = None,
) -> tuple[UUID, UUID | None]:
    full_name = f"synthetic-company/{name}-{marker}"
    stable_external_id = external_id or f"synthetic-{name}-{marker}"
    observed_at = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        repository = Repository(
            workspace_id=workspace_id,
            provider="github",
            external_id=stable_external_id,
            name=f"{name}-{marker}",
            full_name=full_name,
            default_branch=default_branch,
            visibility="private",
            archived=archived,
            source_url=source_url or f"https://github.example/{full_name}",
            repo_metadata={
                "metadata": {
                    "synthetic": True,
                    "repository_type_candidate": repository_type_candidate,
                }
            },
            last_activity_at=observed_at,
        )
        session.add(repository)
        await session.flush()
        source_record_id: UUID | None = None
        if with_source_record:
            normalized: dict[str, Any] = {
                "external_id": stable_external_id,
                "full_name": source_full_name or full_name,
                "default_branch": default_branch,
                "archived": archived,
                "metadata": {"synthetic": True},
            }
            if repository_type_candidate is not None:
                normalized["metadata"]["repository_type_candidate"] = (
                    repository_type_candidate
                )
            payload = {
                "record_type": "repository",
                "normalized_repository": normalized,
                "evidence_refs": [],
            }
            source_record = SourceRecord(
                workspace_id=workspace_id,
                provider="github",
                external_id=stable_external_id,
                record_type="repository",
                source_url=source_url or f"https://github.example/{full_name}",
                payload=payload,
                payload_hash=sha256(repr(payload).encode("utf-8")).hexdigest(),
                observed_at=observed_at,
                source_updated_at=observed_at,
                is_deleted=source_deleted,
                tombstoned_at=observed_at if source_deleted else None,
                tombstone_observed_at=observed_at if source_deleted else None,
                tombstone_reason=(
                    "synthetic_repository_absence" if source_deleted else None
                ),
            )
            session.add(source_record)
            await session.flush()
            source_record_id = source_record.id
        repository_id = repository.id
        await session.commit()
        return repository_id, source_record_id


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as session:
        workspace_ids = list(
            (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.slug.like(f"ri-l0-{marker}%")
                    )
                )
            ).scalars()
        )
        user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.email.like(f"ri-l0-{marker}%@example.test")
                    )
                )
            ).scalars()
        )
        if workspace_ids:
            await session.execute(
                delete(SourceRecord).where(
                    SourceRecord.workspace_id.in_(workspace_ids)
                )
            )
            await session.execute(
                delete(Repository).where(Repository.workspace_id.in_(workspace_ids))
            )
            await session.execute(
                delete(Workspace).where(Workspace.id.in_(workspace_ids))
            )
        if user_ids:
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.commit()


async def _counts(workspace_id: UUID) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        repository_count = await session.scalar(
            select(func.count())
            .select_from(Repository)
            .where(Repository.workspace_id == workspace_id)
        )
        source_record_count = await session.scalar(
            select(func.count())
            .select_from(SourceRecord)
            .where(SourceRecord.workspace_id == workspace_id)
        )
    return int(repository_count or 0), int(source_record_count or 0)


async def test_l0_projects_three_synthetic_repository_classes() -> None:
    marker = uuid4().hex[:10]
    user_id, workspace_id = await _seed_workspace(marker)
    del user_id
    try:
        expected_types = {
            "frontend_application",
            "backend_service",
            "infrastructure",
        }
        for name, repository_type in (
            ("frontend", "frontend_application"),
            ("backend", "backend_service"),
            ("infrastructure", "infrastructure"),
        ):
            await _seed_repository(
                workspace_id=workspace_id,
                marker=marker,
                name=name,
                repository_type_candidate=repository_type,
            )

        async with AsyncSessionLocal() as session:
            results = await build_workspace_repository_intelligence_l0(
                session,
                workspace_id=workspace_id,
            )

        assert len(results) == 3
        assert {result.result.purpose.repository_type.value for result in results} == (
            expected_types
        )
        for result in results:
            assert result.workspace_id == workspace_id
            assert result.audit_level.value == "L0"
            assert result.analysis_target.target_status.value == "unavailable"
            assert result.analysis_target.commit_sha is None
            assert result.engine_version == REPOSITORY_INTELLIGENCE_L0_ENGINE_VERSION
            assert result.policy_hash == REPOSITORY_INTELLIGENCE_L0_POLICY_HASH
            assert result.result.purpose.status.value == "inferred"
            assert len(result.result.purpose.evidence_refs) == 1
            assert result.result.purpose.evidence_refs[0].source_record_id is not None
            assert "unknown.exact-sha" in {
                unknown.unknown_id for unknown in result.result.unknowns
            }
    finally:
        await _cleanup(marker)


async def test_l0_missing_source_record_returns_unknown_without_guessing() -> None:
    marker = uuid4().hex[:10]
    _user_id, workspace_id = await _seed_workspace(marker)
    try:
        await _seed_repository(
            workspace_id=workspace_id,
            marker=marker,
            name="no-source",
            repository_type_candidate="backend_service",
            with_source_record=False,
        )

        async with AsyncSessionLocal() as session:
            [result] = await build_workspace_repository_intelligence_l0(
                session,
                workspace_id=workspace_id,
            )

        assert result.result.purpose.status.value == "insufficient_evidence"
        assert result.result.purpose.repository_type.value == "unknown"
        assert result.result.purpose.evidence_refs == []
        assert {item.unknown_id for item in result.result.unknowns} >= {
            "unknown.canonical-evidence",
            "unknown.exact-sha",
            "unknown.purpose",
        }
        assert any(
            "No active canonical repository SourceRecord" in limitation
            for limitation in result.result.limitations
        )
    finally:
        await _cleanup(marker)


async def test_l0_never_joins_foreign_workspace_evidence() -> None:
    marker = uuid4().hex[:10]
    _user_a, workspace_a = await _seed_workspace(marker, suffix="-a")
    _user_b, workspace_b = await _seed_workspace(marker, suffix="-b")
    shared_external_id = f"synthetic-shared-{marker}"
    try:
        await _seed_repository(
            workspace_id=workspace_a,
            marker=marker,
            name="workspace-a",
            external_id=shared_external_id,
            with_source_record=False,
        )
        _foreign_repository_id, foreign_source_record_id = await _seed_repository(
            workspace_id=workspace_b,
            marker=marker,
            name="workspace-b",
            external_id=shared_external_id,
            repository_type_candidate="backend_service",
        )

        async with AsyncSessionLocal() as session:
            [result] = await build_workspace_repository_intelligence_l0(
                session,
                workspace_id=workspace_a,
            )

        assert result.workspace_id == workspace_a
        assert result.result.purpose.status.value == "insufficient_evidence"
        serialized = result.model_dump(mode="json")
        assert str(foreign_source_record_id) not in repr(serialized)
    finally:
        await _cleanup(marker)


async def test_l0_ignores_tombstoned_and_identity_mismatched_source_records() -> None:
    marker = uuid4().hex[:10]
    _user_id, workspace_id = await _seed_workspace(marker)
    try:
        await _seed_repository(
            workspace_id=workspace_id,
            marker=marker,
            name="tombstoned",
            repository_type_candidate="backend_service",
            source_deleted=True,
        )
        await _seed_repository(
            workspace_id=workspace_id,
            marker=marker,
            name="mismatch",
            repository_type_candidate="frontend_application",
            source_full_name=f"synthetic-company/other-{marker}",
        )

        async with AsyncSessionLocal() as session:
            results = await build_workspace_repository_intelligence_l0(
                session,
                workspace_id=workspace_id,
            )

        assert len(results) == 2
        for result in results:
            assert result.result.purpose.status.value == "insufficient_evidence"
            assert result.result.purpose.evidence_refs == []
        mismatch = next(
            result
            for result in results
            if result.repository.full_name.endswith(f"mismatch-{marker}")
        )
        assert any(
            "failed exact identity validation" in limitation
            for limitation in mismatch.result.limitations
        )
    finally:
        await _cleanup(marker)


async def test_l0_archived_finding_requires_matching_canonical_evidence() -> None:
    marker = uuid4().hex[:10]
    _user_id, workspace_id = await _seed_workspace(marker)
    try:
        _repository_id, source_record_id = await _seed_repository(
            workspace_id=workspace_id,
            marker=marker,
            name="archived",
            repository_type_candidate="legacy_reference",
            archived=True,
        )

        async with AsyncSessionLocal() as session:
            [result] = await build_workspace_repository_intelligence_l0(
                session,
                workspace_id=workspace_id,
            )

        [finding] = result.result.findings
        assert finding.finding_id == "finding.repository-archived"
        assert finding.status.value == "observed"
        assert finding.lifecycle_status.value == "new"
        assert finding.evidence_refs[0].source_record_id == source_record_id
    finally:
        await _cleanup(marker)


async def test_l0_sanitizes_unsafe_urls_and_keeps_output_schema_valid() -> None:
    marker = uuid4().hex[:10]
    _user_id, workspace_id = await _seed_workspace(marker)
    try:
        await _seed_repository(
            workspace_id=workspace_id,
            marker=marker,
            name="unsafe-url",
            repository_type_candidate="backend_service",
            source_url="https://user:pass@example.test/repo?token=hidden",
        )

        async with AsyncSessionLocal() as session:
            [result] = await build_workspace_repository_intelligence_l0(
                session,
                workspace_id=workspace_id,
            )

        assert result.repository.source_url is None
        assert result.result.purpose.evidence_refs[0].url is None
        assert "hidden" not in repr(result.model_dump(mode="json"))
    finally:
        await _cleanup(marker)


async def test_l0_is_deterministic_read_only_and_empty_without_repositories() -> None:
    marker = uuid4().hex[:10]
    _user_id, workspace_id = await _seed_workspace(marker)
    try:
        async with AsyncSessionLocal() as session:
            assert (
                await build_workspace_repository_intelligence_l0(
                    session,
                    workspace_id=workspace_id,
                )
                == []
            )

        await _seed_repository(
            workspace_id=workspace_id,
            marker=marker,
            name="deterministic",
            repository_type_candidate="documentation",
        )
        before = await _counts(workspace_id)
        async with AsyncSessionLocal() as session:
            first = await build_workspace_repository_intelligence_l0(
                session,
                workspace_id=workspace_id,
            )
            second = await build_workspace_repository_intelligence_l0(
                session,
                workspace_id=workspace_id,
            )
            assert not session.new
            assert not session.dirty
            assert not session.deleted
        after = await _counts(workspace_id)

        assert first == second
        assert before == after == (1, 1)
        assert all(
            "filesystem snapshot" in limitation
            for result in first
            for limitation in result.result.limitations
            if limitation.startswith("No filesystem")
        )
    finally:
        await _cleanup(marker)


async def test_l0_fails_closed_when_repository_count_exceeds_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = uuid4().hex[:10]
    _user_id, workspace_id = await _seed_workspace(marker)
    monkeypatch.setattr(
        l0_service,
        "REPOSITORY_INTELLIGENCE_L0_MAX_REPOSITORIES",
        1,
    )
    try:
        await _seed_repository(
            workspace_id=workspace_id,
            marker=marker,
            name="bounded-a",
            repository_type_candidate="backend_service",
        )
        await _seed_repository(
            workspace_id=workspace_id,
            marker=marker,
            name="bounded-b",
            repository_type_candidate="frontend_application",
        )

        async with AsyncSessionLocal() as session:
            with pytest.raises(RepositoryIntelligenceL0Error):
                await build_workspace_repository_intelligence_l0(
                    session,
                    workspace_id=workspace_id,
                )
    finally:
        await _cleanup(marker)


def test_l0_source_has_no_filesystem_provider_or_legacy_audit_dependency() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "repository_intelligence"
        / "l0.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "from pathlib import Path",
        "repository_source_inventory",
        "repo_audit",
        "founderos_local_workspace_path",
        "httpx",
        "github_repository_client",
        "repository_portfolio_catalog",
    ):
        assert forbidden not in source
