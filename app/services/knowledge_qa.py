from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.source_models import SourceDocument
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask
from app.services.knowledge_search import search_knowledge

DEFAULT_ASK_LIMIT = 10

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)

_TASK_WORDS = frozenset(
    {
        "task",
        "tasks",
        "todo",
        "promise",
        "promises",
        "promised",
        "commitment",
        "commitments",
        "задача",
        "задачи",
        "обещал",
        "обещали",
        "обещание",
        "обещания",
        "должен",
        "надо",
        "сделать",
    }
)

_RISK_WORDS = frozenset(
    {
        "risk",
        "risks",
        "problem",
        "problems",
        "issue",
        "issues",
        "риск",
        "риски",
        "проблема",
        "проблемы",
        "угроза",
        "угрозы",
    }
)

_DECISION_WORDS = frozenset(
    {
        "decision",
        "decisions",
        "decided",
        "agree",
        "agreed",
        "решение",
        "решения",
        "решили",
        "приняли",
        "принято",
        "приняты",
        "договорились",
    }
)

_GENERIC_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "about",
        "by",
        "client",
        "company",
        "did",
        "for",
        "from",
        "happen",
        "happening",
        "i",
        "in",
        "is",
        "me",
        "my",
        "of",
        "on",
        "or",
        "project",
        "the",
        "to",
        "was",
        "were",
        "what",
        "with",
        "без",
        "был",
        "была",
        "были",
        "было",
        "в",
        "для",
        "и",
        "какие",
        "какой",
        "клиент",
        "клиента",
        "клиенту",
        "клиенты",
        "компания",
        "кто",
        "мой",
        "мои",
        "мы",
        "на",
        "о",
        "об",
        "по",
        "проект",
        "проекта",
        "происходит",
        "произошло",
        "с",
        "сегодня",
        "что",
        "я",
    }
)

_INTENT_WORDS = _TASK_WORDS | _RISK_WORDS | _DECISION_WORDS


def _question_words(question: str) -> list[str]:
    return [word.lower() for word in _WORD_RE.findall(question)]


def _detect_answer_type(question: str) -> str:
    words = set(_question_words(question))

    wants_tasks = bool(words & _TASK_WORDS)
    wants_risks = bool(words & _RISK_WORDS)
    wants_decisions = bool(words & _DECISION_WORDS)

    requested = sum([wants_tasks, wants_risks, wants_decisions])

    if requested != 1:
        return "overview"

    if wants_tasks:
        return "tasks"

    if wants_risks:
        return "risks"

    return "decisions"


def _has_specific_filter(question: str) -> bool:
    for raw_word in _WORD_RE.findall(question):
        word = raw_word.lower()

        if len(word) < 2:
            continue

        if word in _GENERIC_WORDS or word in _INTENT_WORDS:
            continue

        if raw_word.isupper() and len(raw_word) >= 2:
            return True

        if any(char.isdigit() for char in raw_word):
            return True

        if len(word) > 3:
            return True

    return False


def _first_evidence_value(evidence_refs: list[Any] | None, key: str) -> str | None:
    if not evidence_refs:
        return None

    first_ref = evidence_refs[0]
    if not isinstance(first_ref, dict):
        return None

    value = first_ref.get(key)
    if isinstance(value, str) and value:
        return value

    return None


def _document_title(document: SourceDocument | None) -> str | None:
    if document is None:
        return None

    return document.title


def _result_from_extracted(
    *,
    result_type: str,
    item: Any,
    document: SourceDocument | None,
    preview: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    evidence_refs = item.evidence_refs or []

    source_document_id = item.source_document_id or _first_evidence_value(
        evidence_refs,
        "source_document_id",
    )
    chunk_id = item.chunk_id or _first_evidence_value(evidence_refs, "chunk_id")

    return {
        "result_type": result_type,
        "id": item.id,
        "source_document_id": source_document_id,
        "chunk_id": chunk_id,
        "source_title": _document_title(document),
        "title": item.title,
        "preview": preview,
        "confidence": item.confidence,
        "metadata": metadata,
        "evidence_refs": evidence_refs,
    }


def _dedupe_results(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[tuple[str, Any]] = set()
    deduped: list[dict[str, Any]] = []

    for item in items:
        key = (item["result_type"], item["id"])
        if key in seen:
            continue

        seen.add(key)
        deduped.append(item)

        if len(deduped) >= limit:
            break

    return deduped


def _items_by_type(search_results: list[dict[str, Any]], result_type: str) -> list[dict[str, Any]]:
    return [item for item in search_results if item["result_type"] == result_type]


async def _recent_tasks(limit: int) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(ExtractedTask, SourceDocument)
            .outerjoin(
                SourceDocument,
                ExtractedTask.source_document_id == SourceDocument.source_document_id,
            )
            .order_by(ExtractedTask.id.desc())
            .limit(limit)
        )

        return [
            _result_from_extracted(
                result_type="task",
                item=task,
                document=document,
                preview=task.title,
                metadata={
                    "status": task.status,
                    "item_type": task.item_type,
                    "owner": task.owner,
                    "due_date": task.due_date,
                },
            )
            for task, document in rows.all()
        ]


async def _recent_risks(limit: int) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(ExtractedRisk, SourceDocument)
            .outerjoin(
                SourceDocument,
                ExtractedRisk.source_document_id == SourceDocument.source_document_id,
            )
            .order_by(ExtractedRisk.id.desc())
            .limit(limit)
        )

        return [
            _result_from_extracted(
                result_type="risk",
                item=risk,
                document=document,
                preview=risk.title,
                metadata={
                    "severity": risk.severity,
                },
            )
            for risk, document in rows.all()
        ]


async def _recent_decisions(limit: int) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(ExtractedDecision, SourceDocument)
            .outerjoin(
                SourceDocument,
                ExtractedDecision.source_document_id
                == SourceDocument.source_document_id,
            )
            .order_by(ExtractedDecision.id.desc())
            .limit(limit)
        )

        return [
            _result_from_extracted(
                result_type="decision",
                item=decision,
                document=document,
                preview=decision.decision,
                metadata={
                    "decision": decision.decision,
                    "owner": decision.owner,
                },
            )
            for decision, document in rows.all()
        ]


def _attention_score(item: dict[str, Any]) -> float:
    score = item.get("score")

    if not isinstance(score, dict):
        return 0.0

    raw_attention_score = score.get("attention_score")

    try:
        return float(raw_attention_score)
    except (TypeError, ValueError):
        return 0.0


def _prioritize_scored_results(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(items, key=_attention_score, reverse=True)


def _collect_sources(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()

    for group in groups:
        for item in group:
            evidence_refs = item.get("evidence_refs") or []

            for evidence_ref in evidence_refs:
                if not isinstance(evidence_ref, dict):
                    continue

                source_document_id = (
                    evidence_ref.get("source_document_id")
                    or item.get("source_document_id")
                )
                chunk_id = evidence_ref.get("chunk_id") or item.get("chunk_id")
                quote = evidence_ref.get("quote")

                key = (source_document_id, chunk_id, quote)
                if key in seen:
                    continue

                seen.add(key)
                sources.append(
                    {
                        "source_document_id": source_document_id,
                        "chunk_id": chunk_id,
                        "source_title": item.get("source_title"),
                        "quote": quote,
                        "raw_object_ref": evidence_ref.get("raw_object_ref"),
                        "source_url": evidence_ref.get("source_url"),
                    }
                )

    return sources


def _compose_answer(
    *,
    answer_type: str,
    tasks: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> str:
    if not tasks and not risks and not decisions:
        return "No evidence-backed answer found."

    parts: list[str] = []

    if answer_type in {"overview", "tasks"} and tasks:
        parts.append(f"Found {len(tasks)} relevant task(s).")

    if answer_type in {"overview", "risks"} and risks:
        parts.append(f"Found {len(risks)} relevant risk(s).")

    if answer_type in {"overview", "decisions"} and decisions:
        parts.append(f"Found {len(decisions)} relevant decision(s).")

    return " ".join(parts)


async def ask_knowledge(question: str, limit: int = DEFAULT_ASK_LIMIT) -> dict[str, Any]:
    cleaned_question = question.strip()
    answer_type = _detect_answer_type(cleaned_question)
    has_specific_filter = _has_specific_filter(cleaned_question)

    search_result = await search_knowledge(query=cleaned_question, limit=limit)

    raw_results = search_result["results"]
    tasks = _items_by_type(raw_results, "task")
    risks = _items_by_type(raw_results, "risk")
    decisions = _items_by_type(raw_results, "decision")
    supporting_chunks = _items_by_type(raw_results, "chunk")

    if not has_specific_filter:
        if answer_type in {"overview", "tasks"} and not tasks:
            tasks = await _recent_tasks(limit)

        if answer_type in {"overview", "risks"} and not risks:
            risks = await _recent_risks(limit)

        if answer_type in {"overview", "decisions"} and not decisions:
            decisions = await _recent_decisions(limit)

    tasks = _dedupe_results(_prioritize_scored_results(tasks), limit)
    risks = _dedupe_results(_prioritize_scored_results(risks), limit)
    decisions = _dedupe_results(_prioritize_scored_results(decisions), limit)
    supporting_chunks = _dedupe_results(supporting_chunks, limit)

    return {
        "question": cleaned_question,
        "answer_type": answer_type,
        "answer": _compose_answer(
            answer_type=answer_type,
            tasks=tasks,
            risks=risks,
            decisions=decisions,
        ),
        "relevant_tasks": tasks,
        "relevant_risks": risks,
        "relevant_decisions": decisions,
        "supporting_chunks": supporting_chunks,
        "sources": _collect_sources(tasks, risks, decisions, supporting_chunks),
        "search": {
            "terms": search_result["terms"],
            "counts": search_result["counts"],
            "used_recent_fallback": not has_specific_filter,
        },
    }
