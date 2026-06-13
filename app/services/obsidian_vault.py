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

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AuditLog
from app.services.browser_config import sanitize_for_logs
from app.services.connector_diagnostics import build_connector_diagnostics
from app.services.knowledge_graph_view import build_knowledge_graph
from app.services.obsidian_exporter import sanitize_obsidian_filename
from app.services.secret_patterns import contains_secret_value

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
    connector_notes = _connector_notes(diagnostics, used_paths=used_paths)
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
    title = str(sanitize_markdown_content(node.get("title") or node_id, max_chars=180))
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
            "aliases": [title],
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
        title = node_lookup.get(target, {}).get("title") or target
        links.append(_wikilink(node_path_map[target], str(title)))
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
    title = str(sanitize_markdown_content(node.get("title") or node.get("node_id")))
    properties = sanitize_markdown_content(node.get("properties") or {})
    source_types = [str(item) for item in node.get("source_types") or []]
    node_id = str(node.get("node_id"))
    lines = [
        f"# {title}",
        "",
        "> Generated by FounderOS from evidence-backed Postgres graph data. Edit in FounderOS; treat this vault as a local mirror.",
        "",
        "## Summary",
        "",
        str(sanitize_markdown_content(node.get("summary") or "No summary yet.")),
        "",
        "## Properties",
        "",
        f"- Type: `{sanitize_markdown_content(node.get('node_type'))}`",
        f"- Confidence: `{sanitize_markdown_content(node.get('confidence'))}`",
        f"- Evidence count: `{sanitize_markdown_content(node.get('evidence_count') or 0)}`",
        f"- Source types: {', '.join(f'`{sanitize_markdown_content(s)}`' for s in source_types) or 'none'}",
        f"- FounderOS: {FOUNDEROS_UI_BASE_URL}#/kt?node={quote(node_id, safe='')}",
        "",
        "## Backlinks",
        "",
        *(_markdown_list(backlink_links) or ["No backlinks yet."]),
        "",
        "## Outgoing Links",
        "",
        *(_markdown_list(links) or ["No outgoing links yet."]),
        "",
        "## Evidence",
        "",
        f"- Evidence-backed links: {len(outgoing) + len(backlinks)}",
        "- Source lineage is summarized here; raw source payloads stay in FounderOS.",
        "",
        "## Related Findings",
        "",
        f"- Findings linked: `{sanitize_markdown_content(node.get('finding_count') or 0)}`",
        "",
        "## Related Actions",
        "",
        "- [ ] Review finding or proposal in FounderOS",
        "- [ ] Open evidence trail in FounderOS",
        "",
        "## Source Lineage",
        "",
        f"- Created by run: `{sanitize_markdown_content(node.get('created_by_run_id') or '')}`",
        f"- Updated by run: `{sanitize_markdown_content(node.get('updated_by_run_id') or '')}`",
        f"- Last observed: `{sanitize_markdown_content(node.get('last_observed_at') or '')}`",
        "",
        "## Decision History",
        "",
        "Review audit history in FounderOS for approved changes.",
        "",
        "## Data Quality",
        "",
        "Check FounderOS Data Quality for gaps, stale evidence, or low-confidence links.",
    ]
    if isinstance(properties, dict) and properties:
        lines.extend(["", "### Sanitized Properties", ""])
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
            "# FounderOS Knowledge Vault",
            "",
            "Open this vault in Obsidian to use Graph View, Local Graph, Backlinks, Markdown notes, tags, properties, and search.",
            "",
            "## Sections",
            "",
            *[f"- [[{directory}/_Index|{directory}]]" for directory in VAULT_DIRECTORIES if not directory.startswith("_")],
            "",
            "## Recent Generated Notes",
            "",
            *[f"- {_wikilink(note.path, note.title)}" for note in recent],
            "",
            "## Graph Stats",
            "",
            f"- Nodes: `{graph.get('stats', {}).get('nodes', 0)}`",
            f"- Edges: `{graph.get('stats', {}).get('edges', 0)}`",
            f"- Hidden by limit: `{graph.get('stats', {}).get('hidden_count', 0)}`",
        ]
    ).rstrip() + "\n"
    system = [
        _system_note("00 Index.md", "FounderOS Knowledge Vault", index_body),
        _system_note(
            "01 Command Center.md",
            "Command Center",
            "# Command Center\n\nOpen FounderOS for live status, actions, sources, and data-quality review.\n",
        ),
        _system_note(
            "_System/Manifest.md",
            "Manifest",
            "# Manifest\n\n"
            + "\n".join(f"- {node_type}: {count}" for node_type, count in sorted(by_type.items()))
            + "\n",
        ),
        _system_note(
            "_System/Sync Log.md",
            "Sync Log",
            "# Sync Log\n\nSync history is also recorded in FounderOS `audit_logs`.\n",
        ),
        _system_note(
            "_System/Redaction Policy.md",
            "Redaction Policy",
            "# Redaction Policy\n\nRaw source payloads, external tokens, local dev keys, and raw email bodies are not written to this vault.\n",
        ),
    ]
    for directory in VAULT_DIRECTORIES:
        if directory.startswith("_"):
            continue
        matching = [note for note in notes if note.path.startswith(f"{directory}/")]
        body = f"# {directory}\n\n" + "\n".join(
            f"- {_wikilink(note.path, note.title)}" for note in matching[:100]
        )
        system.append(_system_note(f"{directory}/_Index.md", directory, body.rstrip() + "\n"))
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
        return ["- All required environment variables are present (by name)."]
    return [f"- `{_safe_env_label(name)}`" for name in names]


def _connector_note_body(connector: dict[str, Any]) -> str:
    source_type = str(connector.get("source_type"))
    name = CONNECTOR_NOTE_NAMES.get(source_type, source_type)
    last_error = connector.get("last_error_sanitized") or {}
    error_line = (
        sanitize_markdown_content(last_error.get("message"), max_chars=200)
        if isinstance(last_error, dict) and last_error.get("message")
        else "none"
    )
    # Setup steps are controlled constants; render literally so env-var names
    # stay readable (the markdown safety guard still blocks secret values).
    setup_steps = [f"- {step}" for step in connector.get("setup_steps") or []]
    lines = [
        f"# {name} connector",
        "",
        "> Generated by FounderOS connector diagnostics. Read-only mirror; "
        "manage connectors in FounderOS. No secrets are written to this vault.",
        "",
        "## Status",
        "",
        f"- Connector state: `{sanitize_markdown_content(connector.get('connector_state'))}`",
        f"- Configured: `{bool(connector.get('configured'))}`",
        f"- Readiness: `{sanitize_markdown_content(connector.get('readiness'))}`",
        f"- Adapter type: `{sanitize_markdown_content(connector.get('adapter_type'))}`",
        f"- Paused: `{bool(connector.get('paused'))}`",
        "",
        "## Missing Required Configuration (names only)",
        "",
        *_connector_missing_lines(list(connector.get("missing_env_vars") or [])),
        "",
        "## Last Activity",
        "",
        f"- Last test at: `{sanitize_markdown_content(connector.get('last_test_at') or 'never')}`",
        f"- Last success at: `{sanitize_markdown_content(connector.get('last_success_at') or 'never')}`",
        f"- Last error at: `{sanitize_markdown_content(connector.get('last_error_at') or 'none')}`",
        f"- Last error: {error_line}",
        "",
        "## Security Policy",
        "",
        "- Read only: `true`",
        "- Secrets exposed to browser: `false`",
        "- External writes allowed: `false`",
        "",
        "## Setup",
        "",
        *(setup_steps or ["- No setup required."]),
        f"- Docs: {sanitize_markdown_content(connector.get('docs_link'))}",
        f"- {sanitize_markdown_content(connector.get('restart_required_hint'))}",
        "",
        "## Links",
        "",
        "- [[_System/Connector Diagnostics|Connector Diagnostics]]",
        f"- FounderOS: {FOUNDEROS_UI_BASE_URL}#/src",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _connector_overview_body(connectors: list[dict[str, Any]]) -> str:
    lines = [
        "# Connector Diagnostics",
        "",
        "> Generated by FounderOS. Read-only connector readiness. No secrets.",
        "",
        "## Connectors",
        "",
        "| Connector | State | Configured | Adapter | Missing vars |",
        "| --- | --- | --- | --- | --- |",
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
            f"| {missing} |"
        )
    lines.extend(
        [
            "",
            "## Security Policy",
            "",
            "- Read only: `true`",
            "- Secrets exposed to browser: `false`",
            "- External writes allowed: `false`",
            "",
            f"- FounderOS: {FOUNDEROS_UI_BASE_URL}#/src",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _connector_notes(
    diagnostics: dict[str, Any],
    *,
    used_paths: set[str],
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
                title=f"{name} connector",
                node_id=f"connector:{source_type}",
                connector_state=str(connector.get("connector_state") or "unknown"),
                body=_connector_note_body(connector),
                links=["[[_System/Connector Diagnostics|Connector Diagnostics]]"],
                source_type=source_type,
            )
        )
    overview_path = "_System/Connector Diagnostics.md"
    used_paths.add(overview_path.casefold())
    notes.append(
        _connector_note(
            path=overview_path,
            title="Connector Diagnostics",
            node_id="connector:diagnostics",
            connector_state="overview",
            body=_connector_overview_body(connectors),
            links=overview_links,
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
