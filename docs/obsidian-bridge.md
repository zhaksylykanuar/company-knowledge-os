# Obsidian Native Bridge

FounderOS can mirror its evidence-backed knowledge graph into a real local
Obsidian vault. FounderOS remains the source of truth; Obsidian is the native
graph, backlinks, local graph, markdown notes, tags, properties, and search
surface.

The bridge never sends data to Obsidian Cloud and never writes outside the
configured local vault path.

## Setup

1. Install the Obsidian desktop app.
2. Create a local folder for the vault, or let FounderOS create it on first
   sync.
3. Add local settings to your untracked local env file:

```env
FOUNDEROS_ENABLE_OBSIDIAN_BRIDGE=true
FOUNDEROS_OBSIDIAN_VAULT_NAME=FounderOS Knowledge Vault
FOUNDEROS_OBSIDIAN_VAULT_PATH=/Users/<you>/Documents/FounderOS Knowledge Vault
FOUNDEROS_OBSIDIAN_SYNC_MODE=manual
```

4. Restart the backend after changing env.
5. Open `/ui` and go to Knowledge Tree.
6. Click Dry Run.
7. Click Sync Now.
8. Click Open Vault in Obsidian.
9. In Obsidian, use Graph View, Local Graph, Backlinks, Tags, and Search.

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

## Safety

- The bridge must be enabled explicitly.
- `FOUNDEROS_OBSIDIAN_VAULT_PATH` must be an absolute local path.
- Dry run never writes files.
- Real sync writes by atomic temp-file replace.
- Path traversal is rejected.
- Raw source payloads, raw email bodies, external tokens, local dev keys, and
  raw object refs are not written to markdown.
- Team/investor views cannot access the bridge endpoints.
- Open endpoints return `obsidian://` URIs and do not open applications server-side.

## Open Links

Open the vault:

```text
obsidian://open?vault=FounderOS%20Knowledge%20Vault
```

Open a specific note:

```text
obsidian://open?vault=FounderOS%20Knowledge%20Vault&file=Projects%2FProject%20Alpha
```
