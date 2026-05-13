# Feature: Source Events

## Status

- `source_events` table: implemented
- IngestedEvent -> SourceEvent normalization: implemented
- Integration source registry contracts: implemented
- SourceEvent read model: implemented as a service-level projection
- Development event projections: planned

## Current Behavior

- Connector payloads are validated against source registry contracts.
- Valid payloads can be persisted as `ingested_events`.
- `ingested_events` can be normalized into `source_events`.
- Source events preserve raw refs, trace metadata, and evidence refs.
- Existing SourceEvent rows can be projected into a deterministic read model for internal services.
- The read model exposes normalized identifiers, event time, title/summary, raw refs, trace/correlation IDs, evidence refs, and a whitelisted payload subset when payload is supplied.
- The source activity digest collapses repeated visible source events by source
  system, object type, object id, and event type. Normal rendered output shows
  one item with a short evidence count and a `Seen N times` note when repeated.
  Mock/example events are hidden from production activity and counted in a
  data-quality note.
- Drive/Gmail emitted ingestion event names are registry-compatible.
- New non-duplicate Drive/Gmail backfill events are normalized into SourceEvent rows when they satisfy registry contracts.
- SourceEvent persistence from external inputs requires future API auth and webhook signature validation boundaries.

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
- GitHub/Jira/Telegram real connectors are planned, not implemented.
- Development event projection DTOs are planned, not implemented.
