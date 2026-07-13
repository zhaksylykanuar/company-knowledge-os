"""Computed read-only repository audit for Company Brain.

The audit reads a previously saved GitHub discovery snapshot from
``.local/discovery/github/*/raw/repos.json`` and computes founder-facing repo
facts. It does not call the network, does not require credentials, and does not
write to DB or external systems.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.repository_portfolio import repository_portfolio_catalog

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_EMAIL_MASK = "[email скрыт]"

_MANIFEST_HINTS = {
    "package.json": "node",
    "pnpm-lock.yaml": "node",
    "yarn.lock": "node",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "poetry.lock": "python",
    "go.mod": "go",
    "cargo.toml": "rust",
    "pom.xml": "java",
    "build.gradle": "java",
    "gemfile": "ruby",
    "composer.json": "php",
    "dockerfile": "container",
    "docker-compose.yml": "container",
    "docker-compose.yaml": "container",
}
_DEPLOY_HINTS = {
    "dockerfile": "dockerfile",
    "docker-compose.yml": "docker_compose",
    "docker-compose.yaml": "docker_compose",
    "vercel.json": "vercel",
    "netlify.toml": "netlify",
    "render.yaml": "render",
    "fly.toml": "fly",
    "procfile": "procfile",
    ".github": "github_workflows_hint",
    "helm": "helm",
    "k8s": "kubernetes",
    "kubernetes": "kubernetes",
}
_CI_HINTS = {".github", ".gitlab-ci.yml", ".circleci", "azure-pipelines.yml"}
_TEST_HINTS = {
    "tests",
    "test",
    "__tests__",
    "pytest.ini",
    "tox.ini",
    "jest.config.js",
    "jest.config.ts",
    "vitest.config.js",
    "vitest.config.ts",
}
_SENSITIVE_FILENAME_MARKERS = ("secret", "token", "credential")
_AREA_CODES = ("CORE", "PLAT", "OPS", "CORP", "RND")
_FUTURE_LATER_AREA_CODES = ("GTM", "SALES")
_FUTURE_LATER_AREA_STATUS = "future_later_not_active"
_JIRA_REPO_MAPPING_POLICY = "repo_is_component_or_evidence_not_jira_project"
_STALE_SNAPSHOT_SECONDS = 72 * 60 * 60


def load_repo_audit(
    *,
    workspace_path: str | Path | None = None,
    raw_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a computed repo audit payload for Company Brain."""

    safe_now = now or datetime.now(timezone.utc)
    workspace = Path(workspace_path or settings.founderos_local_workspace_path)
    selected_raw_path = Path(raw_path) if raw_path is not None else _latest_raw_repos_path(workspace)
    generated_at = safe_now.isoformat()

    if selected_raw_path is None or not selected_raw_path.exists():
        return _finalize(
            {
                "status": "raw_discovery_missing",
                "provenance": _provenance(computed=False),
                "preview_only": True,
                "computed": False,
                "db_written": False,
                "network_calls": False,
                "generated_at": generated_at,
                "source_snapshot": _empty_source_snapshot(
                    "Локальный снимок GitHub discovery не найден. Внешние источники не вызывались."
                ),
                "repo_count": 0,
                "catalog_count": _catalog_count(),
                "reconciliation": _reconcile([], _catalog_names()),
                "repo_facts": [],
                "summary_cards": _summary_cards([], _reconcile([], _catalog_names())),
                "risk_summary": {},
                "area_candidate_counts": {},
                "guardrails": _guardrails(),
            }
        )

    try:
        raw = json.loads(selected_raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _missing_or_invalid_payload(
            status="raw_discovery_invalid",
            path=selected_raw_path,
            workspace=workspace,
            generated_at=generated_at,
        )

    if not isinstance(raw, list):
        return _missing_or_invalid_payload(
            status="raw_discovery_invalid",
            path=selected_raw_path,
            workspace=workspace,
            generated_at=generated_at,
        )

    repo_facts = [
        _repo_fact(repo, now=safe_now, source_snapshot=_safe_relative(selected_raw_path, workspace))
        for repo in raw
        if isinstance(repo, Mapping)
    ]
    catalog_names = _catalog_names()
    reconciliation = _reconcile([fact["name"] for fact in repo_facts], catalog_names)
    risk_summary = _risk_summary(repo_facts)
    area_counts = dict(sorted(Counter(fact["area_candidate"] for fact in repo_facts).items()))

    source_snapshot = _source_snapshot_meta(
        path=selected_raw_path,
        workspace=workspace,
        now=safe_now,
        status="available",
    )
    source_snapshot.update(
        {
            "repo_count": len(repo_facts),
            "message_ru": "Вычислено из локального снимка GitHub discovery. Сеть не вызывалась.",
        }
    )

    return _finalize(
        {
            "status": "computed",
            "provenance": _provenance(computed=True),
            "preview_only": True,
            "computed": True,
            "db_written": False,
            "network_calls": False,
            "generated_at": generated_at,
            "source_snapshot": source_snapshot,
            "repo_count": len(repo_facts),
            "catalog_count": len(catalog_names),
            "reconciliation": reconciliation,
            "repo_facts": repo_facts,
            "summary_cards": _summary_cards(repo_facts, reconciliation),
            "risk_summary": risk_summary,
            "area_candidate_counts": area_counts,
            "guardrails": _guardrails(),
        }
    )


def _latest_raw_repos_path(workspace: Path) -> Path | None:
    candidates = sorted((workspace / "discovery" / "github").glob("*/raw/repos.json"))
    if candidates:
        return candidates[-1]
    root_repos = workspace / "repos.json"
    return root_repos if root_repos.exists() else None


def _source_snapshot_meta(
    *,
    path: Path,
    workspace: Path,
    now: datetime,
    status: str,
) -> dict[str, Any]:
    modified_at: datetime | None = None
    try:
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        pass

    age_seconds = (
        max(0, int((now - modified_at).total_seconds())) if modified_at is not None else None
    )
    relative = _safe_relative(path, workspace)
    snapshot_id = _snapshot_id_from_path(path=path, workspace=workspace)
    freshness_status = _snapshot_freshness(age_seconds)
    return {
        "available": status == "available",
        "status": status,
        "path": relative,
        "snapshot_id": snapshot_id,
        "snapshot_key": snapshot_id or relative,
        "modified_at": modified_at.isoformat() if modified_at else None,
        "snapshot_age_seconds": age_seconds,
        "as_of_source": "local_file_mtime" if modified_at else "missing",
        "freshness_status": freshness_status,
        "freshness_label_ru": _snapshot_freshness_label(freshness_status),
        "repo_count": 0,
    }


def _snapshot_id_from_path(*, path: Path, workspace: Path) -> str | None:
    try:
        if path.parent == workspace and path.name == "repos.json":
            return "local-root-repos"
        if path.name == "repos.json" and path.parent.name == "raw":
            return path.parents[1].name
    except IndexError:
        return None
    return None


def _empty_source_snapshot(message_ru: str) -> dict[str, Any]:
    return {
        "available": False,
        "status": "missing",
        "path": None,
        "snapshot_id": None,
        "snapshot_key": None,
        "modified_at": None,
        "snapshot_age_seconds": None,
        "as_of_source": "missing",
        "freshness_status": "unknown",
        "freshness_label_ru": "Свежесть локального снимка неизвестна",
        "repo_count": 0,
        "message_ru": message_ru,
    }


def _snapshot_freshness(age_seconds: int | None) -> str:
    if age_seconds is None:
        return "unknown"
    if age_seconds > _STALE_SNAPSHOT_SECONDS:
        return "stale"
    return "fresh"


def _snapshot_freshness_label(freshness_status: str) -> str:
    if freshness_status == "fresh":
        return "Локальный снимок discovery свежий"
    if freshness_status == "stale":
        return "Локальный снимок discovery устарел"
    return "Свежесть локального снимка неизвестна"


def _repo_fact(
    repo: Mapping[str, Any],
    *,
    now: datetime,
    source_snapshot: str | None,
) -> dict[str, Any]:
    name = _safe_text(repo.get("name")) or "unknown"
    full_name = _safe_text(repo.get("full_name")) or name
    org = _safe_text((repo.get("owner") or {}).get("login") if isinstance(repo.get("owner"), Mapping) else None)
    languages = _language_breakdown(repo.get("_languages"))
    root_files = _root_files(repo.get("_root_contents"))
    manifests = _detected_manifests(root_files)
    pushed_at = _safe_text(repo.get("pushed_at"))
    updated_at = _safe_text(repo.get("updated_at"))
    days_since_last_push = _days_since(pushed_at, now=now)
    activity_bucket = _activity_bucket(days_since_last_push)
    primary_language = _safe_text(repo.get("language")) or _primary_language(languages)
    stack_candidate = _stack_candidate(name=name, primary_language=primary_language, manifests=manifests)
    ci_detected = _ci_detected(root_files)
    tests_detected = _tests_detected(root_files)
    deploy_hints = _deploy_hints(root_files)
    owner_candidates = _owner_candidates(repo.get("_recent_commits"))
    area_candidate, area_confidence = _area_candidate(
        name=name,
        full_name=full_name,
        primary_language=primary_language,
        manifests=manifests,
        root_files=root_files,
        topics=repo.get("topics"),
        stack_candidate=stack_candidate,
    )
    risks = _risks(
        description_present=bool(_safe_text(repo.get("description"))),
        readme_present=bool(_safe_text(repo.get("_readme"))),
        ci_detected=ci_detected,
        tests_detected=tests_detected,
        archived=bool(repo.get("archived")),
        fork=bool(repo.get("fork")),
        activity_bucket=activity_bucket,
        owner_candidates=owner_candidates,
    )
    unknowns = _unknowns(
        days_since_last_push=days_since_last_push,
        owner_candidates=owner_candidates,
        area_confidence=area_confidence,
        branch_count=_count_list(repo.get("_branches")),
    )

    return {
        "repo_role": "component_evidence",
        "repo_not_jira_project": True,
        "name": name,
        "full_name": full_name,
        "org": org,
        "description_status": "present" if _safe_text(repo.get("description")) else "missing",
        "archived": bool(repo.get("archived")),
        "fork": bool(repo.get("fork")),
        "private": bool(repo.get("private")),
        "visibility": _visibility(repo),
        "default_branch": _safe_text(repo.get("default_branch")),
        "pushed_at": pushed_at,
        "updated_at": updated_at,
        "days_since_last_push": days_since_last_push,
        "activity_bucket": activity_bucket,
        "languages_breakdown": languages,
        "primary_language": primary_language,
        "root_files": root_files[:40],
        "detected_manifests": manifests,
        "stack_candidate": stack_candidate,
        "ci_detected": ci_detected,
        "tests_detected": tests_detected,
        "deploy_hints": deploy_hints,
        "license_status": "present" if repo.get("license") else "missing",
        "readme_status": "present" if _safe_text(repo.get("_readme")) else "missing",
        "branch_count": _count_list(repo.get("_branches")),
        "owner_candidates": owner_candidates,
        "owner_candidate_status": "candidate_needs_founder_confirm"
        if owner_candidates
        else "unknown",
        "jira_component_candidate": name,
        "jira_mapping_policy": _JIRA_REPO_MAPPING_POLICY,
        "area_candidate": area_candidate,
        "area_confidence": area_confidence,
        "needs_founder_confirm": True,
        "risks": risks,
        "unknowns": unknowns,
        "evidence_refs": _evidence_refs(name=name, source_snapshot=source_snapshot),
    }


def _missing_or_invalid_payload(
    *,
    status: str,
    path: Path,
    workspace: Path,
    generated_at: str,
) -> dict[str, Any]:
    catalog_names = _catalog_names()
    reconciliation = _reconcile([], catalog_names)
    return _finalize(
        {
            "status": status,
            "provenance": _provenance(computed=False),
            "preview_only": True,
            "computed": False,
            "db_written": False,
            "network_calls": False,
            "generated_at": generated_at,
            "source_snapshot": {
                **_source_snapshot_meta(
                    path=path,
                    workspace=workspace,
                    now=_parse_datetime(generated_at) or datetime.now(timezone.utc),
                    status=status,
                ),
                "message_ru": "Локальный снимок GitHub discovery не читается. Внешние источники не вызывались.",
            },
            "repo_count": 0,
            "catalog_count": len(catalog_names),
            "reconciliation": reconciliation,
            "repo_facts": [],
            "summary_cards": _summary_cards([], reconciliation),
            "risk_summary": {},
            "area_candidate_counts": {},
            "guardrails": _guardrails(),
        }
    )


def _catalog_names() -> list[str]:
    try:
        return sorted(
            str(entry["repo_key"])
            for entry in repository_portfolio_catalog()
            if isinstance(entry, Mapping) and entry.get("repo_key")
        )
    except Exception:
        return []


def _catalog_count() -> int:
    return len(_catalog_names())


def _reconcile(live_names: Sequence[str], catalog_names: Sequence[str]) -> dict[str, Any]:
    live_by_key = {_match_key(name): name for name in live_names if name}
    catalog_by_key = {_match_key(name): name for name in catalog_names if name}
    live_keys = set(live_by_key)
    catalog_keys = set(catalog_by_key)
    matched_keys = live_keys & catalog_keys
    return {
        "status": "computed" if catalog_names else "catalog_unavailable",
        "live_count": len(live_names),
        "catalog_count": len(catalog_names),
        "matched_count": len(matched_keys),
        "live_repos": [live_by_key[key] for key in sorted(live_keys)],
        "catalog_repos": [catalog_by_key[key] for key in sorted(catalog_keys)],
        "in_live_not_in_catalog": [live_by_key[key] for key in sorted(live_keys - catalog_keys)],
        "in_catalog_not_in_live": [
            catalog_by_key[key] for key in sorted(catalog_keys - live_keys)
        ],
        "matched": [live_by_key[key] for key in sorted(matched_keys)],
        "repo_mapping_policy": "repo_is_component_or_evidence_not_jira_project",
    }


def _summary_cards(repo_facts: Sequence[Mapping[str, Any]], reconciliation: Mapping[str, Any]) -> list[dict[str, Any]]:
    risks = _risk_summary(repo_facts)
    area_counts = Counter(str(fact.get("area_candidate") or "unknown") for fact in repo_facts)
    owner_candidate_count = sum(1 for fact in repo_facts if fact.get("owner_candidates"))
    return [
        {
            "key": "computed_repo_count",
            "label_ru": "Репозитории",
            "value": len(repo_facts),
            "detail_ru": "Вычисленные факты из локального снимка GitHub discovery.",
        },
        {
            "key": "catalog_reconciliation",
            "label_ru": "Сверка каталога",
            "value": {
                "live": reconciliation.get("live_count", 0),
                "catalog": reconciliation.get("catalog_count", 0),
                "matched": reconciliation.get("matched_count", 0),
            },
            "detail_ru": "Локальный discovery сверяется со статичным каталогом.",
        },
        {
            "key": "top_risks",
            "label_ru": "Риски",
            "value": dict(sorted(risks.items())),
            "detail_ru": "Классы риска, без внешних записей и без raw payload.",
        },
        {
            "key": "area_candidates",
            "label_ru": "Кандидаты областей",
            "value": dict(sorted(area_counts.items())),
            "detail_ru": "CORE / PLAT / OPS / CORP / RND — кандидаты, требуют подтверждения.",
        },
        {
            "key": "owner_candidates",
            "label_ru": "Кандидаты владельцев",
            "value": owner_candidate_count,
            "detail_ru": "Кандидаты из commit author login, без email-адресов.",
        },
    ]


def _language_breakdown(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Mapping):
        return []
    numeric = {str(k): int(v) for k, v in value.items() if isinstance(v, int | float)}
    total = sum(numeric.values())
    out: list[dict[str, Any]] = []
    for name, bytes_count in sorted(numeric.items(), key=lambda item: item[1], reverse=True):
        out.append(
            {
                "language": _safe_text(name),
                "bytes": bytes_count,
                "percent": round((bytes_count / total) * 100, 1) if total else 0.0,
            }
        )
    return out[:12]


def _root_files(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        name = _safe_root_name(item.get("name"))
        if name:
            names.append(name)
    return sorted(dict.fromkeys(names), key=str.casefold)


def _safe_root_name(value: Any) -> str | None:
    name = _safe_text(value, limit=120)
    if not name:
        return None
    lowered = name.casefold()
    if lowered == ".env" or any(marker in lowered for marker in _SENSITIVE_FILENAME_MARKERS):
        return None
    return name


def _detected_manifests(root_files: Sequence[str]) -> list[str]:
    lowered = {name.casefold(): name for name in root_files}
    return [lowered[key] for key in sorted(_MANIFEST_HINTS) if key in lowered]


def _deploy_hints(root_files: Sequence[str]) -> list[str]:
    lowered = {name.casefold() for name in root_files}
    return sorted({hint for key, hint in _DEPLOY_HINTS.items() if key in lowered})


def _ci_detected(root_files: Sequence[str]) -> bool:
    lowered = {name.casefold() for name in root_files}
    return bool(lowered & _CI_HINTS)


def _tests_detected(root_files: Sequence[str]) -> bool:
    lowered = {name.casefold() for name in root_files}
    return bool(lowered & _TEST_HINTS)


def _primary_language(languages: Sequence[Mapping[str, Any]]) -> str | None:
    if not languages:
        return None
    language = languages[0].get("language")
    return str(language) if language else None


def _stack_candidate(
    *,
    name: str,
    primary_language: str | None,
    manifests: Sequence[str],
) -> str:
    lowered_name = name.casefold()
    lowered_manifests = {item.casefold() for item in manifests}
    lang = (primary_language or "").casefold()
    if "dockerfile" in lowered_manifests and len(lowered_manifests) == 1:
        return "container_only"
    if "package.json" in lowered_manifests and any(
        token in lowered_name for token in ("front", "web", "landing", "viewer", "ui")
    ):
        return "frontend_web"
    if "package.json" in lowered_manifests:
        return "node_app"
    if {"pyproject.toml", "requirements.txt", "setup.py"} & lowered_manifests:
        if any(token in lowered_name for token in ("collector", "work" + "er", "puller")):
            return "python_background_service_or_collector"
        return "python_service"
    if "go.mod" in lowered_manifests:
        return "go_service"
    if "dockerfile" in lowered_manifests:
        return "containerized_service"
    if lang:
        return f"{lang}_repo"
    return "unknown"


def _owner_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    counts: Counter[str] = Counter()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        login = None
        author = item.get("author")
        if isinstance(author, Mapping):
            raw_login = author.get("login")
            if isinstance(raw_login, str) and not _EMAIL_RE.search(raw_login):
                login = _safe_text(raw_login)
        if not login:
            committer = item.get("committer")
            if isinstance(committer, Mapping):
                raw_login = committer.get("login")
                if isinstance(raw_login, str) and not _EMAIL_RE.search(raw_login):
                    login = _safe_text(raw_login)
        if login:
            counts[login] += 1
    return [
        {
            "candidate": login,
            "source": "recent_commit_author_login",
            "commit_count": count,
            "needs_founder_confirm": True,
        }
        for login, count in counts.most_common(3)
    ]


def _area_candidate(
    *,
    name: str,
    full_name: str,
    primary_language: str | None,
    manifests: Sequence[str],
    root_files: Sequence[str],
    topics: Any,
    stack_candidate: str,
) -> tuple[str, float]:
    topic_text = " ".join(t for t in topics if isinstance(t, str)) if isinstance(topics, list) else ""
    text = " ".join(
        [
            name,
            full_name,
            primary_language or "",
            stack_candidate,
            " ".join(manifests),
            " ".join(root_files),
            topic_text,
        ]
    ).casefold()
    if any(token in text for token in ("landing", "corp", "site", "marketing", "brand")):
        return "CORP", 0.72
    if any(token in text for token in ("splat", "potree", "ml", "ai", "rnd", "research", "ar", "mr")):
        return "RND", 0.7
    if any(token in text for token in ("collector", "monitor", "scada", "frigate", "infra", "ops")):
        return "OPS", 0.74
    if any(token in text for token in ("api", "backend", "work" + "er", "platform", "base")):
        return "PLAT", 0.66
    if any(token in text for token in ("ssap", "qaztwin", "front", "chat", "viewer")):
        return "CORE", 0.62
    return "CORE", 0.35


def _risks(
    *,
    description_present: bool,
    readme_present: bool,
    ci_detected: bool,
    tests_detected: bool,
    archived: bool,
    fork: bool,
    activity_bucket: str,
    owner_candidates: Sequence[Mapping[str, Any]],
) -> list[str]:
    risks: list[str] = []
    if not description_present:
        risks.append("description_missing")
    if not readme_present:
        risks.append("readme_missing")
    if not ci_detected:
        risks.append("ci_not_detected")
    if not tests_detected:
        risks.append("tests_not_detected")
    if archived:
        risks.append("archived_repository")
    if fork:
        risks.append("fork_repository")
    if activity_bucket == "stale":
        risks.append("stale_repository")
    if activity_bucket == "dormant":
        risks.append("dormant_repository")
    if not owner_candidates:
        risks.append("owner_candidate_unknown")
    return risks


def _unknowns(
    *,
    days_since_last_push: int | None,
    owner_candidates: Sequence[Mapping[str, Any]],
    area_confidence: float,
    branch_count: int | None,
) -> list[str]:
    unknowns: list[str] = ["area_candidate_unconfirmed", "jira_component_unconfirmed"]
    if days_since_last_push is None:
        unknowns.append("activity_unknown")
    if not owner_candidates:
        unknowns.append("owner_unknown")
    else:
        unknowns.append("owner_candidate_unconfirmed")
    if area_confidence < 0.6:
        unknowns.append("area_low_confidence")
    if branch_count is None:
        unknowns.append("branch_count_unavailable")
    return unknowns


def _risk_summary(repo_facts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for fact in repo_facts:
        risks = fact.get("risks")
        if isinstance(risks, list):
            counts.update(str(risk) for risk in risks)
    return dict(sorted(counts.items()))


def _evidence_refs(*, name: str, source_snapshot: str | None) -> list[str]:
    snapshot = source_snapshot or "missing"
    return [
        f"github_discovery_snapshot:{snapshot}:repo:{name}:metadata",
        f"github_discovery_snapshot:{snapshot}:repo:{name}:contents",
        f"github_discovery_snapshot:{snapshot}:repo:{name}:commits_sanitized",
    ]


def _visibility(repo: Mapping[str, Any]) -> str:
    visibility = _safe_text(repo.get("visibility"))
    if visibility:
        return visibility
    return "private" if repo.get("private") else "public"


def _count_list(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def _days_since(value: str | None, *, now: datetime) -> int | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return max(0, (now - parsed).days)


def _parse_datetime(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _activity_bucket(days_since_last_push: int | None) -> str:
    if days_since_last_push is None:
        return "unknown"
    if days_since_last_push <= 30:
        return "active"
    if days_since_last_push <= 180:
        return "dormant"
    return "stale"


def _match_key(value: str) -> str:
    return value.rsplit("/", 1)[-1].casefold()


def _safe_text(value: Any, *, limit: int = 240) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    cleaned = _EMAIL_RE.sub(_EMAIL_MASK, cleaned)
    return cleaned[:limit]


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _guardrails() -> dict[str, Any]:
    return {
        "preview_only": True,
        "computed": True,
        "db_written": False,
        "network_calls": False,
        "external_writes": False,
        "github_writes": False,
        "jira_writes": False,
        "obsidian_written": False,
        "raw_email_returned": False,
        "repo_is_component_not_project": True,
        "repo_mapping_policy": _JIRA_REPO_MAPPING_POLICY,
        "one_repo_one_jira_project": False,
        "active_area_count": len(_AREA_CODES),
        "active_area_keys": list(_AREA_CODES),
        "future_later_area_keys": list(_FUTURE_LATER_AREA_CODES),
        "future_later_area_status": _FUTURE_LATER_AREA_STATUS,
        "area_owner_candidates_need_founder_confirm": True,
    }


def _provenance(*, computed: bool) -> dict[str, Any]:
    return {
        "mode": "computed_local_snapshot" if computed else "local_preview_missing",
        "mode_label_ru": "Вычисленные факты" if computed else "Предпросмотр",
        "preview_label_ru": "Предпросмотр",
        "computed_facts": computed,
        "computed_facts_label_ru": "Вычисленные факты",
        "source_label_ru": "Локальный снимок GitHub discovery",
        "production_graph": False,
        "production_graph_label_ru": "Рабочий граф компании не заявлен",
    }


def _redact_emails(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: _redact_emails(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_redact_emails(value) for value in obj]
    if isinstance(obj, str):
        return _EMAIL_RE.sub(_EMAIL_MASK, obj)
    return obj


def _finalize(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = _redact_emails(payload)
    serialized = json.dumps(cleaned, ensure_ascii=False, sort_keys=True)
    cleaned["guardrails"]["raw_email_returned"] = bool(_EMAIL_RE.search(serialized))
    return cleaned
