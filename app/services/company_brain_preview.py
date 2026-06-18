"""Read-only loader for the local Company Brain preview (Stage 23.2).

This service reads the local Stage 22 preview artifacts under
``.local/company-brain/stage22/`` and assembles founder-facing read models
for the "Мозг компании" (Company Brain) screen and its API.

Hard guarantees, by construction:

* **No DB.** Nothing here touches ``app.db``; the preview is file-based.
* **No network / connectors.** Only local JSON/Markdown files are read.
* **No raw email.** The source nodes carry only ``email_status`` (confirmed /
  unknown), never an address. As a defensive backstop every assembled payload
  passes through an email redaction sweep; if anything email-shaped is ever
  found it is masked and a guardrail warning is raised.
* **Nothing is treated as confirmed.** Jira values stay founder hints (never a
  verified accountId), RACI ownership stays unconfirmed, the proposed graph is
  never a production graph, and the excluded people (Альбина / Камила) appear
  only as exclusion markers — never as active recommendation targets.

Missing files and invalid JSON are handled gracefully: the loader returns an
empty/blocked read model with a human-readable Russian message instead of
raising.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.config import settings

STAGE = "23.2"
STATUS_PREVIEW = "local_preview_only"

# People the founder asked to keep out of the active graph for now. They may
# appear only as an exclusion marker, never as an active recommendation target.
EXCLUDED_PERSON_IDS = ("p-albina", "p-kamila")

# Source files that make up the local preview (Stage 22.1 outputs).
_NODES_FILE = "stage22-proposed-graph-nodes.json"
_EDGES_FILE = "stage22-proposed-graph-edges.json"
_FEED_FILE = "second-opinion-feed-v0.json"
_UNRESOLVED_FILE = "stage22-unresolved-questions.md"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_EMAIL_MASK = "[email скрыт]"

_SEVERITY_RU = {"high": "высокая", "medium": "средняя", "low": "низкая"}


def _stage22_dir(workspace_path: str | Path | None = None) -> Path:
    base = workspace_path if workspace_path is not None else settings.founderos_local_workspace_path
    return Path(base) / "company-brain" / "stage22"


def _read_json(path: Path, errors: dict[str, list[str]]) -> Any | None:
    try:
        if not path.exists():
            errors["missing"].append(path.name)
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors["invalid"].append(path.name)
        return None


def _read_text(path: Path, errors: dict[str, list[str]]) -> str | None:
    try:
        if not path.exists():
            errors["missing"].append(path.name)
            return None
        return path.read_text(encoding="utf-8")
    except OSError:
        errors["invalid"].append(path.name)
        return None


def _redact_emails(obj: Any) -> tuple[Any, bool]:
    """Return ``(clean, found)`` where any email-shaped string is masked.

    This is a backstop: the preview source never stores addresses, but the UI
    and API must never emit one even if a future artifact regresses.
    """

    found = False

    def walk(value: Any) -> Any:
        nonlocal found
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str) and _EMAIL_RE.search(value):
            found = True
            return _EMAIL_RE.sub(_EMAIL_MASK, value)
        return value

    return walk(obj), found


def _guardrails(raw_email_detected: bool) -> dict[str, Any]:
    return {
        "preview_only": True,
        "db_written": False,
        "production_graph": False,
        "jira_hint_is_verified_account_id": False,
        "raci_confirmed": False,
        "no_raw_email": not raw_email_detected,
        "raw_email_detected": raw_email_detected,
        "excluded_for_now": list(EXCLUDED_PERSON_IDS),
        "notes_ru": (
            "Локальный предпросмотр. В БД ничего не записано, внешних записей нет. "
            "Jira — подсказка основателя, не сверенный accountId. RACI не подтверждён. "
            "Предложенный граф — не рабочий граф компании."
        ),
    }


def _nodes_by_type(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        if isinstance(node, dict):
            grouped.setdefault(node.get("type", ""), []).append(node)
    return grouped


def _build_people(
    grouped: dict[str, list[dict[str, Any]]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hints = {
        node.get("person_id"): node
        for node in grouped.get("IdentityHint", [])
        if isinstance(node, dict)
    }
    areas_by_person: dict[str, list[str]] = {}
    for edge in edges:
        if isinstance(edge, dict) and edge.get("type") == "person_related_to_area":
            areas_by_person.setdefault(edge.get("from"), []).append(edge.get("area"))

    people: list[dict[str, Any]] = []
    for node in grouped.get("Person", []):
        pid = node.get("id")
        excluded = bool(node.get("excluded_for_now")) or pid in EXCLUDED_PERSON_IDS
        person: dict[str, Any] = {
            "person_id": pid,
            "name_ru": node.get("name_ru"),
            "role_ru": node.get("role_ru"),
            "excluded_for_now": excluded,
            "identity": None,
            "areas": [],
            "areas_are_ownership": False,
        }
        if node.get("role_confirmed_ru"):
            person["role_confirmed_ru"] = node["role_confirmed_ru"]
        if excluded:
            person["exclusion_note_ru"] = (
                "Пока исключён из предпросмотра по решению основателя. "
                "Не участвует в рекомендациях."
            )
            people.append(person)
            continue
        hint = hints.get(pid, {})
        person["identity"] = {
            "github": list(hint.get("github", []) or []),
            "github_status": hint.get("github_status", "unknown"),
            "jira_hint": hint.get("jira_hint"),
            "jira_identity_status": hint.get(
                "jira_identity_status", "founder_hint_not_connector_verified"
            ),
            "jira_is_verified_account_id": False,
            "email_status": hint.get("email_status", "unknown"),
        }
        person["areas"] = [area for area in areas_by_person.get(pid, []) if area]
        people.append(person)
    return people


def _build_second_opinion(feed_doc: Any) -> list[dict[str, Any]]:
    feed = (feed_doc or {}).get("feed", []) if isinstance(feed_doc, dict) else []
    cards: list[dict[str, Any]] = []
    for item in feed:
        if not isinstance(item, dict):
            continue
        severity = item.get("severity", "medium")
        cards.append(
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "severity": severity,
                "severity_label_ru": _SEVERITY_RU.get(severity, severity),
                "title_ru": item.get("title_ru"),
                "recommended_next_step_ru": item.get("recommended_next_step_ru"),
                "blocked_actions": list(item.get("blocked_actions", []) or []),
                "evidence_refs": list(item.get("evidence_refs", []) or []),
            }
        )
    return cards


def _build_unresolved(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for node in grouped.get("ApprovalGate", []):
        if not isinstance(node, dict):
            continue
        questions.append(
            {
                "question_id": node.get("question_id"),
                "category": node.get("category"),
                "answer_status": node.get("answer_status"),
                "blocks_stage22": bool(node.get("blocks_stage22")),
                "title_ru": node.get("title_ru"),
            }
        )
    return questions


def _build_ownership_gaps(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for node in grouped.get("UnconfirmedOwnershipGap", []):
        if not isinstance(node, dict):
            continue
        gaps.append(
            {
                "area": node.get("area"),
                "description_ru": node.get("description_ru"),
                "confirmed": False,
            }
        )
    return gaps


def _build_overview(
    people: list[dict[str, Any]],
    second_opinion: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    ownership_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    people_count = len(people)
    active = [p for p in people if not p["excluded_for_now"]]
    github_confirmed = sum(
        1 for p in active if (p.get("identity") or {}).get("github_status") == "confirmed"
    )
    email_confirmed = sum(
        1 for p in active if (p.get("identity") or {}).get("email_status") == "confirmed"
    )
    github_unknown = people_count - github_confirmed
    email_unknown = people_count - email_confirmed

    return {
        "headline_ru": "Мозг компании — локальный предпросмотр",
        "preview_badges_ru": [
            "Предпросмотр",
            "В базу не записано",
            "Внешних записей нет",
            "Email скрыт",
        ],
        "hero_metrics": [
            {"key": "people", "label_ru": "Компания", "value_ru": f"{people_count} человек"},
            {
                "key": "github",
                "label_ru": "GitHub identities",
                "value_ru": f"{github_confirmed} подтверждены / {github_unknown} неизвестны",
            },
            {
                "key": "jira_email",
                "label_ru": "Jira / email",
                "value_ru": "подсказки founder’а, не verified accountId",
            },
            {"key": "raci", "label_ru": "RACI", "value_ru": "не подтверждён"},
            {"key": "preview", "label_ru": "Режим", "value_ru": "Предпросмотр включён"},
        ],
        "cards": [
            {
                "key": "people_and_roles",
                "label_ru": "Люди",
                "metric_ru": f"{people_count} человек",
                "tooltip_ru": "Рабочий состав и предложенные роли. Это черновик, не оргструктура.",
            },
            {
                "key": "identity_gaps",
                "label_ru": "Идентификации",
                "metric_ru": f"GitHub {github_confirmed}/{people_count}, email подтверждён {email_confirmed}",
                "tooltip_ru": "Где рабочие аккаунты подтверждены, а где неизвестны. Email — только статус, без адреса.",
            },
            {
                "key": "ownership_gaps",
                "label_ru": "Владельцы",
                "metric_ru": f"{len(ownership_gaps)} пробелов",
                "tooltip_ru": "Области без подтверждённого владельца. RACI остаётся предложением.",
            },
            {
                "key": "second_opinion_feed",
                "label_ru": "Второе мнение",
                "metric_ru": f"{len(second_opinion)} наблюдений",
                "tooltip_ru": "Что не сходится и что требует решения. Это другой взгляд, не приговор.",
            },
            {
                "key": "approval_gates",
                "label_ru": "Требуют подтверждения",
                "metric_ru": f"{sum(1 for q in unresolved if q['blocks_stage22'])} блокирующих",
                "tooltip_ru": "Открытые вопросы основателя, которые блокируют дальнейшую автоматизацию.",
            },
            {
                "key": "unresolved_questions",
                "label_ru": "Нерешённые вопросы",
                "metric_ru": f"{len(unresolved)} вопросов",
                "tooltip_ru": "Что ещё нужно подтвердить, прежде чем считать данные фактом.",
            },
        ],
        "email_confirmed_count": email_confirmed,
        "email_unknown_count": email_unknown,
    }


def _empty_payload(source_status: dict[str, Any]) -> dict[str, Any]:
    guardrails = _guardrails(raw_email_detected=False)
    return {
        "stage": STAGE,
        "status": STATUS_PREVIEW,
        "guardrails": guardrails,
        "source_status": source_status,
        "overview": _build_overview([], [], [], []),
        "people": [],
        "ownership_gaps": [],
        "second_opinion_feed": [],
        "unresolved_questions": [],
    }


def load_company_brain_preview(
    workspace_path: str | Path | None = None,
) -> dict[str, Any]:
    """Assemble the full Company Brain preview read model (read-only)."""

    stage_dir = _stage22_dir(workspace_path)
    errors: dict[str, list[str]] = {"missing": [], "invalid": []}

    nodes_doc = _read_json(stage_dir / _NODES_FILE, errors)
    edges_doc = _read_json(stage_dir / _EDGES_FILE, errors)
    feed_doc = _read_json(stage_dir / _FEED_FILE, errors)
    # Read for availability/empty-state handling; the structured model is built
    # from the graph nodes, which are more robust than parsing Markdown.
    _read_text(stage_dir / _UNRESOLVED_FILE, errors)

    available = bool(nodes_doc) and isinstance(nodes_doc, dict) and bool(nodes_doc.get("nodes"))
    source_status = {
        "available": available,
        "missing_files": errors["missing"],
        "invalid_files": errors["invalid"],
        "directory_ru": "company-brain/stage22 (локально)",
        "message_ru": (
            "Предпросмотр загружен из локальных файлов."
            if available
            else "Локальный предпросмотр недоступен: нет данных или файлы не читаются. "
            "Внешние источники не вызывались."
        ),
    }

    if not available:
        return _empty_payload(source_status)

    nodes = nodes_doc.get("nodes", []) if isinstance(nodes_doc, dict) else []
    edges = edges_doc.get("edges", []) if isinstance(edges_doc, dict) else []
    grouped = _nodes_by_type(nodes)

    people = _build_people(grouped, edges)
    second_opinion = _build_second_opinion(feed_doc)
    unresolved = _build_unresolved(grouped)
    ownership_gaps = _build_ownership_gaps(grouped)
    overview = _build_overview(people, second_opinion, unresolved, ownership_gaps)

    payload = {
        "stage": STAGE,
        "status": STATUS_PREVIEW,
        "source_status": source_status,
        "overview": overview,
        "people": people,
        "ownership_gaps": ownership_gaps,
        "second_opinion_feed": second_opinion,
        "unresolved_questions": unresolved,
    }

    cleaned, raw_email_detected = _redact_emails(payload)
    cleaned["guardrails"] = _guardrails(raw_email_detected=raw_email_detected)
    return cleaned


def load_overview(workspace_path: str | Path | None = None) -> dict[str, Any]:
    preview = load_company_brain_preview(workspace_path)
    return {
        "stage": preview["stage"],
        "status": preview["status"],
        "guardrails": preview["guardrails"],
        "source_status": preview["source_status"],
        "overview": preview["overview"],
    }


def load_people(workspace_path: str | Path | None = None) -> dict[str, Any]:
    preview = load_company_brain_preview(workspace_path)
    return {
        "stage": preview["stage"],
        "status": preview["status"],
        "guardrails": preview["guardrails"],
        "source_status": preview["source_status"],
        "people": preview["people"],
        "ownership_gaps": preview["ownership_gaps"],
    }


def load_second_opinion(workspace_path: str | Path | None = None) -> dict[str, Any]:
    preview = load_company_brain_preview(workspace_path)
    return {
        "stage": preview["stage"],
        "status": preview["status"],
        "guardrails": preview["guardrails"],
        "source_status": preview["source_status"],
        "second_opinion_feed": preview["second_opinion_feed"],
    }


def load_unresolved_questions(workspace_path: str | Path | None = None) -> dict[str, Any]:
    preview = load_company_brain_preview(workspace_path)
    return {
        "stage": preview["stage"],
        "status": preview["status"],
        "guardrails": preview["guardrails"],
        "source_status": preview["source_status"],
        "unresolved_questions": preview["unresolved_questions"],
    }
