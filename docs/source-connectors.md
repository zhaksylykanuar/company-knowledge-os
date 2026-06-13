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

## Testing Without Providers

Tests use fake connector adapters or local/noop adapters. They must not call
Jira, GitHub, Gmail, OpenAI, or any live provider. Mock adapters should return
sanitized `ConnectorEvent` objects and assert that result summaries, audit
payloads, source event payloads, and API responses do not leak secrets.

## Browser/API Safety

The browser receives source health, readiness, run summaries, and sanitized
event metadata only. It must never receive external tokens, OAuth responses, raw
email bodies, raw provider payloads, or hidden credential values.
