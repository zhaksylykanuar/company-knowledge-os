"""Entity identity layer: source accounts, merge suggestions, canonical ids.

One real person seen as a Jira display name and a GitHub login must not
stay two graph nodes — otherwise team/ownership/stamina views lie. The
layer never merges silently: it files an ``entity_merge_proposal`` and
applies it only after the founder's decision. Cyrillic names are
transliterated for cross-script matching (амир ↔ amir).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import AgentProposal
from app.db.graph_models import (
    EntityAliasRecord,
    EntityLinkRecord,
    EntityRecord,
    EntitySourceAccount,
)
from app.services.agent_proposals import (
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    create_proposal,
    mark_applied,
)
from app.services.confidence import build_confidence
from app.services.knowledge_graph import ENTITY_PERSON

AGENT_NAME = "entity_identity"
KIND_ENTITY_MERGE = "entity_merge_proposal"

MERGE_STATUS_NONE = "none"
MERGE_STATUS_SUGGESTED = "suggested"
MERGE_STATUS_APPROVED = "approved"
MERGE_STATUS_REJECTED = "rejected"

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(value: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in value.casefold())


def name_tokens(entity_id: str) -> set[str]:
    raw = entity_id.split(":", 1)[-1]
    return {tok for tok in raw.split("-") if len(tok) > 2}


def _normalized_token_forms(token: str) -> set[str]:
    forms = {token, transliterate(token)}
    # "kh" vs "h" is the most common transliteration divergence.
    forms |= {form.replace("kh", "h") for form in set(forms)}
    return {form for form in forms if len(form) > 2}


def merge_match(entity_a: str, entity_b: str) -> set[str]:
    """Shared name evidence between two person ids, cross-script aware.

    Matches direct token overlap and transliterated containment
    (``амир-бикчентаев`` vs ``amirbikchentaev``).
    """

    tokens_a = name_tokens(entity_a)
    tokens_b = name_tokens(entity_b)
    shared = {
        form_a
        for tok_a in tokens_a
        for form_a in _normalized_token_forms(tok_a)
        for tok_b in tokens_b
        for form_b in _normalized_token_forms(tok_b)
        if form_a == form_b
    }
    if shared:
        return shared

    compact_a = transliterate("".join(sorted(tokens_a))).replace("kh", "h")
    joined_b = transliterate(entity_b.split(":", 1)[-1].replace("-", "")).replace(
        "kh", "h"
    )
    contained = {
        form
        for tok in tokens_a
        for form in _normalized_token_forms(tok)
        if form in joined_b
    }
    if len(contained) >= 2 or (contained and compact_a and compact_a in joined_b):
        return contained
    return set()


async def register_source_account(
    session: AsyncSession,
    *,
    entity_id: str,
    source_system: str,
    account_id: str,
    account_url: str | None = None,
    confidence: float = 1.0,
) -> bool:
    existing = await session.scalar(
        select(EntitySourceAccount)
        .where(EntitySourceAccount.source_system == source_system)
        .where(EntitySourceAccount.account_id == account_id)
    )
    if existing is not None:
        return False
    session.add(
        EntitySourceAccount(
            entity_id=entity_id,
            source_system=source_system,
            account_id=account_id,
            account_url=account_url,
            confidence=confidence,
        )
    )
    await session.flush()
    return True


async def _people_by_source(session: AsyncSession) -> dict[str, set[str]]:
    rows = (
        await session.execute(
            select(EntitySourceAccount.source_system, EntitySourceAccount.entity_id)
        )
    ).all()
    by_source: dict[str, set[str]] = {}
    for source_system, entity_id in rows:
        by_source.setdefault(str(source_system), set()).add(str(entity_id))
    return by_source


async def suggest_person_merges(session: AsyncSession) -> int:
    """File merge proposals for likely-same people across sources."""

    by_source = await _people_by_source(session)
    sources = sorted(by_source)
    proposals = 0
    for i, source_a in enumerate(sources):
        for source_b in sources[i + 1 :]:
            only_a = by_source[source_a] - by_source[source_b]
            only_b = by_source[source_b] - by_source[source_a]
            for a in sorted(only_a):
                for b in sorted(only_b):
                    if a == b:
                        continue
                    shared = merge_match(a, b)
                    if not shared:
                        continue
                    merged_entity = await session.scalar(
                        select(EntityRecord).where(EntityRecord.entity_id == b)
                    )
                    if (
                        merged_entity is not None
                        and merged_entity.merge_status
                        in {MERGE_STATUS_APPROVED, MERGE_STATUS_REJECTED}
                    ):
                        continue
                    pair = sorted([a, b])
                    score, factors = build_confidence(
                        evidence_count=len(shared),
                        source_quality=0.8,
                        freshness=0.8,
                        cross_source_match=True,
                    )
                    created = await create_proposal(
                        session,
                        proposal_id=f"merge:{pair[0]}+{pair[1]}",
                        dedupe_key=f"merge:{pair[0]}+{pair[1]}",
                        agent=AGENT_NAME,
                        kind=KIND_ENTITY_MERGE,
                        title=f"Это один человек? {a} ({source_a}) и {b} ({source_b})",
                        payload={"keep": a, "merge": b},
                        source_snapshot={
                            "keep": a,
                            "merge": b,
                            "shared_tokens": sorted(shared),
                            "sources": [source_a, source_b],
                        },
                        evidence_refs=[
                            {"kind": "name_overlap", "tokens": sorted(shared)}
                        ],
                        confidence=score,
                        confidence_factors=factors,
                    )
                    if created:
                        proposals += 1
                        if merged_entity is not None:
                            merged_entity.merge_status = MERGE_STATUS_SUGGESTED
                            merged_entity.merge_confidence = score
                            await session.flush()
    return proposals


async def apply_decided_merges(session: AsyncSession) -> dict[str, int]:
    """Apply accepted merges; mark rejected candidates on the entity."""

    counts = {"applied": 0, "rejected": 0, "links_repointed": 0}
    decided = (
        await session.execute(
            select(AgentProposal)
            .where(AgentProposal.kind == KIND_ENTITY_MERGE)
            .where(AgentProposal.status.in_([STATUS_ACCEPTED, STATUS_REJECTED]))
            .where(AgentProposal.applied_at.is_(None))
        )
    ).scalars()

    for proposal in decided:
        keep_id = str(proposal.payload.get("keep") or "")
        merge_id = str(proposal.payload.get("merge") or "")
        merged = await session.scalar(
            select(EntityRecord).where(EntityRecord.entity_id == merge_id)
        )
        if proposal.status == STATUS_REJECTED:
            if merged is not None:
                merged.merge_status = MERGE_STATUS_REJECTED
            proposal.applied_at = datetime.now(timezone.utc)
            counts["rejected"] += 1
            await session.flush()
            continue

        if merged is None or not keep_id:
            proposal.applied_at = datetime.now(timezone.utc)
            await session.flush()
            continue

        merged.canonical_entity_id = keep_id
        merged.merge_status = MERGE_STATUS_APPROVED
        merged.merge_confidence = proposal.confidence

        counts["links_repointed"] += await _repoint_links(
            session, merge_id=merge_id, keep_id=keep_id
        )
        await _copy_aliases(session, merge_id=merge_id, keep_id=keep_id)
        await _repoint_accounts(session, merge_id=merge_id, keep_id=keep_id)

        await mark_applied(session, proposal)
        proposal.applied_at = datetime.now(timezone.utc)
        counts["applied"] += 1
        await session.flush()
    return counts


async def _repoint_links(
    session: AsyncSession, *, merge_id: str, keep_id: str
) -> int:
    from app.services.knowledge_graph import upsert_link

    repointed = 0
    links = (
        await session.execute(
            select(EntityLinkRecord).where(
                (EntityLinkRecord.from_entity_id == merge_id)
                | (EntityLinkRecord.to_entity_id == merge_id)
            )
        )
    ).scalars()
    for link in links:
        new_from = keep_id if link.from_entity_id == merge_id else link.from_entity_id
        new_to = keep_id if link.to_entity_id == merge_id else link.to_entity_id
        if new_from == new_to:
            continue
        created = await upsert_link(
            session,
            from_entity_id=new_from,
            relation=link.relation,
            to_entity_id=new_to,
            evidence_refs=list(link.evidence_refs or []),
            confidence=link.confidence,
        )
        if created:
            repointed += 1
    return repointed


async def _copy_aliases(
    session: AsyncSession, *, merge_id: str, keep_id: str
) -> None:
    from app.services.knowledge_graph import upsert_alias

    aliases = (
        await session.execute(
            select(EntityAliasRecord).where(EntityAliasRecord.entity_id == merge_id)
        )
    ).scalars()
    for alias in aliases:
        await upsert_alias(
            session,
            entity_id=keep_id,
            alias=alias.alias,
            source=f"merge:{alias.source}",
            confidence=alias.confidence,
        )


async def _repoint_accounts(
    session: AsyncSession, *, merge_id: str, keep_id: str
) -> None:
    accounts = (
        await session.execute(
            select(EntitySourceAccount).where(
                EntitySourceAccount.entity_id == merge_id
            )
        )
    ).scalars()
    for account in accounts:
        account.entity_id = keep_id
    await session.flush()


async def resolve_canonical(session: AsyncSession, entity_id: str) -> str:
    """Follow canonical_entity_id chain (with loop safety)."""

    current = entity_id
    for _ in range(5):
        row = await session.scalar(
            select(EntityRecord).where(EntityRecord.entity_id == current)
        )
        if row is None or not row.canonical_entity_id:
            return current
        if row.canonical_entity_id == current:
            return current
        current = row.canonical_entity_id
    return current


_ = ENTITY_PERSON  # identity layer currently targets person entities
