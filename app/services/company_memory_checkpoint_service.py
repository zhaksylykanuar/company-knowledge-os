"""Snapshot-bound writes for membership-scoped temporal-memory checkpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.db.base import AsyncSessionLocal
from app.db.memory_models import (
    COMPANY_MEMORY_CHECKPOINT_VERSION,
    CompanyMemoryCheckpoint,
)
from app.services.headquarters_read_service import (
    HEADQUARTERS_CHECKPOINT_FINGERPRINT_LIMIT,
    HEADQUARTERS_STATEMENT_TIMEOUT_MS,
    _build_headquarters_snapshot,
    company_memory_checkpoint_cursor,
)


class CompanyMemoryCheckpointConflictError(RuntimeError):
    """The acknowledged headquarters snapshot is no longer current."""


async def acknowledge_company_memory_checkpoint(
    *,
    workspace_id: UUID,
    user_id: UUID,
    expected_snapshot_id: str,
) -> dict[str, object]:
    """Upsert one exact checkpoint without persisting source or rendered text."""

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            )
            await session.execute(
                text(
                    f"SET LOCAL statement_timeout = "
                    f"'{HEADQUARTERS_STATEMENT_TIMEOUT_MS}ms'"
                )
            )
            as_of = await session.scalar(select(func.transaction_timestamp()))
            if not isinstance(as_of, datetime):
                raise RuntimeError("transaction timestamp is unavailable")

            snapshot = await _build_headquarters_snapshot(
                session=session,
                workspace_id=workspace_id,
                user_id=user_id,
                as_of=as_of,
            )
            if snapshot["snapshot"]["id"] != expected_snapshot_id:
                raise CompanyMemoryCheckpointConflictError(
                    "headquarters snapshot changed"
                )
            fingerprints = snapshot.pop("_checkpoint_fingerprints", None)
            if (
                not isinstance(fingerprints, list)
                or len(fingerprints) > HEADQUARTERS_CHECKPOINT_FINGERPRINT_LIMIT
                or any(not isinstance(value, str) for value in fingerprints)
            ):
                raise RuntimeError("temporal checkpoint material is unavailable")

            statement = (
                insert(CompanyMemoryCheckpoint)
                .values(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    checkpoint_version=COMPANY_MEMORY_CHECKPOINT_VERSION,
                    source_snapshot_id=expected_snapshot_id,
                    observed_through_at=as_of,
                    event_fingerprints=fingerprints,
                    updated_at=as_of,
                )
                .on_conflict_do_update(
                    index_elements=[
                        CompanyMemoryCheckpoint.workspace_id,
                        CompanyMemoryCheckpoint.user_id,
                    ],
                    set_={
                        "checkpoint_version": COMPANY_MEMORY_CHECKPOINT_VERSION,
                        "source_snapshot_id": expected_snapshot_id,
                        "observed_through_at": as_of,
                        "event_fingerprints": fingerprints,
                        "updated_at": as_of,
                    },
                )
                .returning(CompanyMemoryCheckpoint)
            )
            checkpoint = await session.scalar(statement)
            if checkpoint is None:
                raise RuntimeError("temporal checkpoint was not persisted")

            return {
                "contract_version": COMPANY_MEMORY_CHECKPOINT_VERSION,
                "workspace_id": workspace_id,
                "checkpoint": {
                    "cursor": company_memory_checkpoint_cursor(checkpoint),
                    "checkpointed_at": checkpoint.observed_through_at,
                    "source_snapshot_id": checkpoint.source_snapshot_id,
                    "event_fingerprint_count": len(
                        checkpoint.event_fingerprints
                    ),
                    "retention": "membership_scoped",
                },
            }
