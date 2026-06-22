# Architecture

## Status

- FastAPI backend: implemented
- Raw storage + Postgres source of truth: implemented
- Obsidian export-only model: implemented
- Local founder UI / Company Brain read models: implemented, protected, and
  read-only by default
- Source Control orchestration: implemented for guarded request lifecycles;
  live provider execution remains opt-in and acknowledged
- Gmail/Drive/Jira/GitHub ingestion: partial; compatibility backfill/sync
  surfaces now create Source Control requests instead of directly calling
  providers or persisting provider payloads
- Telegram founder bot: operator-launched long polling exists behind live
  provider acknowledgement; production webhook/scheduler behavior is planned
- End-to-end scheduled delivery: planned

## System Shape

FounderOS is a Python/FastAPI backend for evidence-backed company knowledge and decisions.

Current pipeline:

```text
manual text / local discovery / guarded Source Control requests
-> raw storage + Postgres
-> source_documents + document_chunks and/or normalized source_events
-> extraction / deterministic scoring / attention triage
-> evidence graph + status read models + Company Brain previews
-> founder UI / Telegram bot views / Obsidian export
```

Target pipeline:

```text
All external sources
-> Source Control request + provider guard + receipt/audit trail
-> raw storage + Postgres
-> unified normalized source-event contract
-> evidence-backed extraction and graph/status agents
-> FounderAnswer / Company Brain / digest read models
-> human approval gate
-> audited write outbox for any Jira/GitHub/Telegram action
```

## Source Of Truth

- Raw storage + Postgres are the source of truth.
- Obsidian is export-only.
- Generated vault files must not be treated as authoritative data.

## Safety Model

- Every extracted task/risk/decision must have `evidence_refs`.
- LLM outputs used in pipelines must be strict JSON.
- LLM output must be validated before persistence.
- If evidence is missing, return `null`, an empty array, or `insufficient evidence`.
- LLM must not directly mutate production data.

## API Boundary

Endpoint-level auth is implemented for selected protected API routers. Write
approval enforcement exists as a guard for future external write call sites.
Rate limiting and webhook signature validation remain planned because public
exposure and webhook routes are not implemented yet.

GET/read-model routes must remain side-effect free unless an endpoint explicitly
declares snapshot or audit persistence. Derived history such as project status
snapshots belongs behind an operator/bot/command path, not behind ordinary UI
reads.

## Modernization Direction

- Keep Source Control as the only production path for Jira/GitHub/Gmail/Drive
  provider activity; compatibility CLI/API surfaces should stay thin Source
  Control request wrappers.
- Keep Company Brain and repo audit computed from saved evidence with visible
  provenance labels (`computed`, `preview`, `source discovery`).
- Use agent/orchestration frameworks only where they buy durable state,
  approval handoff, tool governance, or observability. The default remains
  small deterministic services with strict JSON, validation, and
  `evidence_refs`.
- Treat live providers, LLM execution, DB writes, Obsidian sync, and outbound
  delivery as separate gates with separate approvals.
