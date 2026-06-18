"""Explainable confidence: a score is never shipped without its factors.

Every agent computes confidence through ``build_confidence`` so the UI
can always answer "why 0.82?" with concrete factors instead of a bare
number.
"""

from __future__ import annotations

from typing import Any

# Factor weights; contradiction subtracts.
_WEIGHTS = {
    "evidence_count": 0.30,
    "source_quality": 0.20,
    "freshness": 0.20,
    "cross_source_match": 0.30,
}
_CONTRADICTION_WEIGHT = 0.30
_EVIDENCE_SATURATION = 4
MIN_CONFIDENCE = 0.05
MAX_CONFIDENCE = 0.99


def build_confidence(
    *,
    evidence_count: int = 0,
    source_quality: float = 0.5,
    freshness: float = 0.5,
    cross_source_match: bool = False,
    contradiction_strength: float = 0.0,
) -> tuple[float, dict[str, Any]]:
    """Return (score, factors). Factors are persisted next to the score."""

    evidence_factor = min(max(int(evidence_count), 0), _EVIDENCE_SATURATION) / (
        _EVIDENCE_SATURATION
    )
    quality = min(max(float(source_quality), 0.0), 1.0)
    fresh = min(max(float(freshness), 0.0), 1.0)
    contradiction = min(max(float(contradiction_strength), 0.0), 1.0)

    score = (
        _WEIGHTS["evidence_count"] * evidence_factor
        + _WEIGHTS["source_quality"] * quality
        + _WEIGHTS["freshness"] * fresh
        + _WEIGHTS["cross_source_match"] * (1.0 if cross_source_match else 0.0)
        - _CONTRADICTION_WEIGHT * contradiction
    )
    score = min(max(score, MIN_CONFIDENCE), MAX_CONFIDENCE)

    factors = {
        "evidence_count": int(evidence_count),
        "source_quality": round(quality, 2),
        "freshness": round(fresh, 2),
        "cross_source_match": bool(cross_source_match),
        "contradiction_strength": round(contradiction, 2),
    }
    return round(score, 2), factors


def explain_confidence(score: float, factors: dict[str, Any]) -> str:
    """Human-readable hint for the UI tooltip, in Russian."""

    parts: list[str] = []
    evidence_count = int(factors.get("evidence_count") or 0)
    if evidence_count:
        parts.append(f"evidence-событий: {evidence_count}")
    if factors.get("cross_source_match"):
        parts.append("подтверждено в нескольких источниках")
    else:
        parts.append("найдено только в одном источнике")
    freshness = float(factors.get("freshness") or 0.0)
    if freshness >= 0.7:
        parts.append("данные свежие")
    elif freshness <= 0.3:
        parts.append("данные устарели")
    contradiction = float(factors.get("contradiction_strength") or 0.0)
    if contradiction >= 0.3:
        parts.append("есть противоречащие сигналы")

    level = (
        "High confidence"
        if score >= 0.7
        else "Medium confidence"
        if score >= 0.4
        else "Low confidence"
    )
    return f"{level}: " + ", ".join(parts) + "."
