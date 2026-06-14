# Source Connectors

FounderOS source connectors turn approved source run requests into sanitized
source events and normalized activity. Raw storage and Postgres stay the source
of truth; connectors are read-only unless a future approved flow explicitly
adds a write path.

## Supported Sources

- Jira: read-only readiness, test, sync, and backfill contract.
- GitHub: read-only readiness, test, sync, and backfill contract.
- Gmail / Email: local stored email records are supported; OAuth/provider
  reads require configured credentials and explicit operator execution.
- Meetings: internal/local documents and meeting-like records.
- Declarations: internal declaration records.
- Manual inputs: internal/manual source documents.
- Generated evidence: local findings and proposals.
- Share packs / curated outputs: local share-pack lifecycle records.

## Configuration

Connector readiness returns only configured, missing, or masked status. It must
never return credential values, token lengths, token prefixes, OAuth payloads,
or raw provider configuration.

Common setup fields:

- Jira: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`.
- GitHub: `GITHUB_TOKEN`.
- Gmail: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, plus OAuth/local email state
  depending on the deployment.

Missing credentials produce `missing_config` with variable names only. The
connector result, audit payload, API response, UI, and logs must not include raw
secret values.

## Real Read-only Connector Execution (opt-in)

Real Jira/GitHub reads are **disabled by default** and are always read-only.

Enable them explicitly in the backend env (never sent to the browser):

```bash
FOUNDEROS_ENABLE_REAL_CONNECTORS=true
FOUNDEROS_CONNECTOR_NETWORK_TIMEOUT_SECONDS=10
FOUNDEROS_CONNECTOR_SYNC_LIMIT=50
FOUNDEROS_CONNECTOR_BACKFILL_LIMIT=100
```

When `FOUNDEROS_ENABLE_REAL_CONNECTORS=false` (the default), the real Jira/GitHub
clients never make a network call; configured external requests run, but the run
result is `skipped` with mode `real_connectors_disabled`. Internal and local
sources keep working regardless.

Required backend env vars:

- Jira: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` (read-only API token).
- GitHub: `GITHUB_TOKEN` (read-only), plus optional `GITHUB_REPOS`
  (`owner/repo,owner/other`) and `GITHUB_ORG` to scope reads.
- Gmail: stays **local-only** in this release. If OAuth is not configured the
  diagnostics report `local_only` / `oauth_not_configured` and never a fake
  `connected` state. Already-ingested local email threads are read without any
  network call; raw email bodies never leave backend storage.

Read-only guarantee: connectors only issue HTTP GET reads. No connector writes
to Jira, GitHub, or Gmail, and no email is ever sent.

### Enable, test, and sync from the UI

1. Set the env vars above and restart the backend
   (`uv run python scripts/start_local.py`).
2. Open `http://127.0.0.1:8765/ui` → **Sources / Data Control**.
3. For Jira or GitHub: **Test connection** (records a founder request).
4. **Sync now** to record a sync request; **Backfill** for a bounded history.
5. Execute the queued requests with the operator script:

```bash
uv run python scripts/run_source_requests.py --confirm-run "RUN SOURCE REQUESTS"
```

A connector only shows `connected` after a real `test`/`sync` succeeds — never
from the presence of env vars alone. Failures are recorded as `degraded`/`error`
with a sanitized message (no secret values).

### Testing stance

Tests use fake connector clients (or local/noop adapters) and never call a real
Jira, GitHub, Gmail, or other live API. Secret values never reach the browser,
API responses, audit payloads, source events, or the Obsidian vault — only
environment-variable names and masked statuses are exposed.

## Safe Live Connector Setup (scopes & limits)

Before any real Jira/GitHub read, an explicit scope is required so a whole org
can never be read by accident. `test_connection` is exempt (it is only a
read-only auth check); `sync`, `preview_sync`, and `backfill` require a scope.

1. Keep real connectors disabled by default
   (`FOUNDEROS_ENABLE_REAL_CONNECTORS=false`).
2. Add credentials (backend env only).
3. Add explicit scopes (names only — never secrets):

```bash
FOUNDEROS_JIRA_PROJECT_KEYS=QS
FOUNDEROS_GITHUB_REPOS=owner/repo
```

4. Enable real connectors:

```bash
FOUNDEROS_ENABLE_REAL_CONNECTORS=true
```

5. Restart the backend.
6. **Test connection** (works without a scope).
7. **Preview sync** — counts and shows sample sanitized titles; writes no
   source events.
8. **Sync** — only runs when a scope is configured.
9. Run the evidence pipeline.
10. Sync Obsidian.

Limits are always applied to live reads:

```bash
FOUNDEROS_CONNECTOR_SYNC_LIMIT=50
FOUNDEROS_CONNECTOR_BACKFILL_LIMIT=100
FOUNDEROS_CONNECTOR_BACKFILL_MAX_DAYS=30
```

Guarantees:

- No writes to Jira/GitHub/Gmail; no email is sent.
- No full-org scan: sync/backfill are blocked with `blocked_missing_scope` until
  an explicit scope is set; a wildcard/`*` scope is flagged as too broad.
- Limits bound every live read.
- Tests use fakes and never hit a real external API.
- Secrets stay backend-side and never reach the browser, API, audit, source
  events, or the Obsidian vault — only scope/env-var names and statuses.

## Local Connector Pilot

The local pilot drives the whole connector E2E chain with one command:

  diagnostics → test → sync → evidence pipeline → Obsidian dry-run

1. Configure the local env override with the backend env vars (names above).
   Restart the backend.
2. Keep `FOUNDEROS_ENABLE_REAL_CONNECTORS=false` for a dry, safe run first. With
   it false, no external network call is made and the pilot just records the
   next steps; internal/local sources still run.
3. Run the pilot:

```bash
uv run python scripts/run_local_connector_pilot.py \
  --confirm-run "RUN LOCAL CONNECTOR PILOT"
```

4. Enable real connectors only when ready:

```bash
FOUNDEROS_ENABLE_REAL_CONNECTORS=true
```

5. Run test/sync through the Sources UI (Test connection → Sync now) or re-run
   the pilot. Execute queued requests with:

```bash
uv run python scripts/run_source_requests.py --confirm-run "RUN SOURCE REQUESTS"
```

6. Process evidence into the graph:

```bash
uv run python scripts/run_evidence_pipeline.py --confirm-run "RUN EVIDENCE PIPELINE"
```

7. Sync the Obsidian vault (the pilot only previews it unless `--sync-obsidian`
   is passed):

```bash
uv run python scripts/sync_obsidian_vault.py --confirm-run "SYNC OBSIDIAN VAULT"
```

Guarantees:

- No writes to Jira, GitHub, or Gmail; no email is sent.
- Tests use fakes and never hit a real external API.
- Secrets stay backend-side and never reach the browser, audit, source events,
  or the Obsidian vault.
- A connector is shown `connected` only after a successful test or sync — never
  from env presence. The UI shows `requested`/`queued` versus `succeeded`
  honestly, and disabled real connectors skip with `real_connectors_disabled`.
- The pilot performs no real Obsidian write without `--sync-obsidian`.

## Safe Execution

Source actions are requested through Source Control Center first. The operator
execution command is:

```bash
uv run python scripts/run_source_requests.py --confirm-run "RUN SOURCE REQUESTS"
```

The script processes queued source run requests through the orchestrator. It
does not push code and does not require credentials for noop or local internal
sources. External adapters must remain read-only and behind explicit
configuration, unpaused source state, a queued request, and the confirmation
flag.

## Ingestion Contract

Adapters return `ConnectorEvent` DTOs. Each event carries:

- source type, object type, event type, external ID, and occurred time;
- title/summary/actor/url where available;
- sanitized payload, never raw bodies or tokens;
- `raw_object_ref` as a pointer only, not raw content;
- deterministic content hash;
- run/correlation IDs.

Ingestion upserts events idempotently into `ingested_events` and `source_events`.
Repeated sync with the same `source_type`, `external_id`, and content hash is a
duplicate. Changed content creates a deterministic new event version through
the existing connector idempotency key.

## Normalization

Sync and backfill events are projected into `normalized_activity_items` when a
safe mapper exists. Unsupported or invalid source events are retained as source
events and reported as normalization issues; one bad event must not fail the
whole run.

`test_connection` never ingests events.

## Evidence Pipeline

After ingestion/normalization, the local evidence pipeline can lift normalized
activity into the Knowledge Graph, Second Opinion findings, and Inbox
proposals:

```bash
uv run python scripts/run_evidence_pipeline.py --confirm-run "RUN EVIDENCE PIPELINE"
```

The pipeline is local-only and provider-free. It reads
`normalized_activity_items`, requires evidence-backed `source_event_id`
lineage before asserting graph edges or findings, and writes sanitized
`agent_run_logs` / `audit_logs` summaries. Low-confidence relationships become
Inbox proposals instead of graph assertions. Re-running the pipeline is
idempotent: existing nodes, links, findings, and proposals are updated or left
unchanged by stable keys.

Source run details, Source Control Center, Data Quality, Command Center,
Knowledge Tree, and Evidence Trail surface the resulting graph/finding/proposal
counts and run lineage. Browser/API payloads expose only sanitized summaries;
raw provider bodies and external tokens never leave backend storage.

## Testing Without Providers

Tests use fake connector adapters or local/noop adapters. They must not call
Jira, GitHub, Gmail, OpenAI, or any live provider. Mock adapters should return
sanitized `ConnectorEvent` objects and assert that result summaries, audit
payloads, source event payloads, and API responses do not leak secrets.

## Browser/API Safety

The browser receives source health, readiness, run summaries, and sanitized
event metadata only. It must never receive external tokens, OAuth responses, raw
email bodies, raw provider payloads, or hidden credential values.
