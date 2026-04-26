from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class ScoreResult:
    importance_score: float
    urgency_score: float
    risk_score: float
    confidence_score: float
    attention_score: float
    reasons: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]


CLIENT_KEYWORDS = (
    "client",
    "customer",
    "proposal",
    "onboarding",
    "contract",
    "stakeholder",
)

SECURITY_KEYWORDS = (
    "security",
    "scada",
    "access",
    "oauth",
    "token",
    "secret",
    "credential",
)

WRITE_ACTION_KEYWORDS = (
    "write action",
    "write actions",
    "write access",
    "control command",
    "change production",
)

URGENT_KEYWORDS = (
    "urgent",
    "asap",
    "today",
    "tomorrow",
    "this week",
    "next week",
    "deadline",
)


def compute_knowledge_score(
    *,
    entity_type: str,
    title: str,
    confidence: float | None,
    evidence_refs: list[dict[str, Any]] | None,
    status: str | None = None,
    due_date: str | None = None,
    severity: str | None = None,
    decision: str | None = None,
    owner: str | None = None,
    today: date | None = None,
) -> ScoreResult:
    scoring_date = today or date.today()
    normalized_type = entity_type.lower().strip()

    reasons: list[dict[str, Any]] = []
    refs = _safe_evidence_refs(evidence_refs)

    importance_score = _base_importance(normalized_type)
    urgency_score = 0.1
    risk_score = _base_risk(normalized_type)
    confidence_score = _clamp(confidence if confidence is not None else 0.0)

    text = _join_text(
        title,
        status,
        due_date,
        severity,
        decision,
        owner,
    )

    if normalized_type == "task":
        importance_score, urgency_score = _score_task(
            importance_score=importance_score,
            urgency_score=urgency_score,
            status=status,
            due_date=due_date,
            scoring_date=scoring_date,
            reasons=reasons,
        )

    if normalized_type == "risk":
        importance_score, urgency_score, risk_score = _score_risk(
            importance_score=importance_score,
            urgency_score=urgency_score,
            risk_score=risk_score,
            severity=severity,
            reasons=reasons,
        )

    if normalized_type == "decision":
        importance_score += 0.1
        reasons.append(
            _reason(
                "decision_record",
                "Decision records are important because they affect future execution.",
                "importance_score",
                0.1,
            )
        )

    if _contains_any(text, CLIENT_KEYWORDS):
        importance_score += 0.15
        reasons.append(
            _reason(
                "client_or_stakeholder_context",
                "Text contains client/stakeholder context.",
                "importance_score",
                0.15,
            )
        )

    if _contains_any(text, SECURITY_KEYWORDS):
        importance_score += 0.15
        risk_score += 0.2
        reasons.append(
            _reason(
                "security_or_access_context",
                "Text contains security/access/SCADA context.",
                "importance_score,risk_score",
                0.2,
            )
        )

    if _contains_any(text, WRITE_ACTION_KEYWORDS):
        importance_score += 0.15
        risk_score += 0.25
        reasons.append(
            _reason(
                "write_action_context",
                "Text mentions write actions or control access.",
                "importance_score,risk_score",
                0.25,
            )
        )

    if _contains_any(text, URGENT_KEYWORDS):
        urgency_score += 0.2
        reasons.append(
            _reason(
                "urgent_language",
                "Text contains urgency/deadline language.",
                "urgency_score",
                0.2,
            )
        )

    if confidence_score < 0.6:
        reasons.append(
            _reason(
                "low_confidence",
                "Extracted entity has low confidence and may need review.",
                "attention_score",
                0.1,
            )
        )

    if not refs:
        confidence_score = min(confidence_score, 0.2)
        reasons.append(
            _reason(
                "missing_evidence_refs",
                "No evidence_refs were attached to this entity.",
                "confidence_score",
                -0.4,
            )
        )

    importance_score = _round_score(importance_score)
    urgency_score = _round_score(urgency_score)
    risk_score = _round_score(risk_score)
    confidence_score = _round_score(confidence_score)

    review_pressure = max(0.0, 0.7 - confidence_score)
    attention_score = _round_score(
        (0.4 * importance_score)
        + (0.3 * urgency_score)
        + (0.25 * risk_score)
        + (0.05 * review_pressure)
    )

    return ScoreResult(
        importance_score=importance_score,
        urgency_score=urgency_score,
        risk_score=risk_score,
        confidence_score=confidence_score,
        attention_score=attention_score,
        reasons=reasons,
        evidence_refs=refs,
    )


def build_score_values(
    *,
    entity_type: str,
    entity: Any,
    today: date | None = None,
) -> dict[str, Any]:
    entity_id = getattr(entity, "id", None)
    if entity_id is None:
        raise ValueError("Cannot score entity without an id")

    score = compute_knowledge_score(
        entity_type=entity_type,
        title=getattr(entity, "title", ""),
        status=getattr(entity, "status", None),
        due_date=getattr(entity, "due_date", None),
        severity=getattr(entity, "severity", None),
        decision=getattr(entity, "decision", None),
        owner=getattr(entity, "owner", None),
        confidence=getattr(entity, "confidence", None),
        evidence_refs=getattr(entity, "evidence_refs", None),
        today=today,
    )

    return {
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "source_document_id": getattr(entity, "source_document_id", None),
        "chunk_id": getattr(entity, "chunk_id", None),
        "importance_score": score.importance_score,
        "urgency_score": score.urgency_score,
        "risk_score": score.risk_score,
        "confidence_score": score.confidence_score,
        "attention_score": score.attention_score,
        "reasons": score.reasons,
        "evidence_refs": score.evidence_refs,
    }


def _score_task(
    *,
    importance_score: float,
    urgency_score: float,
    status: str | None,
    due_date: str | None,
    scoring_date: date,
    reasons: list[dict[str, Any]],
) -> tuple[float, float]:
    normalized_status = (status or "").lower().strip()

    if normalized_status in {"open", "todo", "pending"}:
        importance_score += 0.1
        urgency_score += 0.2
        reasons.append(
            _reason(
                "open_task",
                "Open task needs founder/team follow-up.",
                "importance_score,urgency_score",
                0.2,
            )
        )

    if normalized_status in {"done", "closed", "completed"}:
        urgency_score -= 0.2
        reasons.append(
            _reason(
                "closed_task",
                "Closed task has lower urgency.",
                "urgency_score",
                -0.2,
            )
        )

    due_delta = _days_until_due(due_date, scoring_date)
    if due_delta is not None:
        if due_delta < 0:
            urgency_score += 0.4
            reasons.append(
                _reason(
                    "overdue_due_date",
                    "Task due date is in the past.",
                    "urgency_score",
                    0.4,
                )
            )
        elif due_delta <= 2:
            urgency_score += 0.35
            reasons.append(
                _reason(
                    "due_date_soon",
                    "Task due date is within two days.",
                    "urgency_score",
                    0.35,
                )
            )
        elif due_delta <= 7:
            urgency_score += 0.25
            reasons.append(
                _reason(
                    "due_date_this_week",
                    "Task due date is within seven days.",
                    "urgency_score",
                    0.25,
                )
            )

    return importance_score, urgency_score


def _score_risk(
    *,
    importance_score: float,
    urgency_score: float,
    risk_score: float,
    severity: str | None,
    reasons: list[dict[str, Any]],
) -> tuple[float, float, float]:
    normalized_severity = (severity or "medium").lower().strip()

    if normalized_severity in {"critical", "high"}:
        importance_score += 0.2
        urgency_score += 0.25
        risk_score += 0.35
        reasons.append(
            _reason(
                "high_severity_risk",
                "Risk severity is high or critical.",
                "importance_score,urgency_score,risk_score",
                0.35,
            )
        )
    elif normalized_severity == "medium":
        importance_score += 0.1
        urgency_score += 0.1
        risk_score += 0.2
        reasons.append(
            _reason(
                "medium_severity_risk",
                "Risk severity is medium.",
                "importance_score,urgency_score,risk_score",
                0.2,
            )
        )
    elif normalized_severity == "low":
        risk_score += 0.05
        reasons.append(
            _reason(
                "low_severity_risk",
                "Risk severity is low.",
                "risk_score",
                0.05,
            )
        )

    return importance_score, urgency_score, risk_score


def _days_until_due(raw_due_date: str | None, scoring_date: date) -> int | None:
    if not raw_due_date:
        return None

    value = raw_due_date.strip()
    for date_format in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(value, date_format).date()
            return (parsed - scoring_date).days
        except ValueError:
            continue

    return None


def _base_importance(entity_type: str) -> float:
    return {
        "task": 0.35,
        "risk": 0.55,
        "decision": 0.5,
    }.get(entity_type, 0.3)


def _base_risk(entity_type: str) -> float:
    return {
        "task": 0.1,
        "risk": 0.35,
        "decision": 0.15,
    }.get(entity_type, 0.1)


def _safe_evidence_refs(
    evidence_refs: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not evidence_refs:
        return []

    return [ref for ref in evidence_refs if isinstance(ref, dict)]


def _join_text(*parts: str | None) -> str:
    return " ".join(part for part in parts if part).lower()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _reason(
    code: str,
    message: str,
    score: str,
    weight: float,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "score": score,
        "weight": weight,
    }


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _round_score(value: float) -> float:
    return round(_clamp(value), 3)
