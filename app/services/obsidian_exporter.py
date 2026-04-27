from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from app.db.score_models import KnowledgeScore
from app.db.task_models import ExtractedDecision, ExtractedRisk, ExtractedTask


ENTITY_DIRS = {
    "task": "Tasks",
    "risk": "Risks",
    "decision": "Decisions",
    "source_document": "Sources",
    "document_chunk": "Chunks",
}


@dataclass(frozen=True)
class ObsidianEntity:
    entity_type: str
    entity_id: str
    title: str
    source_document_id: str | None
    chunk_id: str | None
    evidence_refs: list[dict[str, Any]]
    metadata: dict[str, Any]
    score: dict[str, Any] | None = None


def sanitize_obsidian_filename(
    value: str | None,
    *,
    fallback: str = "untitled",
    max_length: int = 120,
) -> str:
    cleaned = re.sub(r'[\\/:*"<>|\n\r\t]+', " ", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")

    if not cleaned:
        cleaned = fallback

    return cleaned[:max_length].strip(" .") or fallback


def obsidian_entity_relative_path(entity: ObsidianEntity) -> Path:
    directory = ENTITY_DIRS.get(entity.entity_type, "Knowledge")
    filename = sanitize_obsidian_filename(
        entity.title,
        fallback=f"{entity.entity_type}-{entity.entity_id}",
    )
    stable_suffix = sanitize_obsidian_filename(
        f"{entity.entity_type}-{entity.entity_id}",
        fallback=f"{entity.entity_type}-unknown",
    )

    return Path(directory) / f"{filename} -- {stable_suffix}.md"


def render_entity_markdown(entity: ObsidianEntity) -> str:
    lines = [
        "---",
        f"entity_type: {_yaml_quote(entity.entity_type)}",
        f"entity_id: {_yaml_quote(entity.entity_id)}",
        f"source_document_id: {_yaml_quote(entity.source_document_id)}",
        f"chunk_id: {_yaml_quote(entity.chunk_id)}",
        "export_note: "
        '"Generated from Postgres source of truth. Obsidian is read-only export."',
        "---",
        "",
        f"# {_clean_markdown_text(entity.title)}",
        "",
    ]

    lines.extend(_metadata_section(entity.metadata))
    lines.extend(_score_section(entity.score))
    lines.extend(_evidence_section(entity.evidence_refs))

    return "\n".join(lines).rstrip() + "\n"


async def collect_obsidian_entities(
    *,
    source_document_id: str | None = None,
) -> list[ObsidianEntity]:
    async with AsyncSessionLocal() as session:
        return await collect_obsidian_entities_for_session(
            session,
            source_document_id=source_document_id,
        )


async def collect_obsidian_entities_for_session(
    session: AsyncSession,
    *,
    source_document_id: str | None = None,
) -> list[ObsidianEntity]:
    tasks = await _load_entities(
        session,
        model=ExtractedTask,
        source_document_id=source_document_id,
    )
    risks = await _load_entities(
        session,
        model=ExtractedRisk,
        source_document_id=source_document_id,
    )
    decisions = await _load_entities(
        session,
        model=ExtractedDecision,
        source_document_id=source_document_id,
    )

    task_scores = await _load_scores(
        session,
        entity_type="task",
        entity_ids=[str(task.id) for task in tasks],
    )
    risk_scores = await _load_scores(
        session,
        entity_type="risk",
        entity_ids=[str(risk.id) for risk in risks],
    )
    decision_scores = await _load_scores(
        session,
        entity_type="decision",
        entity_ids=[str(decision.id) for decision in decisions],
    )

    entities = [
        task_to_obsidian_entity(
            task=task,
            score=task_scores.get(str(task.id)),
        )
        for task in tasks
    ]
    entities.extend(
        risk_to_obsidian_entity(
            risk=risk,
            score=risk_scores.get(str(risk.id)),
        )
        for risk in risks
    )
    entities.extend(
        decision_to_obsidian_entity(
            decision=decision,
            score=decision_scores.get(str(decision.id)),
        )
        for decision in decisions
    )

    return sorted(
        entities,
        key=lambda entity: (
            entity.entity_type,
            entity.title.lower(),
            entity.entity_id,
        ),
    )


async def export_obsidian_vault(
    *,
    vault_path: Path | str,
    source_document_id: str | None = None,
) -> dict[str, Any]:
    entities = await collect_obsidian_entities(
        source_document_id=source_document_id,
    )
    entity_output_paths = write_obsidian_entities(
        vault_path=vault_path,
        entities=entities,
    )
    index_output_paths = write_obsidian_index_files(
        vault_path=vault_path,
        entities=entities,
    )
    output_paths = entity_output_paths + index_output_paths

    base_path = Path(vault_path)

    return {
        "exported": True,
        "vault_path": str(base_path),
        "source_document_id": source_document_id,
        "exported_count": len(output_paths),
        "entity_count": len(entity_output_paths),
        "index_count": len(index_output_paths),
        "files": [
            path.relative_to(base_path).as_posix()
            for path in output_paths
        ],
    }


async def _load_entities(
    session: AsyncSession,
    *,
    model: Any,
    source_document_id: str | None,
) -> list[Any]:
    statement = select(model)

    if source_document_id:
        statement = statement.where(model.source_document_id == source_document_id)

    result = await session.execute(statement)

    return list(result.scalars().all())


async def _load_scores(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_ids: list[str],
) -> dict[str, KnowledgeScore]:
    if not entity_ids:
        return {}

    result = await session.execute(
        select(KnowledgeScore).where(
            KnowledgeScore.entity_type == entity_type,
            KnowledgeScore.entity_id.in_(entity_ids),
        )
    )

    return {
        score.entity_id: score
        for score in result.scalars().all()
    }


def score_to_dict(score: Any | None) -> dict[str, Any] | None:
    if score is None:
        return None

    return {
        "entity_type": getattr(score, "entity_type", None),
        "entity_id": getattr(score, "entity_id", None),
        "importance_score": getattr(score, "importance_score", None),
        "urgency_score": getattr(score, "urgency_score", None),
        "risk_score": getattr(score, "risk_score", None),
        "confidence_score": getattr(score, "confidence_score", None),
        "attention_score": getattr(score, "attention_score", None),
        "reasons": getattr(score, "reasons", None) or [],
        "evidence_refs": getattr(score, "evidence_refs", None) or [],
    }


def task_to_obsidian_entity(
    *,
    task: Any,
    score: Any | None = None,
) -> ObsidianEntity:
    return ObsidianEntity(
        entity_type="task",
        entity_id=_required_entity_id(task),
        title=_entity_title(task, fallback="Untitled task"),
        source_document_id=getattr(task, "source_document_id", None),
        chunk_id=getattr(task, "chunk_id", None),
        evidence_refs=_safe_evidence_refs(getattr(task, "evidence_refs", None)),
        metadata={
            "status": getattr(task, "status", None),
            "item_type": getattr(task, "item_type", None),
            "owner": getattr(task, "owner", None),
            "due_date": getattr(task, "due_date", None),
            "confidence": getattr(task, "confidence", None),
        },
        score=score_to_dict(score),
    )


def risk_to_obsidian_entity(
    *,
    risk: Any,
    score: Any | None = None,
) -> ObsidianEntity:
    return ObsidianEntity(
        entity_type="risk",
        entity_id=_required_entity_id(risk),
        title=_entity_title(risk, fallback="Untitled risk"),
        source_document_id=getattr(risk, "source_document_id", None),
        chunk_id=getattr(risk, "chunk_id", None),
        evidence_refs=_safe_evidence_refs(getattr(risk, "evidence_refs", None)),
        metadata={
            "severity": getattr(risk, "severity", None),
            "confidence": getattr(risk, "confidence", None),
        },
        score=score_to_dict(score),
    )


def decision_to_obsidian_entity(
    *,
    decision: Any,
    score: Any | None = None,
) -> ObsidianEntity:
    return ObsidianEntity(
        entity_type="decision",
        entity_id=_required_entity_id(decision),
        title=_entity_title(decision, fallback="Untitled decision"),
        source_document_id=getattr(decision, "source_document_id", None),
        chunk_id=getattr(decision, "chunk_id", None),
        evidence_refs=_safe_evidence_refs(getattr(decision, "evidence_refs", None)),
        metadata={
            "decision": getattr(decision, "decision", None),
            "owner": getattr(decision, "owner", None),
            "confidence": getattr(decision, "confidence", None),
        },
        score=score_to_dict(score),
    )


def _required_entity_id(entity: Any) -> str:
    raw_id = getattr(entity, "id", None)

    if raw_id is None:
        raise ValueError("Cannot export entity without an id")

    return str(raw_id)


def _entity_title(entity: Any, *, fallback: str) -> str:
    raw_title = getattr(entity, "title", None)

    if not raw_title:
        return fallback

    return str(raw_title)


def _safe_evidence_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


def write_obsidian_entity(
    *,
    vault_path: Path | str,
    entity: ObsidianEntity,
) -> Path:
    base_path = Path(vault_path)
    relative_path = obsidian_entity_relative_path(entity)
    output_path = base_path / relative_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_entity_markdown(entity), encoding="utf-8")

    return output_path


def write_obsidian_entities(
    *,
    vault_path: Path | str,
    entities: list[ObsidianEntity],
) -> list[Path]:
    return [
        write_obsidian_entity(vault_path=vault_path, entity=entity)
        for entity in entities
    ]


def render_vault_index_markdown(entities: list[ObsidianEntity]) -> str:
    counts = {
        "task": 0,
        "risk": 0,
        "decision": 0,
    }

    for entity in entities:
        if entity.entity_type in counts:
            counts[entity.entity_type] += 1

    lines = [
        "# FounderOS Vault Export",
        "",
        "> Generated from Postgres source of truth. Obsidian is read-only export.",
        "",
        "## Sections",
        "",
        f"- [Tasks](Tasks/_Index.md): {counts['task']}",
        f"- [Risks](Risks/_Index.md): {counts['risk']}",
        f"- [Decisions](Decisions/_Index.md): {counts['decision']}",
        "",
    ]

    return "\n".join(lines).rstrip() + "\n"


def render_entity_index_markdown(
    *,
    entity_type: str,
    title: str,
    entities: list[ObsidianEntity],
) -> str:
    matching_entities = [
        entity for entity in entities if entity.entity_type == entity_type
    ]
    matching_entities = sorted(
        matching_entities,
        key=lambda entity: (
            -_entity_attention_score(entity),
            entity.title.lower(),
            entity.entity_id,
        ),
    )

    lines = [
        f"# {title}",
        "",
        "> Generated from Postgres source of truth. Obsidian is read-only export.",
        "",
    ]

    if not matching_entities:
        lines.extend(["No exported items yet.", ""])
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            "| Attention | Title | Source document | Chunk |",
            "| ---: | --- | --- | --- |",
        ]
    )

    for entity in matching_entities:
        lines.append(
            "| "
            f"{_format_value(_entity_attention_score(entity))} | "
            f"{_markdown_link(entity)} | "
            f"{_table_cell(entity.source_document_id)} | "
            f"{_table_cell(entity.chunk_id)} |"
        )

    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_obsidian_index_files(
    *,
    vault_path: Path | str,
    entities: list[ObsidianEntity],
) -> list[Path]:
    if not entities:
        return []

    base_path = Path(vault_path)

    index_files = {
        Path("FounderOS.md"): render_vault_index_markdown(entities),
        Path("Tasks/_Index.md"): render_entity_index_markdown(
            entity_type="task",
            title="Tasks",
            entities=entities,
        ),
        Path("Risks/_Index.md"): render_entity_index_markdown(
            entity_type="risk",
            title="Risks",
            entities=entities,
        ),
        Path("Decisions/_Index.md"): render_entity_index_markdown(
            entity_type="decision",
            title="Decisions",
            entities=entities,
        ),
    }

    output_paths = []
    for relative_path, markdown in index_files.items():
        output_path = base_path / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        output_paths.append(output_path)

    return output_paths


def _entity_attention_score(entity: ObsidianEntity) -> float:
    if not entity.score:
        return 0.0

    raw_score = entity.score.get("attention_score")

    try:
        return float(raw_score)
    except (TypeError, ValueError):
        return 0.0


def _markdown_link(entity: ObsidianEntity) -> str:
    relative_path = obsidian_entity_relative_path(entity).as_posix()
    title = _table_cell(entity.title)

    return f"[{title}](<{relative_path}>)"


def _table_cell(value: str | None) -> str:
    if value is None:
        return ""

    return _clean_markdown_text(str(value)).replace("|", "\\|")


def _metadata_section(metadata: dict[str, Any]) -> list[str]:
    if not metadata:
        return []

    lines = [
        "## Metadata",
        "",
    ]

    for key in sorted(metadata):
        value = metadata[key]
        if value is None:
            continue

        lines.append(f"- **{_clean_markdown_text(str(key))}**: {_format_value(value)}")

    lines.append("")
    return lines


def _score_section(score: dict[str, Any] | None) -> list[str]:
    if not score:
        return [
            "## Score",
            "",
            "No score available.",
            "",
        ]

    lines = [
        "## Score",
        "",
        f"- **attention_score**: {_format_value(score.get('attention_score'))}",
        f"- **importance_score**: {_format_value(score.get('importance_score'))}",
        f"- **urgency_score**: {_format_value(score.get('urgency_score'))}",
        f"- **risk_score**: {_format_value(score.get('risk_score'))}",
        f"- **confidence_score**: {_format_value(score.get('confidence_score'))}",
        "",
    ]

    reasons = score.get("reasons") or []
    if reasons:
        lines.extend(
            [
                "### Score reasons",
                "",
            ]
        )
        for reason in reasons:
            if isinstance(reason, dict):
                code = _format_value(reason.get("code"))
                message = _format_value(reason.get("message"))
                lines.append(f"- **{code}**: {message}")
        lines.append("")

    return lines


def _evidence_section(evidence_refs: list[dict[str, Any]]) -> list[str]:
    return [
        "## Evidence refs",
        "",
        "```json",
        json.dumps(evidence_refs or [], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ]


def _format_value(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return "`" + json.dumps(value, ensure_ascii=False, sort_keys=True) + "`"

    return _clean_markdown_text(str(value))


def _clean_markdown_text(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def _yaml_quote(value: str | None) -> str:
    if value is None:
        return '""'

    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
