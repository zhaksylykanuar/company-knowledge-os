# Feature: Source Events

## Status

- `source_events` table: implemented
- IngestedEvent -> SourceEvent normalization: implemented
- Integration source registry contracts: implemented
- SourceEvent read model: implemented as a service-level projection
- GitHub/Jira/Drive activity normalization: implemented as pure mappings

## Current Behavior

- Connector payloads are validated against source registry contracts.
- Valid payloads can be persisted as `ingested_events`.
- `ingested_events` can be normalized into `source_events`.
- Source events preserve raw refs, trace metadata, and evidence refs.
- Existing SourceEvent rows can be projected into a deterministic read model for internal services.
- The read model exposes normalized identifiers, event time, title/summary, raw refs, trace/correlation IDs, evidence refs, and a whitelisted payload subset when payload is supplied.
- GitHub pull request, Jira issue, and Drive document source-event-like inputs
  can be projected into `NormalizedActivityItem` objects for future attention
  triage. These mappings are in-memory and do not call live source APIs,
  providers, ingestion, or persistence.
- The source activity digest collapses repeated visible source events by source
  system, object type, object id, and event type. Normal rendered output shows
  one item with a short evidence count and a `Seen N times` note when repeated.
  Mock/example events are hidden from production activity and counted in a
  data-quality note.
- Drive/Gmail emitted ingestion event names are registry-compatible.
- New non-duplicate Drive/Gmail backfill events are normalized into SourceEvent rows when they satisfy registry contracts.
- Gmail message source events can be projected into `NormalizedActivityItem`
  rows as `source="gmail"` and `activity_type="email.received"` for explicit
  local attention triage windows.
- SourceEvent persistence from external inputs happens through the Source
  Control orchestrator/connector ingestion boundary or through already-protected
  local/manual paths. Public webhook ingestion still requires future API auth
  and webhook signature validation boundaries.

## Activity Normalization

- GitHub PR inputs include safe event identifiers, event type, title, summary,
  source URL, actor, repository, PR number, assignees, requested reviewers, and
  requested teams. Outputs use `source="github"`, activity types such as
  `pull_request.review_requested`, `pull_request.assigned`, and
  `pull_request.updated`, with safe PR refs and reviewer/team context.
- Jira issue inputs include safe event identifiers, issue key, title, summary,
  source URL, actor, assignee, project key, status, labels, and optional blocker
  information. Outputs use `source="jira"`, activity types such as
  `issue.assigned`, `issue.blocked`, and `issue.updated`, with Jira keys and
  people refs.
- Drive document inputs include safe event identifiers, document title/name,
  summary, source URL or web view link, actor, document ID, modification time,
  and optional project/topic hints. Outputs use `source="drive"` and
  `activity_type="document.changed"`, with document refs in `related_files`.
- `evidence_refs` are compact top-level refs only: source, source object ID,
  event type, optional source event ID, optional raw payload ref, and safe source
  URL or document identifiers. They must not include raw message bodies, raw
  document bodies, or full provider payloads.

## Invariants

- Source events are derived from raw ingested events.
- Connector event names must match registry contracts.
- SourceEvent IDs must not be confused with DocumentChunk IDs.
- Source event creation must be deterministic.
- Source event read projection must be deterministic and must not mutate source data.
- Contract-invalid events must fail before source event persistence.
- Projections must preserve `raw_object_ref` and evidence links internally.
- Normal operator digest output must show short evidence counts; raw refs are
  debug-only.

## Known Gaps

- No public SourceEvent query/read API is visible yet.
- Duplicate or legacy Drive/Gmail ingested events are not repaired into SourceEvent rows by backfill.
- Opt-in read-only GitHub/Jira Source Control connectors exist for operator-run
  polling. Public webhook handling, production schedulers, and external writes
  remain deferred.
- Live Drive webhook handling and production API polling are deferred.
- GitHub/Jira/Drive digest integration is deferred.
