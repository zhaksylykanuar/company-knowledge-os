"""Declared states the founder asserts and agents verify against reality.

Known keys:

- ``focus``: {"title": str, "pct": int, "note": str} — weekly focus;
  the focus_drift generator compares it with actual team activity.
- ``hypotheses``: {"items": [{"text": str, "status":
  "validated|testing|risk"}]} — the hypothesis agent checks declared
  statuses against stored evidence.
- ``company``: {"oneliner": str, "sub": str, "model": [str, ...]} — the
  curated one-line story shown in the investor view.
- ``roadmap``: {"items": [{"horizon": "30|60|90", "text": str}]} — the
  declared 30/60/90 roadmap surfaced (read-only) to investors.
- ``ask``: {"ask": str, "note": str, "milestone": str} — the declared
  fundraise ask / next milestone (free text, never derived numbers).

These last three are *declarations*: they are the founder's stated
intent, surfaced to the investor view marked as declared (not observed)
unless real evidence backs them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.declaration_models import FounderDeclaration

KEY_FOCUS = "focus"
KEY_HYPOTHESES = "hypotheses"
KEY_COMPANY = "company"
KEY_ROADMAP = "roadmap"
KEY_ASK = "ask"
KNOWN_KEYS = frozenset(
    {KEY_FOCUS, KEY_HYPOTHESES, KEY_COMPANY, KEY_ROADMAP, KEY_ASK}
)


async def get_declaration(
    session: AsyncSession, *, key: str
) -> dict[str, Any] | None:
    row = await session.scalar(
        select(FounderDeclaration).where(
            FounderDeclaration.declaration_key == key
        )
    )
    if row is None:
        return None
    return {
        "key": row.declaration_key,
        "payload": row.payload,
        "declared_by": row.declared_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def set_declaration(
    session: AsyncSession,
    *,
    key: str,
    payload: dict[str, Any],
    declared_by: str = "founder",
) -> dict[str, Any]:
    if key not in KNOWN_KEYS:
        raise ValueError(f"unknown declaration key: {key}")
    row = await session.scalar(
        select(FounderDeclaration).where(
            FounderDeclaration.declaration_key == key
        )
    )
    if row is None:
        row = FounderDeclaration(
            declaration_key=key, payload=dict(payload), declared_by=declared_by
        )
        session.add(row)
    else:
        row.payload = dict(payload)
        row.declared_by = declared_by
    await session.flush()
    return {"key": key, "payload": row.payload}
