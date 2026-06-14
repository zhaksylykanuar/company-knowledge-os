# Obsidian Native Bridge

FounderOS can mirror its evidence-backed knowledge graph into a real local
Obsidian vault. FounderOS remains the source of truth; Obsidian is the native
graph, backlinks, local graph, markdown notes, tags, properties, and search
surface.

The bridge never sends data to Obsidian Cloud and never writes outside the
configured local vault path.

## Setup

1. Install the Obsidian desktop app.
2. Bootstrap the project-local workspace:

```bash
cd /Users/anuarzh/Projects/company-knowledge-os
uv run python scripts/bootstrap_local_workspace.py --apply
uv run python scripts/start_local.py
```

3. Open `http://127.0.0.1:8765/ui`.
4. Go to Knowledge Tree.
5. Click Dry Run.
6. Click Sync Now.
7. Click Open Vault in Obsidian.
8. In Obsidian, use Graph View, Local Graph, Backlinks, Tags, and Search.

Manual local env editing is no longer required for the local happy path.
The bootstrap script preserves existing local secrets, writes only a managed
FounderOS block, and points the bridge to:

```text
.local/obsidian/FounderOS Knowledge Vault
```

If an older Obsidian vault path is already present in the local env override, bootstrap
copies its files into `.local/obsidian/FounderOS Knowledge Vault` and leaves the
old vault untouched. Migration details are written to `.local/migration-log.json`.

## Operator Commands

Preview without file writes:

```bash
uv run python scripts/sync_obsidian_vault.py \
  --confirm-run "SYNC OBSIDIAN VAULT" \
  --dry-run
```

Write the local vault:

```bash
uv run python scripts/sync_obsidian_vault.py \
  --confirm-run "SYNC OBSIDIAN VAULT"
```

Run the evidence pipeline and then sync Obsidian explicitly:

```bash
uv run python scripts/run_evidence_pipeline.py \
  --confirm-run "RUN EVIDENCE PIPELINE" \
  --sync-obsidian
```

No sync happens from the evidence pipeline unless `--sync-obsidian` is passed.

## Vault Shape

```text
FounderOS Knowledge Vault/
  00 Index.md
  01 Command Center.md
  Projects/
  People/
  Tasks/
  Products/
  Meetings/
  Decisions/
  Risks/
  Accounts/
  Contacts/
  Hypotheses/
  Findings/
  Sources/
  Share Packs/
  Inbox/
  Data Quality/
  _System/
    Manifest.md
    Manifest.json
    Sync Log.md
    Redaction Policy.md
```

Each graph node becomes a markdown note with YAML frontmatter and real Obsidian
wikilinks. Obsidian builds the graph from those links, not from custom JSON.

The generated local vault lives under:

```text
/Users/anuarzh/Projects/company-knowledge-os/.local/obsidian/FounderOS Knowledge Vault
```

`.local/` and the local env override are gitignored.

## Connector Diagnostics & Local Pilot Notes

The vault also mirrors connector readiness as read-only notes:

```text
_System/Connector Diagnostics.md   # all connectors: state, adapter, real exec
_System/Local Pilot.md             # E2E pilot: pipeline stages, counts, next steps
Sources/Jira.md
Sources/GitHub.md
Sources/Gmail.md
```

Each connector note shows status, configured/missing (env-var **names only**),
adapter type, real-execution enabled/disabled, pipeline stage, events ingested /
normalized, the next action, and the security policy. No token values and no raw
bodies are ever written.

Drive the end-to-end connector chain locally with:

```bash
uv run python scripts/run_local_connector_pilot.py \
  --confirm-run "RUN LOCAL CONNECTOR PILOT"
```

The pilot previews the vault by default; pass `--sync-obsidian` for a real
write. See `source-connectors.md` for the full pilot runbook.

## Safety

- The bridge must be enabled explicitly.
- `FOUNDEROS_OBSIDIAN_VAULT_PATH` must be an absolute local path.
- Bootstrap sets that path to the project-local `.local/` workspace.
- Dry run never writes files.
- Real sync writes by atomic temp-file replace.
- Path traversal is rejected.
- Raw source payloads, raw email bodies, external tokens, local dev keys, and
  raw object refs are not written to markdown.
- Team/investor views cannot access the bridge endpoints.
- Open endpoints return `obsidian://` URIs and do not open applications server-side.
- External secrets remain backend-only. The browser receives only local dev
  config from the allowlisted browser-config endpoint.

## Open Links

Open the vault:

```text
obsidian://open?vault=FounderOS%20Knowledge%20Vault
```

Open a specific note:

```text
obsidian://open?vault=FounderOS%20Knowledge%20Vault&file=Projects%2FProject%20Alpha
```
