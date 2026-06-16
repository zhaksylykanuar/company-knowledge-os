"""Native Obsidian vault bridge for the evidence-backed knowledge graph.

The bridge writes a local, Obsidian-compatible markdown vault only when the
founder explicitly enables it and provides an absolute local vault path. The
same generator powers preview, dry-run, and real sync so the browser does not
show a divergent export.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AuditLog
from app.db.source_control_models import SourceRunRequest
from app.services.browser_config import sanitize_for_logs
from app.services.connector_diagnostics import build_connector_diagnostics
from app.services.knowledge_graph_view import build_knowledge_graph
from app.services.obsidian_exporter import sanitize_obsidian_filename
from app.services.secret_patterns import contains_secret_value
from app.services.source_run_receipts import build_source_run_receipt

DEFAULT_VAULT_NAME = "FounderOS Knowledge Vault"
MANIFEST_JSON_PATH = Path("_System") / "Manifest.json"
FOUNDEROS_UI_BASE_URL = "http://127.0.0.1:8765/ui"

# Display names for connector diagnostics notes under Sources/.
CONNECTOR_NOTE_NAMES = {
    "jira": "Jira",
    "github": "GitHub",
    "gmail": "Gmail",
    "meetings": "Meetings",
    "declarations": "Declarations",
    "manual_inputs": "Manual Inputs",
    "generated_evidence": "Generated Evidence",
    "share_packs": "Share Packs",
}

VAULT_DIRECTORIES = (
    "Projects",
    "People",
    "Tasks",
    "Products",
    "Meetings",
    "Decisions",
    "Risks",
    "Accounts",
    "Contacts",
    "Hypotheses",
    "Findings",
    "Sources",
    "Share Packs",
    "Inbox",
    "Data Quality",
    "_System",
)

NODE_DIRECTORY = {
    "project": "Projects",
    "person": "People",
    "task": "Tasks",
    "issue": "Tasks",
    "pull_request": "Tasks",
    "commit": "Tasks",
    "repo": "Products",
    "feature": "Products",
    "product_area": "Products",
    "meeting": "Meetings",
    "decision": "Decisions",
    "action_item": "Tasks",
    "risk": "Risks",
    "blocker": "Risks",
    "account": "Accounts",
    "company": "Accounts",
    "contact": "Contacts",
    "email_thread": "Contacts",
    "hypothesis": "Hypotheses",
    "declaration": "Hypotheses",
    "finding": "Findings",
    "proposal": "Inbox",
    "share_pack": "Share Packs",
    "source_event": "Sources",
    "normalized_event": "Sources",
    "knowledge_note": "Projects",
}

# --- Russian-first founder-facing text ---------------------------------------
# All founder-facing prose in generated notes is Russian. Technical identifiers
# (Jira keys, repo names, env-var names, source/connector names, SSE, run ids)
# stay verbatim but are given a Russian label or explanation in context.

RU_NOTICE = (
    "> Сгенерировано FounderOS из локального графа знаний. "
    "Не редактируй этот файл вручную — изменения потеряются при следующей "
    "синхронизации."
)
RU_CONNECTOR_NOTICE = (
    "> Сгенерировано диагностикой коннекторов FounderOS. Только чтение; "
    "управляй коннекторами в FounderOS. Секреты в это хранилище не пишутся."
)

# Jira-style technical key, e.g. CORE-1 — not a human-readable title.
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")

# Russian display names for node types (the raw type is kept alongside).
NODE_TYPE_RU = {
    "project": "проект",
    "person": "человек",
    "task": "задача",
    "issue": "задача",
    "pull_request": "pull request",
    "commit": "коммит",
    "repo": "репозиторий/компонент",
    "feature": "функция",
    "product_area": "продуктовая область",
    "meeting": "встреча",
    "decision": "решение",
    "action_item": "действие",
    "risk": "риск",
    "blocker": "блокер",
    "account": "компания",
    "company": "компания",
    "contact": "контакт",
    "email_thread": "почтовая переписка",
    "hypothesis": "гипотеза",
    "declaration": "декларация",
    "finding": "вывод",
    "proposal": "предложение",
    "share_pack": "пакет для шаринга",
    "source_event": "событие источника",
    "normalized_event": "нормализованное событие",
    "knowledge_note": "заметка",
    "system": "система",
    "connector_diagnostics": "диагностика коннектора",
}

# Russian display labels for vault directories (folder paths stay English so
# wikilinks and deterministic paths are unchanged).
DIRECTORY_RU = {
    "Projects": "Проекты",
    "People": "Люди",
    "Tasks": "Задачи",
    "Products": "Продукты (репозитории/компоненты)",
    "Meetings": "Встречи",
    "Decisions": "Решения",
    "Risks": "Риски",
    "Accounts": "Компании",
    "Contacts": "Контакты",
    "Hypotheses": "Гипотезы",
    "Findings": "Выводы",
    "Sources": "Источники",
    "Share Packs": "Пакеты для шаринга",
    "Inbox": "Входящие",
    "Data Quality": "Качество данных",
}

# Russian explanations for common issue/Jira statuses (raw value kept too).
STATUS_RU = {
    "backlog": "в очереди",
    "to do": "к выполнению",
    "todo": "к выполнению",
    "selected for development": "выбрано в работу",
    "in progress": "в работе",
    "in review": "на проверке",
    "in dev": "в разработке",
    "blocked": "заблокировано",
    "done": "готово",
    "closed": "закрыто",
    "resolved": "решено",
    "active": "активно",
    "archived": "в архиве",
}


def _clean(value: Any, max_chars: int = 300) -> str:
    return str(sanitize_markdown_content(value, max_chars=max_chars) or "")


def _first_present(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _is_technical_key(value: str, node: dict[str, Any]) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    props = node.get("properties") or {}
    if text == str(props.get("jira_key") or ""):
        return True
    if text == str(node.get("node_id") or ""):
        return True
    return bool(JIRA_KEY_RE.match(text))


def display_title_for_node(node: dict[str, Any]) -> str:
    """Russian-first human title: title_ru → name_ru → readable title → key."""
    props = node.get("properties") or {}
    russian = _first_present(
        props.get("title_ru"),
        props.get("name_ru"),
        props.get("display_name_ru"),
        node.get("title_ru"),
        node.get("name_ru"),
        node.get("display_name"),
    )
    if russian:
        return russian
    title = str(node.get("title") or "").strip()
    if title and not _is_technical_key(title, node):
        return title
    return title or str(node.get("node_id") or "Без названия")


def display_summary_for_node(node: dict[str, Any]) -> str:
    """Russian-first summary; falls back to the Russian title, never a raw key."""
    props = node.get("properties") or {}
    summary = _first_present(
        props.get("summary_ru"),
        props.get("description_ru"),
        node.get("summary_ru"),
    )
    if summary:
        return summary
    raw_summary = str(node.get("summary") or "").strip()
    if raw_summary and not _is_technical_key(raw_summary, node):
        return raw_summary
    russian_title = _first_present(props.get("title_ru"), props.get("name_ru"))
    if russian_title:
        return russian_title
    return "Пока нет краткого описания."


def status_ru_label(node: dict[str, Any]) -> str:
    """Render status as `raw` (русское пояснение)."""
    props = node.get("properties") or {}
    explicit = _first_present(props.get("status_ru"), node.get("status_ru"))
    raw = "archived" if node.get("archived") else str(props.get("status") or "active")
    if explicit:
        return f"`{_clean(raw, 60)}` ({_clean(explicit, 60)})"
    russian = STATUS_RU.get(raw.strip().casefold())
    if russian:
        return f"`{_clean(raw, 60)}` ({russian})"
    return f"`{_clean(raw, 60)}`"


def node_type_ru_label(node_type: str) -> str:
    russian = NODE_TYPE_RU.get(str(node_type))
    return f"`{node_type}` ({russian})" if russian else f"`{node_type}`"


SENSITIVE_KEY_RE = re.compile(
    r"(secret|token|api[_-]?key|password|client_secret|dev_api_key|"
    r"raw_object_ref|raw_payload|raw_body|email_body|body_html|body_text)",
    re.IGNORECASE,
)
SENSITIVE_VALUE_RE = re.compile(
    r"(OPENAI_API_KEY|GITHUB_TOKEN|JIRA_API_TOKEN|GMAIL_CLIENT_SECRET|"
    r"FOUNDEROS_DEV_API_KEY|dev_api_key|sk-[A-Za-z0-9_-]{10,}|raw://\S+)",
    re.IGNORECASE,
)
# Tokens that must never appear in a vault note in any form. These are
# dev-key NAMES (not legitimate connector env-var names) plus the raw-store
# scheme; actual secret *values* are caught separately by
# ``contains_secret_value`` so connector notes can still list env-var names.
FORBIDDEN_MARKDOWN_TERMS = (
    "FOUNDEROS_DEV_API_KEY",
    "dev_api_key",
    "raw://",
)


@dataclass(frozen=True)
class ObsidianBridgeConfig:
    enabled: bool
    vault_name: str
    vault_path: Path | None
    recommended_vault_path: Path
    sync_mode: str
    status: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ObsidianNote:
    node_id: str
    node_type: str
    title: str
    relative_path: Path
    frontmatter: dict[str, Any]
    body: str
    links: list[str]
    content_hash: str
    archived: bool = False

    @property
    def path(self) -> str:
        return self.relative_path.as_posix()

    @property
    def markdown(self) -> str:
        fm = dict(self.frontmatter)
        fm["content_hash"] = self.content_hash
        return f"---\n{render_frontmatter(fm)}---\n\n{self.body.rstrip()}\n"

    def preview_model(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "frontmatter": self.frontmatter | {"content_hash": self.content_hash},
            "body": self.body,
            "links": list(self.links),
            "redaction": {
                "raw_refs_included": False,
                "raw_bodies_included": False,
                "external_tokens_included": False,
            },
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class ObsidianVaultPlan:
    vault_name: str
    notes: list[ObsidianNote]
    node_path_map: dict[str, str]
    stats: dict[str, int]
    warnings: list[str]

    @property
    def files(self) -> list[dict[str, Any]]:
        return [note.preview_model() for note in self.notes]


def obsidian_bridge_config(config: Any = settings) -> ObsidianBridgeConfig:
    enabled = bool(getattr(config, "enable_obsidian_bridge", False))
    vault_name = str(
        getattr(config, "obsidian_bridge_vault_name", None) or DEFAULT_VAULT_NAME
    ).strip() or DEFAULT_VAULT_NAME
    workspace_path = Path(
        str(
            getattr(config, "founderos_local_workspace_path", None)
            or (Path.cwd() / ".local")
        )
    ).expanduser()
    recommended_vault_path = workspace_path / "obsidian" / vault_name
    sync_mode = str(getattr(config, "obsidian_bridge_sync_mode", "manual") or "manual")
    raw_path = getattr(config, "obsidian_bridge_vault_path", None)
    warnings: list[str] = []
    vault_path: Path | None = None
    status = "disabled"
    if enabled:
        if not raw_path:
            status = "missing_path"
            warnings.append(
                "FOUNDEROS_OBSIDIAN_VAULT_PATH is not configured. "
                f"Recommended path: {recommended_vault_path}"
            )
        else:
            candidate = Path(str(raw_path)).expanduser()
            if not candidate.is_absolute():
                status = "missing_path"
                warnings.append("FOUNDEROS_OBSIDIAN_VAULT_PATH must be absolute.")
            else:
                vault_path = candidate
                status = "configured"
    return ObsidianBridgeConfig(
        enabled=enabled,
        vault_name=vault_name,
        vault_path=vault_path,
        recommended_vault_path=recommended_vault_path,
        sync_mode=sync_mode,
        status=status,
        warnings=warnings,
    )


def sanitize_markdown_content(value: Any, *, max_chars: int = 1200) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            clean_key = sanitize_markdown_content(str(key), max_chars=120)
            if SENSITIVE_KEY_RE.search(str(key)):
                cleaned[str(clean_key)] = "***redacted***"
            else:
                cleaned[str(clean_key)] = sanitize_markdown_content(
                    item, max_chars=max_chars
                )
        return cleaned
    if isinstance(value, list):
        return [sanitize_markdown_content(item, max_chars=max_chars) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    text = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    text = SENSITIVE_VALUE_RE.sub("***redacted***", text)
    return text[:max_chars]


def sanitize_frontmatter(value: dict[str, Any]) -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    for key, item in value.items():
        if SENSITIVE_KEY_RE.search(str(key)):
            continue
        allowed[str(key)] = sanitize_markdown_content(item, max_chars=500)
    return allowed


def sanitize_wikilink_target(value: str) -> str:
    cleaned = str(sanitize_markdown_content(value, max_chars=240) or "")
    cleaned = cleaned.replace("[", " ").replace("]", " ").replace("|", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ./")
    return cleaned or "Untitled"


def note_relative_path_for_node(
    node: dict[str, Any],
    *,
    used_paths: set[str] | None = None,
) -> Path:
    node_type = str(node.get("node_type") or "knowledge_note")
    directory = NODE_DIRECTORY.get(node_type, "Projects")
    title = sanitize_wikilink_target(str(node.get("title") or node.get("node_id")))
    filename = sanitize_obsidian_filename(title, fallback=node_type, max_length=100)
    relative = Path(directory) / f"{filename}.md"
    used = used_paths if used_paths is not None else set()
    key = relative.as_posix().casefold()
    if key in used:
        suffix = hashlib.sha256(str(node.get("node_id")).encode("utf-8")).hexdigest()[:8]
        relative = Path(directory) / f"{filename} -- {suffix}.md"
        key = relative.as_posix().casefold()
    used.add(key)
    return safe_relative_path(relative)


def safe_relative_path(relative_path: Path | str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        raise ValueError("vault note path must be relative")
    parts = []
    for part in path.parts:
        if part in {"", ".", ".."}:
            raise ValueError("vault note path contains traversal")
        parts.append(sanitize_obsidian_filename(part, fallback="Untitled", max_length=120))
    clean = Path(*parts)
    if clean.suffix != ".md" and clean != MANIFEST_JSON_PATH:
        raise ValueError("vault note path must be a markdown file")
    return clean


def safe_vault_join(vault_path: Path, relative_path: Path | str) -> Path:
    relative = safe_relative_path(relative_path)
    base = vault_path.expanduser().resolve()
    target = (base / relative).resolve()
    target.relative_to(base)
    return target


def obsidian_open_uri(vault_name: str, file_path: str | None = None) -> str:
    uri = f"obsidian://open?vault={quote(vault_name, safe='')}"
    if file_path:
        file_without_suffix = file_path[:-3] if file_path.endswith(".md") else file_path
        uri += f"&file={quote(file_without_suffix, safe='')}"
    return uri


def render_frontmatter(frontmatter: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in frontmatter.items():
        lines.extend(_yaml_lines(str(key), value))
    return "\n".join(lines) + "\n"


def _yaml_lines(key: str, value: Any) -> list[str]:
    if isinstance(value, list):
        if not value:
            return [f"{key}: []"]
        return [f"{key}:"] + [f"  - {_yaml_scalar(item)}" for item in value]
    if isinstance(value, dict):
        if not value:
            return [f"{key}: {{}}"]
        return [f"{key}: {_yaml_scalar(value)}"]
    return [f"{key}: {_yaml_scalar(value)}"]


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


async def generate_obsidian_vault_plan(
    session: AsyncSession,
    *,
    vault_name: str = DEFAULT_VAULT_NAME,
    limit: int = 300,
) -> ObsidianVaultPlan:
    graph = await build_knowledge_graph(
        session,
        viewer_scope="founder",
        include_archived=True,
        limit=max(1, min(int(limit or 300), 300)),
    )
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    used_paths: set[str] = set()
    # Reserve connector-note paths first so a graph node titled "Jira" cannot
    # claim Sources/Jira.md before the connector diagnostics note.
    diagnostics = await build_connector_diagnostics(session)
    receipt_rows = (
        await session.execute(
            select(SourceRunRequest)
            .where(SourceRunRequest.run_id.is_not(None))
            .order_by(SourceRunRequest.created_at.desc(), SourceRunRequest.id.desc())
            .limit(80)
        )
    ).scalars().all()
    receipts_by_source: dict[str, list[dict[str, Any]]] = {}
    for row in receipt_rows:
        receipts_by_source.setdefault(row.source_type, []).append(
            build_source_run_receipt(row)
        )
    connector_notes = _connector_notes(
        diagnostics,
        used_paths=used_paths,
        receipts_by_source=receipts_by_source,
    )
    node_path_map = {
        str(node["node_id"]): note_relative_path_for_node(node, used_paths=used_paths).as_posix()
        for node in nodes
        if node.get("node_id")
    }
    notes = [
        _node_note(node, edges=edges, node_path_map=node_path_map, node_lookup=_node_lookup(nodes))
        for node in nodes
    ]
    notes.extend(connector_notes)
    notes.extend(_system_notes(vault_name=vault_name, notes=notes, graph=graph))
    stats = _note_stats(notes)
    warnings = list(graph.get("warnings") or [])
    return ObsidianVaultPlan(
        vault_name=vault_name,
        notes=notes,
        node_path_map=node_path_map,
        stats=stats,
        warnings=warnings,
    )


def _node_lookup(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(node["node_id"]): node for node in nodes if node.get("node_id")}


def _node_note(
    node: dict[str, Any],
    *,
    edges: list[dict[str, Any]],
    node_path_map: dict[str, str],
    node_lookup: dict[str, dict[str, Any]],
) -> ObsidianNote:
    node_id = str(node["node_id"])
    node_type = str(node.get("node_type") or "knowledge_note")
    title = str(sanitize_markdown_content(display_title_for_node(node), max_chars=180))
    raw_key = str(sanitize_markdown_content(node.get("title") or node_id, max_chars=180))
    aliases = [title] + ([raw_key] if raw_key and raw_key != title else [])
    relative_path = Path(node_path_map[node_id])
    outgoing = [edge for edge in edges if edge.get("source_node_id") == node_id]
    backlinks = [edge for edge in edges if edge.get("target_node_id") == node_id]
    links = _edge_links(
        outgoing,
        endpoint="target_node_id",
        node_path_map=node_path_map,
        node_lookup=node_lookup,
    )
    backlink_links = _edge_links(
        backlinks,
        endpoint="source_node_id",
        node_path_map=node_path_map,
        node_lookup=node_lookup,
    )
    source_types = [str(item) for item in node.get("source_types") or [] if item]
    archived = bool(node.get("archived"))
    frontmatter = sanitize_frontmatter(
        {
            "id": node_id,
            "type": node_type,
            "node_type": node_type,
            "status": "archived" if archived else str(node.get("properties", {}).get("status") or "active"),
            "tags": _frontmatter_tags(node_type, source_types),
            "aliases": aliases,
            "confidence": node.get("confidence"),
            "evidence_count": node.get("evidence_count") or 0,
            "finding_count": node.get("finding_count") or 0,
            "proposal_count": node.get("proposal_count") or 0,
            "source_types": source_types,
            "visibility_scope": node.get("visibility_scope") or "founder",
            "created_by_run_id": node.get("created_by_run_id"),
            "updated_by_run_id": node.get("updated_by_run_id"),
            "last_observed_at": node.get("last_observed_at"),
        }
    )
    body = _render_note_body(
        node=node,
        links=links,
        backlink_links=backlink_links,
        outgoing=outgoing,
        backlinks=backlinks,
    )
    content_hash = _content_hash({"frontmatter": frontmatter, "body": body})
    return ObsidianNote(
        node_id=node_id,
        node_type=node_type,
        title=title,
        relative_path=relative_path,
        frontmatter=frontmatter,
        body=body,
        links=[*links, *backlink_links],
        content_hash=content_hash,
        archived=archived,
    )


def _frontmatter_tags(node_type: str, source_types: list[str]) -> list[str]:
    tags = {f"#founderos/{sanitize_wikilink_target(node_type).casefold().replace(' ', '-')}"}
    tags.update(
        f"#source/{sanitize_wikilink_target(source).casefold().replace(' ', '-')}"
        for source in source_types
        if source
    )
    return sorted(tags)


def _edge_links(
    edges: list[dict[str, Any]],
    *,
    endpoint: str,
    node_path_map: dict[str, str],
    node_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for edge in edges:
        target = str(edge.get(endpoint) or "")
        if target not in node_path_map or target in seen:
            continue
        seen.add(target)
        target_node = node_lookup.get(target)
        label = display_title_for_node(target_node) if target_node else target
        links.append(_wikilink(node_path_map[target], str(label)))
    return links


def _wikilink(path: str, title: str | None = None) -> str:
    target = sanitize_wikilink_target(path[:-3] if path.endswith(".md") else path)
    label = sanitize_wikilink_target(title or target)
    return f"[[{target}|{label}]]"


def _render_note_body(
    *,
    node: dict[str, Any],
    links: list[str],
    backlink_links: list[str],
    outgoing: list[dict[str, Any]],
    backlinks: list[dict[str, Any]],
) -> str:
    title = _clean(display_title_for_node(node), 180)
    properties = sanitize_markdown_content(node.get("properties") or {})
    raw_props = node.get("properties") or {}
    source_types = [str(item) for item in node.get("source_types") or []]
    node_id = str(node.get("node_id"))
    node_type = str(node.get("node_type") or "knowledge_note")
    jira_key = raw_props.get("jira_key")
    raw_title = str(node.get("title") or "").strip()
    lines = [
        f"# {title}",
        "",
        RU_NOTICE,
        "",
        "## Кратко",
        "",
        _clean(display_summary_for_node(node), 1200),
        "",
        "## Свойства",
        "",
        f"- Тип (type): {node_type_ru_label(node_type)}",
        f"- Статус (status): {status_ru_label(node)}",
    ]
    if jira_key:
        lines.append(f"- Ключ Jira: `{_clean(jira_key, 60)}`")
    elif raw_title and _is_technical_key(raw_title, node):
        lines.append(f"- Технический ключ: `{_clean(raw_title, 60)}`")
    lines += [
        f"- Уверенность (confidence): `{_clean(node.get('confidence'))}`",
        f"- Число подтверждений (evidence): `{_clean(node.get('evidence_count') or 0)}`",
        "- Источник (source type): "
        + (", ".join(f"`{_clean(s)}`" for s in source_types) or "нет"),
        f"- Открыть в FounderOS: {FOUNDEROS_UI_BASE_URL}#/kt?node={quote(node_id, safe='')}",
        "",
        "## Обратные ссылки",
        "",
        *(_markdown_list(backlink_links) or ["Пока нет обратных ссылок."]),
        "",
        "## Исходящие связи",
        "",
        *(_markdown_list(links) or ["Пока нет исходящих связей."]),
        "",
        "## Подтверждения",
        "",
        f"- Связей с подтверждениями: {len(outgoing) + len(backlinks)}",
        "- Здесь сводка происхождения; исходные данные источников остаются в FounderOS.",
        "",
        "## Связанные выводы FounderOS",
        "",
        f"- Связано выводов (findings): `{_clean(node.get('finding_count') or 0)}`",
        "",
        "## Следующие действия",
        "",
        "- [ ] Просмотреть вывод или предложение в FounderOS",
        "- [ ] Открыть цепочку подтверждений в FounderOS",
        "",
        "## Происхождение данных",
        "",
        f"- Создано запуском (run id): `{_clean(node.get('created_by_run_id') or '')}`",
        f"- Обновлено запуском (run id): `{_clean(node.get('updated_by_run_id') or '')}`",
        f"- Замечено (observed at): `{_clean(node.get('last_observed_at') or '')}`",
        "",
        "## История решений",
        "",
        "История изменений и одобрений доступна в аудите FounderOS.",
        "",
        "## Качество данных",
        "",
        "Проверь раздел «Качество данных» в FounderOS: пробелы, устаревшие "
        "подтверждения, связи с низкой уверенностью.",
    ]
    if isinstance(properties, dict) and properties:
        lines.extend(["", "### Свойства (очищенные)", ""])
        for key in sorted(properties):
            value = properties[key]
            if value in (None, "", [], {}):
                continue
            lines.append(f"- **{key}**: `{_inline_value(value)}`")
    return "\n".join(lines).rstrip() + "\n"


def _markdown_list(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items if item]


def _inline_value(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(sanitize_markdown_content(value, max_chars=300))


def _system_notes(
    *,
    vault_name: str,
    notes: list[ObsidianNote],
    graph: dict[str, Any],
) -> list[ObsidianNote]:
    by_type: dict[str, int] = {}
    for note in notes:
        by_type[note.node_type] = by_type.get(note.node_type, 0) + 1
    recent = notes[:25]
    index_body = "\n".join(
        [
            "# Хранилище знаний FounderOS",
            "",
            "Открой это хранилище в Obsidian: граф знаний (Graph View), локальный "
            "граф, обратные ссылки, markdown-заметки, теги, свойства и поиск.",
            "",
            "## Разделы",
            "",
            *[
                f"- [[{directory}/_Index|{DIRECTORY_RU.get(directory, directory)}]]"
                for directory in VAULT_DIRECTORIES
                if not directory.startswith("_")
            ],
            "",
            "## Недавно сгенерированные заметки",
            "",
            *[f"- {_wikilink(note.path, note.title)}" for note in recent],
            "",
            "## Статистика графа",
            "",
            f"- Узлы (nodes): `{graph.get('stats', {}).get('nodes', 0)}`",
            f"- Связи (edges): `{graph.get('stats', {}).get('edges', 0)}`",
            f"- Скрыто лимитом: `{graph.get('stats', {}).get('hidden_count', 0)}`",
        ]
    ).rstrip() + "\n"
    system = [
        _system_note("00 Index.md", "Хранилище знаний FounderOS", index_body),
        _system_note(
            "01 Command Center.md",
            "Командный центр",
            "# Командный центр\n\nОткрой FounderOS для актуального статуса, действий, "
            "источников и проверки качества данных.\n",
        ),
        _system_note(
            "_System/Manifest.md",
            "Манифест",
            "# Манифест\n\n"
            + "\n".join(
                f"- {node_type} ({NODE_TYPE_RU.get(node_type, node_type)}): {count}"
                for node_type, count in sorted(by_type.items())
            )
            + "\n",
        ),
        _system_note(
            "_System/Sync Log.md",
            "Журнал синхронизации",
            "# Журнал синхронизации\n\nИстория синхронизаций также пишется в "
            "`audit_logs` FounderOS.\n",
        ),
        _system_note(
            "_System/Redaction Policy.md",
            "Политика очистки данных",
            "# Политика очистки данных\n\nИсходные данные источников, внешние токены, "
            "локальные dev-ключи и тела писем в это хранилище не записываются.\n",
        ),
    ]
    for directory in VAULT_DIRECTORIES:
        if directory.startswith("_"):
            continue
        matching = [note for note in notes if note.path.startswith(f"{directory}/")]
        directory_ru = DIRECTORY_RU.get(directory, directory)
        body = f"# {directory_ru}\n\n" + "\n".join(
            f"- {_wikilink(note.path, note.title)}" for note in matching[:100]
        )
        system.append(
            _system_note(f"{directory}/_Index.md", directory_ru, body.rstrip() + "\n")
        )
    return system


def _system_note(path: str, title: str, body: str) -> ObsidianNote:
    frontmatter = {
        "id": path,
        "type": "system",
        "status": "active",
        "tags": ["#founderos/system"],
        "aliases": [title],
        "confidence": 1.0,
        "evidence_count": 0,
        "finding_count": 0,
        "proposal_count": 0,
        "source_types": [],
        "visibility_scope": "founder",
        "created_by_run_id": None,
        "updated_by_run_id": None,
        "last_observed_at": None,
    }
    content_hash = _content_hash({"frontmatter": frontmatter, "body": body})
    return ObsidianNote(
        node_id=path,
        node_type="system",
        title=title,
        relative_path=safe_relative_path(path),
        frontmatter=frontmatter,
        body=body,
        links=[],
        content_hash=content_hash,
    )


def _connector_note(
    *,
    path: str,
    title: str,
    node_id: str,
    connector_state: str,
    body: str,
    links: list[str],
    source_type: str,
) -> ObsidianNote:
    frontmatter = {
        "id": node_id,
        "type": "connector_diagnostics",
        "source_type": source_type,
        "status": connector_state,
        "tags": [
            "#founderos/connector",
            f"#connector/{sanitize_wikilink_target(source_type).casefold().replace(' ', '-')}",
        ],
        "aliases": [title],
        "read_only": True,
        "secrets_exposed_to_browser": False,
        "external_writes_allowed": False,
        "visibility_scope": "founder",
    }
    content_hash = _content_hash({"frontmatter": frontmatter, "body": body})
    return ObsidianNote(
        node_id=node_id,
        node_type="connector_diagnostics",
        title=title,
        relative_path=safe_relative_path(path),
        frontmatter=frontmatter,
        body=body,
        links=links,
        content_hash=content_hash,
    )


_SAFE_ENV_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ /]{0,80}$")


def _safe_env_label(value: Any) -> str:
    # Env-var names are controlled constants (not user input) and are safe to
    # show by name. Guard anyway: anything unexpected or secret-shaped is
    # redacted rather than printed.
    text = str(value)
    if _SAFE_ENV_NAME_RE.match(text) and not contains_secret_value(text):
        return text
    return "***redacted***"


def _connector_missing_lines(missing_env_vars: list[Any]) -> list[str]:
    names = [str(name) for name in missing_env_vars if name]
    if not names:
        return ["- Все обязательные переменные окружения присутствуют (по имени)."]
    return [f"- `{_safe_env_label(name)}`" for name in names]


def _connector_note_body(
    connector: dict[str, Any],
    *,
    latest_receipt: dict[str, Any] | None = None,
) -> str:
    source_type = str(connector.get("source_type"))
    name = CONNECTOR_NOTE_NAMES.get(source_type, source_type)
    last_error = connector.get("last_error_sanitized") or {}
    error_line = (
        sanitize_markdown_content(last_error.get("message"), max_chars=200)
        if isinstance(last_error, dict) and last_error.get("message")
        else "нет"
    )
    # Setup steps are controlled constants; render literally so env-var names
    # stay readable (the markdown safety guard still blocks secret values).
    setup_steps = [f"- {step}" for step in connector.get("setup_steps") or []]
    limits = connector.get("limits") or {}
    lines = [
        f"# Коннектор {name}",
        "",
        RU_CONNECTOR_NOTICE,
        "",
        "## Статус",
        "",
        f"- Состояние коннектора (state): `{_clean(connector.get('connector_state'))}`",
        f"- Настроен (configured): `{bool(connector.get('configured'))}`",
        f"- Готовность (readiness): `{_clean(connector.get('readiness'))}`",
        f"- Тип адаптера (adapter type): `{_clean(connector.get('adapter_type'))}`",
        f"- Реальное выполнение (real execution): `{_clean(connector.get('real_execution'))}`",
        f"- Этап конвейера (pipeline stage): `{_clean(connector.get('pipeline_state'))}`",
        f"- Причина блокировки (blocked reason): `{_clean(connector.get('blocked_reason') or 'нет')}`",
        f"- Область обязательна (scope required): `{bool(connector.get('scope_required'))}`",
        f"- Область настроена (scope configured): `{bool(connector.get('scope_configured'))}`",
        f"- Размер области (scope count): `{_clean((connector.get('scope_summary') or {}).get('count') or 0)}`",
        f"- На паузе (paused): `{bool(connector.get('paused'))}`",
        f"- Событий загружено (events ingested): `{_clean(connector.get('events_ingested') or 0)}`",
        f"- Нормализованных событий (normalized events): `{_clean(connector.get('normalized_events') or 0)}`",
        f"- Следующее действие (next action): {_clean((connector.get('runbook') or {}).get('next_action'))}",
        "",
        "## Отсутствующая конфигурация (только имена)",
        "",
        *_connector_missing_lines(list(connector.get("missing_env_vars") or [])),
        "",
        "## Область и лимиты",
        "",
        *(
            _connector_missing_lines(list(connector.get("missing_scope_fields") or []))
            if connector.get("scope_required")
            and not connector.get("scope_configured")
            else ["- Область в порядке или не требуется."]
        ),
        f"- Лимиты: синхронизация `{_clean(limits.get('sync_limit') or 0)}`, "
        f"добор `{_clean(limits.get('backfill_limit') or 0)}`, "
        f"макс. дней `{_clean(limits.get('backfill_max_days') or 0)}`",
        "",
        "## Последняя активность",
        "",
        f"- Последняя проверка (last test): `{_clean(connector.get('last_test_at') or 'никогда')}`",
        f"- Последний успех (last success): `{_clean(connector.get('last_success_at') or 'никогда')}`",
        f"- Время последней ошибки (last error at): `{_clean(connector.get('last_error_at') or 'нет')}`",
        f"- Последняя ошибка (last error): {error_line}",
        "",
        "## Последний отчёт о запуске",
        "",
        *_connector_receipt_lines(latest_receipt),
        "",
        "## Политика безопасности",
        "",
        "- Только чтение (read only): `true`",
        "- Секреты доступны браузеру: `false`",
        "- Внешние записи разрешены: `false`",
        "",
        "## Настройка",
        "",
        *(setup_steps or ["- Настройка не требуется."]),
        f"- Документация (docs): {_clean(connector.get('docs_link'))}",
        f"- {_clean(connector.get('restart_required_hint'))}",
        "",
        "## Ссылки",
        "",
        "- [[_System/Connector Diagnostics|Диагностика коннекторов]]",
        f"- FounderOS: {FOUNDEROS_UI_BASE_URL}#/src",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _connector_receipt_lines(receipt: dict[str, Any] | None) -> list[str]:
    if not receipt:
        return ["- Отчётов о запусках пока нет."]
    warnings = receipt.get("warnings_sanitized") or []
    errors = receipt.get("errors_sanitized") or []
    return [
        f"- Отчёт (receipt): `{_clean(receipt.get('receipt_id'))}`",
        f"- Статус (status): `{_clean(receipt.get('status'))}`",
        f"- Действие (action): `{_clean(receipt.get('action_type'))}`",
        f"- Область настроена (scope configured): `{bool(receipt.get('scope_configured'))}`",
        f"- Лимиты (limits): `{_clean(receipt.get('limits_applied') or {})}`",
        f"- Водяной знак (watermark): `{_clean(receipt.get('watermark_update_reason'))}`",
        f"- События: замечено `{_clean(receipt.get('events_seen') or 0)}`, "
        f"загружено `{_clean(receipt.get('events_ingested') or 0)}`, "
        f"нормализовано `{_clean(receipt.get('normalized_events') or 0)}`",
        f"- Прочитано страниц (pages read): `{_clean(receipt.get('pages_read') or 0)}`",
        f"- Причина остановки (stopped reason): `{_clean(receipt.get('stopped_reason') or 'нет')}`",
        f"- Предупреждений (warnings): `{_clean(len(warnings))}`",
        f"- Ошибок (errors): `{_clean(len(errors))}`",
        f"- Следующее действие (next action): `{_receipt_next_action(receipt)}`",
        f"- FounderOS: {FOUNDEROS_UI_BASE_URL}#/src",
    ]


def _receipt_next_action(receipt: dict[str, Any]) -> str:
    status = str(receipt.get("status") or "")
    action = str(receipt.get("action_type") or "")
    if action == "preview_sync":
        return "Проверь предпросмотр, затем запусти синхронизацию, если область и лимиты верны"
    if status in {"failed", "blocked", "skipped", "partial_succeeded"}:
        return "Изучи отчёт и безопасно повтори после устранения причины"
    if status == "succeeded" and int(receipt.get("events_ingested") or 0) > 0:
        return "Запусти evidence pipeline, затем синхронизацию Obsidian"
    return "Наблюдай за следующим запуском источника"


def _connector_receipts_body(receipts: list[dict[str, Any]]) -> str:
    lines = [
        "# Отчёты о запусках коннекторов",
        "",
        "> Сгенерировано FounderOS. Только очищенные отчёты; без исходных данных и секретов.",
        "",
        "| Источник | Действие | Статус | Водяной знак | События | Лимит | Причина |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for receipt in receipts:
        source = sanitize_markdown_content(receipt.get("source_type"))
        action = sanitize_markdown_content(receipt.get("action_type"))
        status = sanitize_markdown_content(receipt.get("status"))
        watermark = sanitize_markdown_content(receipt.get("watermark_update_reason"))
        events = sanitize_markdown_content(receipt.get("events_ingested") or 0)
        limit = sanitize_markdown_content(receipt.get("limit_applied") or 0)
        reason = sanitize_markdown_content(
            receipt.get("blocked_reason") or receipt.get("stopped_reason") or "none"
        )
        lines.append(
            f"| {source} | {action} | {status} | {watermark} | {events} | {limit} | {reason} |"
        )
    if not receipts:
        lines.append("| нет | нет | нет | нет | 0 | 0 | отчётов пока нет |")
    lines.extend(
        [
            "",
            "## Политика безопасности",
            "",
            "- Только чтение (read only): `true`",
            "- Секреты доступны браузеру: `false`",
            "- Внешние записи разрешены: `false`",
            "- Исходные данные провайдера включены: `false`",
            "",
            "## Ссылки",
            "",
            "- [[_System/Connector Diagnostics|Диагностика коннекторов]]",
            f"- FounderOS: {FOUNDEROS_UI_BASE_URL}#/src",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _connector_overview_body(connectors: list[dict[str, Any]]) -> str:
    lines = [
        "# Диагностика коннекторов",
        "",
        "> Сгенерировано FounderOS. Только чтение, готовность коннекторов. Без секретов.",
        "",
        "## Коннекторы",
        "",
        "| Коннектор | Состояние | Настроен | Адаптер | Реальное вып. | Нет переменных |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for connector in connectors:
        source_type = str(connector.get("source_type"))
        name = CONNECTOR_NOTE_NAMES.get(source_type, source_type)
        missing = len(connector.get("missing_env_vars") or [])
        lines.append(
            f"| [[Sources/{name}\\|{name}]] "
            f"| {sanitize_markdown_content(connector.get('connector_state'))} "
            f"| {bool(connector.get('configured'))} "
            f"| {sanitize_markdown_content(connector.get('adapter_type'))} "
            f"| {sanitize_markdown_content(connector.get('real_execution'))} "
            f"| {missing} |"
        )
    lines.extend(
        [
            "",
            "## Политика безопасности",
            "",
            "- Только чтение (read only): `true`",
            "- Секреты доступны браузеру: `false`",
            "- Внешние записи разрешены: `false`",
            "",
            f"- FounderOS: {FOUNDEROS_UI_BASE_URL}#/src",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _local_pilot_body(diagnostics: dict[str, Any]) -> str:
    pilot = diagnostics.get("pilot") or {}
    connectors = list(diagnostics.get("connectors") or [])
    lines = [
        "# Локальный пилот коннекторов",
        "",
        "> Сгенерировано диагностикой коннекторов FounderOS. Только чтение, статус "
        "сквозного прогона (E2E). Секреты в это хранилище не пишутся.",
        "",
        "## Реальное выполнение",
        "",
        f"- Реальные коннекторы включены (real connectors enabled): "
        f"`{bool(pilot.get('real_execution_enabled'))}`",
        "",
        "## Коннекторы",
        "",
        "| Коннектор | Этап конвейера | События | Нормализовано | Следующее действие |",
        "| --- | --- | --- | --- | --- |",
    ]
    for connector in connectors:
        source_type = str(connector.get("source_type"))
        name = CONNECTOR_NOTE_NAMES.get(source_type, source_type)
        runbook = connector.get("runbook") or {}
        lines.append(
            f"| [[Sources/{name}\\|{name}]] "
            f"| {sanitize_markdown_content(connector.get('pipeline_state'))} "
            f"| {sanitize_markdown_content(connector.get('events_ingested') or 0)} "
            f"| {sanitize_markdown_content(connector.get('normalized_events') or 0)} "
            f"| {sanitize_markdown_content(runbook.get('next_action'))} |"
        )
    lines.extend(["", "## Этапы конвейера", ""])
    for state, count in sorted((pilot.get("by_pipeline_state") or {}).items()):
        lines.append(f"- {sanitize_markdown_content(state)}: `{int(count)}`")
    lines.extend(["", "## Следующие шаги", ""])
    for step in pilot.get("next_steps") or []:
        lines.append(f"- {sanitize_markdown_content(step, max_chars=400)}")
    commands = pilot.get("commands") or {}
    lines.extend(["", "## Команды", ""])
    for label in ("pilot", "operator_run", "evidence_pipeline", "sync_obsidian", "restart"):
        if commands.get(label):
            lines.append(f"- {label}: `{commands[label]}`")
    lines.extend(
        [
            "",
            "## Политика безопасности",
            "",
            "- Только чтение (read only): `true`",
            "- Секреты доступны браузеру: `false`",
            "- Внешние записи разрешены: `false`",
            "",
            "- [[_System/Connector Diagnostics|Диагностика коннекторов]]",
            f"- FounderOS: {FOUNDEROS_UI_BASE_URL}#/src",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _connector_notes(
    diagnostics: dict[str, Any],
    *,
    used_paths: set[str],
    receipts_by_source: dict[str, list[dict[str, Any]]],
) -> list[ObsidianNote]:
    connectors = list(diagnostics.get("connectors") or [])
    notes: list[ObsidianNote] = []
    overview_links: list[str] = []
    for connector in connectors:
        source_type = str(connector.get("source_type"))
        name = CONNECTOR_NOTE_NAMES.get(source_type, source_type)
        path = f"Sources/{name}.md"
        used_paths.add(path.casefold())
        overview_links.append(_wikilink(path, name))
        notes.append(
            _connector_note(
                path=path,
                title=f"Коннектор {name}",
                node_id=f"connector:{source_type}",
                connector_state=str(connector.get("connector_state") or "unknown"),
                body=_connector_note_body(
                    connector,
                    latest_receipt=(receipts_by_source.get(source_type) or [None])[0],
                ),
                links=["[[_System/Connector Diagnostics|Диагностика коннекторов]]"],
                source_type=source_type,
            )
        )
    overview_path = "_System/Connector Diagnostics.md"
    used_paths.add(overview_path.casefold())
    notes.append(
        _connector_note(
            path=overview_path,
            title="Диагностика коннекторов",
            node_id="connector:diagnostics",
            connector_state="overview",
            body=_connector_overview_body(connectors),
            links=overview_links,
            source_type="all",
        )
    )
    receipts_path = "_System/Connector Run Receipts.md"
    used_paths.add(receipts_path.casefold())
    all_receipts = [
        receipt
        for receipts in receipts_by_source.values()
        for receipt in receipts
    ]
    notes.append(
        _connector_note(
            path=receipts_path,
            title="Отчёты о запусках коннекторов",
            node_id="connector:run_receipts",
            connector_state="receipts",
            body=_connector_receipts_body(all_receipts[:50]),
            links=overview_links,
            source_type="all",
        )
    )
    pilot_path = "_System/Local Pilot.md"
    used_paths.add(pilot_path.casefold())
    notes.append(
        _connector_note(
            path=pilot_path,
            title="Локальный пилот коннекторов",
            node_id="connector:local_pilot",
            connector_state="pilot",
            body=_local_pilot_body(diagnostics),
            links=["[[_System/Connector Diagnostics|Диагностика коннекторов]]"],
            source_type="all",
        )
    )
    return notes


def _note_stats(notes: list[ObsidianNote]) -> dict[str, int]:
    stats = {
        "notes": len(notes),
        "projects": 0,
        "people": 0,
        "tasks": 0,
        "meetings": 0,
        "findings": 0,
        "risks": 0,
        "hypotheses": 0,
        "sources": 0,
    }
    for note in notes:
        if note.node_type == "project":
            stats["projects"] += 1
        elif note.node_type == "person":
            stats["people"] += 1
        elif note.node_type in {"task", "issue", "pull_request", "action_item"}:
            stats["tasks"] += 1
        elif note.node_type == "meeting":
            stats["meetings"] += 1
        elif note.node_type == "finding":
            stats["findings"] += 1
        elif note.node_type in {"risk", "blocker"}:
            stats["risks"] += 1
        elif note.node_type in {"hypothesis", "declaration"}:
            stats["hypotheses"] += 1
        elif note.node_type in {"source_event", "normalized_event"}:
            stats["sources"] += 1
    return stats


def _content_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _assert_markdown_safe(markdown: str) -> None:
    if contains_secret_value(markdown):
        raise ValueError("unsafe markdown: secret value detected")
    lowered = markdown.casefold()
    for term in FORBIDDEN_MARKDOWN_TERMS:
        if term.casefold() in lowered:
            raise ValueError(f"unsafe markdown term: {term}")


async def build_obsidian_preview(
    session: AsyncSession,
    *,
    vault_name: str | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    cfg = obsidian_bridge_config()
    plan = await generate_obsidian_vault_plan(
        session,
        vault_name=vault_name or cfg.vault_name,
        limit=limit,
    )
    files = plan.files[:limit]
    return {
        "vault_name": plan.vault_name,
        "files": files,
        "manifest": {
            "file_write_performed": False,
            "source": "obsidian_bridge_generator",
            "node_path_map": dict(plan.node_path_map),
            "stats": dict(plan.stats),
            "content_hash": _content_hash([file["content_hash"] for file in files]),
            "redaction": {
                "excluded_sections": [
                    "raw_source_bodies",
                    "external_tokens",
                    "raw_email_bodies",
                ]
            },
        },
        "warnings": list(plan.warnings),
    }


async def build_obsidian_status(session: AsyncSession) -> dict[str, Any]:
    cfg = obsidian_bridge_config()
    plan = await generate_obsidian_vault_plan(session, vault_name=cfg.vault_name, limit=300)
    return {
        "status": cfg.status,
        "enabled": cfg.enabled,
        "vault_name": cfg.vault_name,
        "sync_mode": cfg.sync_mode,
        "configured": cfg.status == "configured",
        "vault_path_configured": cfg.vault_path is not None,
        "vault_path": str(cfg.vault_path) if cfg.vault_path else None,
        "recommended_vault_path": str(cfg.recommended_vault_path),
        "recommended_relative_path": ".local/obsidian/FounderOS Knowledge Vault",
        "open_vault_uri": obsidian_open_uri(cfg.vault_name),
        "open_index_uri": obsidian_open_uri(cfg.vault_name, "00 Index.md"),
        "notes_seen": len(plan.notes),
        "stats": dict(plan.stats),
        "recent_notes": [
            {"node_id": note.node_id, "title": note.title, "path": note.path}
            for note in plan.notes[:20]
        ],
        "warnings": [*cfg.warnings, *plan.warnings],
    }


async def sync_obsidian_vault(
    session: AsyncSession,
    *,
    dry_run: bool = True,
    requested_by: str = "founder",
) -> dict[str, Any]:
    cfg = obsidian_bridge_config()
    if cfg.status != "configured" or cfg.vault_path is None:
        result = {
            "status": cfg.status,
            "dry_run": dry_run,
            "vault_name": cfg.vault_name,
            "vault_path": None,
            "notes_seen": 0,
            "notes_created": 0,
            "notes_updated": 0,
            "notes_unchanged": 0,
            "notes_archived": 0,
            "warnings": list(cfg.warnings),
            "manifest": {"file_write_performed": False},
        }
        await _audit_sync(session, result=result, requested_by=requested_by)
        return result

    plan = await generate_obsidian_vault_plan(session, vault_name=cfg.vault_name, limit=300)
    created = updated = unchanged = archived = 0
    changed_notes: list[dict[str, str]] = []
    for note in plan.notes:
        _assert_markdown_safe(note.markdown)
        target = safe_vault_join(cfg.vault_path, note.relative_path)
        existing = target.read_text(encoding="utf-8") if target.exists() else None
        if existing is None:
            created += 1
            changed_notes.append({"path": note.path, "change": "created"})
        elif existing != note.markdown:
            updated += 1
            changed_notes.append({"path": note.path, "change": "updated"})
        else:
            unchanged += 1
        if note.archived:
            archived += 1
        if not dry_run and existing != note.markdown:
            _atomic_write(target, note.markdown)

    manifest = {
        "file_write_performed": not dry_run,
        "node_path_map": dict(plan.node_path_map),
        "stats": dict(plan.stats),
        "changed_notes": changed_notes[:50],
        "content_hash": _content_hash([note.content_hash for note in plan.notes]),
    }
    if not dry_run:
        manifest_target = safe_vault_join(cfg.vault_path, MANIFEST_JSON_PATH)
        _atomic_write(manifest_target, json.dumps(manifest, ensure_ascii=False, indent=2))
    result = {
        "status": "succeeded",
        "dry_run": dry_run,
        "vault_path": str(cfg.vault_path),
        "vault_name": cfg.vault_name,
        "notes_seen": len(plan.notes),
        "notes_created": created,
        "notes_updated": updated,
        "notes_unchanged": unchanged,
        "notes_archived": archived,
        "warnings": list(plan.warnings),
        "manifest": manifest,
    }
    await _audit_sync(session, result=result, requested_by=requested_by)
    return result


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


async def _audit_sync(
    session: AsyncSession,
    *,
    result: dict[str, Any],
    requested_by: str,
) -> None:
    event_id = f"obsidian_sync_{uuid4().hex}"
    safe_result = sanitize_for_logs(
        {
            key: value
            for key, value in result.items()
            if key not in {"vault_path"}
        }
    )
    session.add(
        AuditLog(
            event_type="obsidian_vault_sync",
            actor=requested_by,
            correlation_id=event_id,
            trace_id=event_id,
            before_ref="knowledge_graph",
            after_ref="obsidian_vault",
            payload=safe_result,
        )
    )
    await session.flush()


async def obsidian_open_vault_model() -> dict[str, Any]:
    cfg = obsidian_bridge_config()
    if cfg.status != "configured":
        return {"status": cfg.status, "uri": None, "warnings": list(cfg.warnings)}
    return {
        "status": "configured",
        "uri": obsidian_open_uri(cfg.vault_name),
        "vault_name": cfg.vault_name,
    }


async def obsidian_open_node_model(
    session: AsyncSession,
    *,
    node_id: str,
) -> dict[str, Any] | None:
    cfg = obsidian_bridge_config()
    if cfg.status != "configured":
        return {"status": cfg.status, "uri": None, "warnings": list(cfg.warnings)}
    plan = await generate_obsidian_vault_plan(session, vault_name=cfg.vault_name, limit=300)
    path = plan.node_path_map.get(node_id)
    if path is None:
        return None
    return {
        "status": "configured",
        "uri": obsidian_open_uri(cfg.vault_name, path),
        "vault_name": cfg.vault_name,
        "node_id": node_id,
        "file": path,
    }


def build_cli_summary(sync_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": sync_result.get("status"),
        "dry_run": sync_result.get("dry_run"),
        "vault_name": sync_result.get("vault_name"),
        "vault_path_configured": bool(sync_result.get("vault_path")),
        "notes_created": sync_result.get("notes_created", 0),
        "notes_updated": sync_result.get("notes_updated", 0),
        "notes_unchanged": sync_result.get("notes_unchanged", 0),
        "notes_archived": sync_result.get("notes_archived", 0),
        "warnings": sync_result.get("warnings", []),
    }
