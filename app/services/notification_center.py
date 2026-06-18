"""Internal notification / digest center (no external delivery).

A founder-facing read-model that surfaces, in one place, everything that
wants attention: new high-severity findings, decisions waiting, share
packs awaiting approval, stale approved packs, new evidence since the last
update, revoked packs and data-availability problems. It is derived from
live state — each notification reflects the current status of its
underlying item, and its CTA routes to that item's existing safe action
(snooze/resolve a finding, approve/export a pack, …). Nothing is sent
anywhere; this is a review surface, not a delivery channel.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.second_opinion_models import SecondOpinionFinding
from app.db.share_pack_models import SharePack
from app.services.agent_run_log import latest_runs
from app.services.data_availability import get_availability
from app.services.inbox import build_inbox
from app.services.second_opinion import _finding_read_model
from app.services.share_packs import (
    STATUS_REVOKED,
    last_approved_pack,
    packs_awaiting_approval,
    stale_approved_packs,
)

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
RECENT_REVOKED_DAYS = 14
NEW_EVIDENCE_FALLBACK_DAYS = 7


def _notification(
    *,
    notif_id: str,
    notif_type: str,
    severity: str,
    source: str,
    title: str,
    related_entity: str | None,
    cta: str,
    cta_ref: dict[str, Any],
    status: str,
    trail_link: str | None = None,
) -> dict[str, Any]:
    return {
        "id": notif_id,
        "type": notif_type,
        "severity": severity,
        "source": source,
        "title": title,
        "related_entity": related_entity,
        "cta": cta,
        "cta_ref": cta_ref,
        "trail_link": trail_link,
        "status": status,
        # Snooze/resolve route to the underlying item's existing safe action.
        "actions": ["snooze", "resolve"],
    }


async def build_notification_center(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit_per_type: int = 10,
) -> dict[str, Any]:
    safe_now = now or datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []

    # 1. New high-severity findings (open, not snoozed).
    finding_rows = (
        await session.execute(
            select(SecondOpinionFinding)
            .where(SecondOpinionFinding.status == "open")
            .where(SecondOpinionFinding.severity == "high")
            .where(
                (SecondOpinionFinding.snoozed_until.is_(None))
                | (SecondOpinionFinding.snoozed_until <= safe_now)
            )
            .order_by(SecondOpinionFinding.created_at.desc(), SecondOpinionFinding.finding_key)
            .limit(limit_per_type)
        )
    ).scalars()
    for row in finding_rows:
        f = _finding_read_model(row)
        items.append(
            _notification(
                notif_id=f"finding:{f['finding_key']}",
                notif_type="high_severity_finding",
                severity="high",
                source="second_opinion",
                title=f["summary"],
                related_entity=f.get("entity_id"),
                cta="Разобрать конфликт",
                cta_ref={"kind": "finding", "finding_key": f["finding_key"]},
                status=f["status"],
                trail_link=f"/v1/founder/second-opinion/{f['finding_key']}/trail",
            )
        )

    # 2. Decisions waiting (pending inbox proposals).
    inbox = await build_inbox(session, limit=limit_per_type * 2)
    for proposal in inbox.get("proposals", [])[:limit_per_type]:
        items.append(
            _notification(
                notif_id=f"proposal:{proposal['proposal_id']}",
                notif_type="decision_waiting",
                severity="medium",
                source="inbox",
                title=proposal.get("title") or "Решение по предложению",
                related_entity=(proposal.get("payload") or {}).get("entity_id"),
                cta="Принять / отклонить в Inbox",
                cta_ref={"kind": "proposal", "proposal_id": proposal["proposal_id"]},
                status="pending",
            )
        )

    # 3. Share packs awaiting approval.
    for pack in await packs_awaiting_approval(session, limit=limit_per_type):
        items.append(
            _notification(
                notif_id=f"pack_pending:{pack['pack_id']}",
                notif_type="pack_awaiting_approval",
                severity="medium",
                source="share_pack",
                title=f"{pack['title']} ждёт approve ({pack['audience']})",
                related_entity=pack["pack_id"],
                cta="Проверить и approve",
                cta_ref={"kind": "share_pack", "pack_id": pack["pack_id"]},
                status=pack["status"],
            )
        )

    # 4. Stale approved packs (approved long ago, not exported).
    for pack in await stale_approved_packs(session, now=safe_now, limit=limit_per_type):
        items.append(
            _notification(
                notif_id=f"pack_stale:{pack['pack_id']}",
                notif_type="stale_approved_pack",
                severity="medium",
                source="share_pack",
                title=f"{pack['title']} approved, но не экспортирован",
                related_entity=pack["pack_id"],
                cta="Экспортировать или revoke",
                cta_ref={"kind": "share_pack", "pack_id": pack["pack_id"]},
                status=pack["status"],
            )
        )

    # 5. Revoked / expired packs (recent).
    revoked_cutoff = safe_now - timedelta(days=RECENT_REVOKED_DAYS)
    revoked_rows = (
        await session.execute(
            select(SharePack)
            .where(SharePack.status == STATUS_REVOKED)
            .where(SharePack.revoked_at >= revoked_cutoff)
            .order_by(SharePack.revoked_at.desc())
            .limit(limit_per_type)
        )
    ).scalars()
    for row in revoked_rows:
        items.append(
            _notification(
                notif_id=f"pack_revoked:{row.pack_id}",
                notif_type="revoked_pack",
                severity="low",
                source="share_pack",
                title=f"{row.title} отозван",
                related_entity=row.pack_id,
                cta="Открыть pack",
                cta_ref={"kind": "share_pack", "pack_id": row.pack_id},
                status=row.status,
            )
        )

    # 6. New evidence since the last update.
    last_update = await last_approved_pack(session, audience="investor")
    since = safe_now - timedelta(days=NEW_EVIDENCE_FALLBACK_DAYS)
    if last_update and last_update.get("approved_at"):
        try:
            since = datetime.fromisoformat(last_update["approved_at"])
        except ValueError:
            pass
    runs = await latest_runs(session, limit=40)
    new_evidence = sum(
        int(r.get("created") or 0) + int(r.get("updated_from_new_evidence") or 0)
        for r in runs
        if (r.get("run_finished_at") or "") >= since.isoformat()
    )
    if new_evidence:
        items.append(
            _notification(
                notif_id="new_evidence",
                notif_type="new_evidence",
                severity="low",
                source="agent_run",
                title=f"Новых сигналов из источников: {new_evidence}",
                related_entity=None,
                cta="Обновить апдейт",
                cta_ref={"kind": "evidence"},
                status="info",
            )
        )

    # 7. Data-availability problems.
    availability = await get_availability(session)
    for row in [a for a in availability if a["status"] in {"stale", "no_data"}][
        :limit_per_type
    ]:
        items.append(
            _notification(
                notif_id=f"data:{row['metric_key']}:{row['scope']}",
                notif_type="data_availability",
                severity="low",
                source="data_availability",
                title=f"Данные: {row['metric_key']} ({row['scope']}) — {row['status']}",
                related_entity=row["scope"],
                cta="Прогнать агентов / синк",
                cta_ref={"kind": "metric", "metric_key": row["metric_key"]},
                status=row["status"],
            )
        )

    items.sort(key=lambda n: _SEVERITY_RANK.get(n["severity"], 3))

    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for n in items:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
        by_severity[n["severity"]] = by_severity.get(n["severity"], 0) + 1

    return {
        "generated_at": safe_now.isoformat(),
        "notifications": items,
        "counts": {
            "total": len(items),
            "by_type": by_type,
            "by_severity": by_severity,
        },
    }
