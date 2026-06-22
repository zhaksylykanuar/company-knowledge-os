# Feature Contract: Company Brain

## Status

- Implemented as protected read-only founder API endpoints under
  `/v1/founder/company-brain/*`.
- Rendered in the local founder UI.
- Built from local Stage 22 preview files plus the computed repository audit.
- Preview/computed only: no DB writes, no external calls, no raw email output,
  and no implied founder confirmation for inferred ownership.

## Source Inputs

- Stage 22 preview files in the local workspace.
- Local GitHub discovery snapshots under `.local/discovery/github/*/raw/repos.json`.
- Static repository catalog metadata as seed/planning context only.
- Repository source inventory read model:
  `SourceEvent/Postgres -> discovery snapshot -> legacy seed catalog`.

Company Brain must prefer computed read models over hand-authored cards. When a
fact comes from a preview file, local discovery snapshot, or computed audit, the
payload and UI should make that provenance visible with labels such as
`preview`, `computed`, or `source discovery`.

Repository counts must distinguish the current operational inventory from the
legacy seed. `operational_repo_count` comes from stored SourceEvents when
available, otherwise from the latest saved discovery snapshot, and only falls
back to the static 19-entry catalog when no observed inventory exists.
`legacy_seed_repo_count` remains available for reconciliation and migration
planning, but must not be presented as current GitHub truth.

For static local preview files, the API must also expose artifact provenance:
relative file names, availability status, latest artifact mtime as `generated_at`,
artifact age, content hashes, and a combined snapshot ID. The UI renders this as
a compact source/as-of/snapshot strip with technical details collapsed by
default. This prevents Stage 22 preview content from looking like a fresh
production graph.

For the computed repo audit, the saved discovery file is also part of the
contract: `source_snapshot.modified_at`, `snapshot_age_seconds`,
`as_of_source`, and `freshness_status` must be returned and rendered. A stale
local discovery snapshot must be labelled as stale/local rather than just
green `computed` output.

## API Surface

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/founder/company-brain/preview` | full bundle |
| `GET /v1/founder/company-brain/overview` | high-level counts and guardrails |
| `GET /v1/founder/company-brain/people` | people/roles/ownership preview |
| `GET /v1/founder/company-brain/second-opinion` | second-opinion feed |
| `GET /v1/founder/company-brain/unresolved-questions` | founder confirmation gaps |
| `GET /v1/founder/company-brain/repo-audit` | computed repo audit from saved discovery |

## Guardrails

- Repos are components/evidence, not Jira projects. Never infer
  `1 repo = 1 Jira project`.
- Keep inferred ownership provisional until founder confirmation.
- Never expose raw email-shaped strings.
- Missing evidence returns empty arrays, `null`, or explicit insufficient
  evidence, not invented facts.
- The repo audit reads saved snapshots only; it does not call GitHub live.

## Target Direction

Company Brain should become the founder-facing read model over the evidence
graph: people, areas, repos, risks, decisions, ownership gaps, and second
opinions. The target state is still evidence-first: Source Control gathers and
normalizes source events, graph/status agents compute candidates, humans approve
or correct sensitive facts, and Company Brain presents the current best picture
with provenance instead of pretending that previews are final truth.
