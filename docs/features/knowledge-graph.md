# Knowledge Graph

## Current Implementation Status

- Implemented foundations include graph entities/links, evidence refs,
  deterministic lift helpers, identity/merge proposals, second-opinion
  findings, data availability, confidence helpers, and guarded read-model
  endpoints.
- Current graph surfaces are supporting read models over stored evidence. They
  are not the canonical execution plan for the GitHub-first MVP.
- Target direction remains post-MVP unless a scoped task explicitly pulls a
  graph slice into the current chunk.

## Current Contract

The graph must preserve evidence and provenance. It may support Company Brain,
second-opinion, local UI, and operator read models, but it must not silently
merge uncertain identities, invent ownership, or perform external writes.

## Archived Original

The large historical/target document was archived to
`../_archive/docs/features/knowledge-graph.md`. Keep it as traceability only;
the root master playbook and execution plan are the current source of truth.

## Boundaries

- Humans confirm uncertain facts.
- Evidence refs remain visible.
- Post-MVP graph expansion is parked in `../POST_MVP.md`.
