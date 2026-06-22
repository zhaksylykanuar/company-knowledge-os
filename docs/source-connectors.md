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
- Drive: local/noop Source Control request path is supported; live Google Drive
  reads are not wired into the default connector registry yet.
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
- Gmail/Drive: stay **local-only/noop through Source Control** in this release.
  Low-level Google wrappers and compatibility request routes exist, but the
  default Source Control registry does not wire real Google clients yet.
  Diagnostics report `local_only`, `noop`, or `oauth_not_configured` rather
  than a fake `connected` state. Already-ingested local email/file records are
  read without any network call; raw email bodies and document contents never
  leave backend storage.

Read-only guarantee: live connectors only issue HTTP GET reads. No connector
writes to Jira, GitHub, Gmail, or Drive, and no email is ever sent.

### Enable, test, and sync from the UI

1. Set the env vars above and restart the backend
   (`uv run python scripts/start_local.py`).
2. Open `http://127.0.0.1:8765/ui` → **Sources / Data Control**.
3. For Jira or GitHub: **Test connection** (records a founder request).
4. **Preview sync** first to record a no-write preview request; after reviewing
   the receipt/scope, use **Sync now** or **Backfill** for bounded history.
5. Execute the queued requests with the operator script:

```bash
uv run python scripts/run_source_requests.py \
  --confirm-run "RUN SOURCE REQUESTS" \
  --allow-live-provider-execution \
  --acknowledge-live-provider-risk "ALLOW LIVE PROVIDER EXECUTION"
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

Before any real Jira/GitHub read, the operator must provide the live-provider
acknowledgement phrase at execution time. `test_connection` is exempt only from
scope (it is a read-only auth check); `sync`, `preview_sync`, and `backfill`
require both the live-provider ack and an explicit scope so a whole org can
never be read by accident.

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
6. **Test connection** (works without a scope, but the operator runner still
   needs live-provider ack to call the provider).
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
  an explicit scope is set, and with `blocked_scope_too_broad` when the scope is
  a wildcard/`*`/`all`.
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

5. Run test/preview/sync through the Sources UI (Test connection → Preview
   sync → Sync now) or re-run the pilot. Execute queued requests with:

```bash
uv run python scripts/run_source_requests.py \
  --confirm-run "RUN SOURCE REQUESTS" \
  --allow-live-provider-execution \
  --acknowledge-live-provider-risk "ALLOW LIVE PROVIDER EXECUTION"
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

## Connector Run Receipts and Watermarks

Every executed connector request writes a sanitized receipt in the source run
read-model. A receipt answers exactly what happened:

- request, source, action, run/correlation IDs;
- scope snapshot and limits applied;
- pages/records/events seen;
- events ingested, duplicates skipped, normalized events and errors;
- watermarks before/after and the reason the watermark did or did not move;
- sanitized warnings/errors;
- content hash and `secret_scan_status=passed`.

Inspect one receipt through the UI Source Run Detail drawer or API:

```bash
GET /v1/founder/source-runs/{request_id}/receipt
```

`configured` is not the same as `connected`: a source is connected only after a
successful read-only test/sync, not from env vars alone.

Watermark rules:

- `test_connection` never updates the sync watermark.
- `preview_sync` writes no `source_events` and never updates the watermark.
- failed, blocked, missing-config, missing-scope, real-disabled and skipped
  runs never update the normal sync watermark.
- `sync` updates the normal watermark only on success or partial success with a
  valid output watermark.
- `backfill` never overwrites the normal sync watermark; for live-scoped Jira
  and GitHub reads it must include a bounded `since` window within
  `FOUNDEROS_CONNECTOR_BACKFILL_MAX_DAYS`, then records that window in the
  receipt/result summary.
- completed requests do not run twice.

Pagination and limits:

- live reads must respect `FOUNDEROS_CONNECTOR_SYNC_LIMIT`,
  `FOUNDEROS_CONNECTOR_BACKFILL_LIMIT`, and
  `FOUNDEROS_CONNECTOR_BACKFILL_MAX_DAYS`;
- receipts record `pages_read`, `limit_applied`, `stopped_reason`,
  `retry_after_seconds` and `rate_limit_remaining` when available;
- rate-limit/timeout/partial success are sanitized reasons, not raw stack
  traces.

Retry policy:

- failed/blocked/skipped/partial runs can create a safe retry request;
- a retry does not execute externally until the operator runs the source
  request script;
- retry keeps scope/paused/real-disabled gates intact;
- retry output is idempotent by request key.

Operator sequence:

```bash
uv run python scripts/run_local_connector_pilot.py \
  --confirm-run "RUN LOCAL CONNECTOR PILOT" --preview-only

uv run python scripts/run_source_requests.py \
  --confirm-run "RUN SOURCE REQUESTS" \
  --allow-live-provider-execution \
  --acknowledge-live-provider-risk "ALLOW LIVE PROVIDER EXECUTION"

uv run python scripts/run_evidence_pipeline.py --confirm-run "RUN EVIDENCE PIPELINE"

uv run python scripts/sync_obsidian_vault.py --confirm-run "SYNC OBSIDIAN VAULT"
```

## Safe Execution

Source actions are requested through Source Control Center first. The operator
execution command is:

```bash
uv run python scripts/run_source_requests.py \
  --confirm-run "RUN SOURCE REQUESTS" \
  --allow-live-provider-execution \
  --acknowledge-live-provider-risk "ALLOW LIVE PROVIDER EXECUTION"
```

The script processes queued source run requests through the orchestrator. It
does not push code and does not require credentials for noop or local internal
sources. External adapters must remain read-only and behind explicit
configuration, unpaused source state, a queued request, the run confirmation
flag, and the live-provider acknowledgement phrase.

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
