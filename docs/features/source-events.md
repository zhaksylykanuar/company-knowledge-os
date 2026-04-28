# Feature: Source Events

## Status

- `source_events` table: implemented
- IngestedEvent -> SourceEvent normalization: implemented
- Integration source registry contracts: implemented
- SourceEvent read model: planned
- Development event projections: planned

## Current Behavior

- Connector payloads are validated against source registry contracts.
- Valid payloads can be persisted as `ingested_events`.
- `ingested_events` can be normalized into `source_events`.
- Source events preserve raw refs, trace metadata, and evidence refs.
- Drive/Gmail emitted ingestion event names are registry-compatible.

## Invariants

- Source events are derived from raw ingested events.
- Connector event names must match registry contracts.
- SourceEvent IDs must not be confused with DocumentChunk IDs.
- Source event creation must be deterministic.
- Contract-invalid events must fail before source event persistence.
- Projections must preserve `raw_object_ref` and evidence links.

## Known Gaps

- No public SourceEvent query/read API is visible yet.
- GitHub/Jira/Telegram real connectors are planned, not implemented.
- Development event projection DTOs are planned, not implemented.
