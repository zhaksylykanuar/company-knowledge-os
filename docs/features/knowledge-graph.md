# Knowledge Graph Core

Foundation of the agent-driven second-opinion platform: every UI block
is a query over an evidence-backed entity graph that agents populate
from company sources. Humans only confirm uncertain facts and set goals.

## Ontology

Entity types (`app/services/knowledge_graph.py`): `project`,
`jira_project`, `repository`, `person`, `client`, `deal`, `meeting`,
`decision`, `risk`, `task`, `hypothesis`.

Relations: `belongs_to`, `works_on`, `employed_by`, `mentions`,
`decided_in`, `affects`, `supports`, `refutes`, `next_step_of`.
Every link carries `evidence_refs` and `confidence`.

## Agents (deterministic, idempotent)

- Graph lift (`graph_lift.py`): people from Jira assignees and GitHub
  PR authors become `person` nodes with `works_on` links; extracted
  decisions/risks/tasks become graph nodes with project links via alias
  resolution. Likely-same people across sources are NOT merged
  silently — the agent files a `merge_person` proposal.
- Metric collector (`metric_collector.py`): one point per day per
  series into `metric_snapshots` (`jira.open/stale/overdue/done`,
  `code.merged_prs/commits_7d` per project; `knowledge.*` and
  `activity.events` global). Real time series for the UI — no
  hand-entered numbers.

Run locally:

```bash
uv run python scripts/run_graph_agents.py --confirm-run "RUN GRAPH AGENTS"
```

## Approval queue

`agent_proposals` table + `app/services/agent_proposals.py`. Anything
an agent infers below its confidence threshold becomes a pending
proposal (`pending -> accepted/rejected -> applied`). Accepting only
flips status; the owning agent applies accepted proposals on its next
run. This is the human-approval boundary required by CLAUDE.md.

## Second opinion foundation (stage 1.5)

- Identity layer (`entity_identity.py`): `entity_source_accounts` tie
  external accounts to entities; cross-script merge matching (Cyrillic
  display name vs Latin GitHub login) files `entity_merge_proposal`s;
  accepted merges set `canonical_entity_id`/`merge_status` on the
  merged node, repoint links, copy aliases. `resolve_canonical()` for
  read models.
- Second opinion findings (`second_opinion.py` +
  `second_opinion_findings`): declared-vs-observed conflicts as
  first-class rows with taxonomy (`execution_mismatch`, `focus_drift`,
  `stale_claim`, `evidence_contradiction`, `ownership_gap`,
  `communication_silence`, `delivery_risk`, `validation_gap`),
  lifecycle open/accepted/dismissed/resolved, `visibility_scope`.
  Scanner projects persisted status snapshots into findings.
- Data availability (`data_availability.py`): formal widget data state
  (`no_data/collecting/insufficient/ready/stale`) with honest Russian
  messages — the UI never draws a number without checking it.
- Explainable confidence (`confidence.py`): every score ships with
  factors (evidence_count, source_quality, freshness,
  cross_source_match, contradiction_strength) and a human hint.
- Proposals extended: `dedupe_key`, `source_snapshot`,
  `confidence_factors`, `decision_reason`, `applied_at`, `expires_at`,
  `reversible`.
- Visibility scopes (`visibility.py`): founder / team / investor
  hierarchy plus declared source permissions and redaction rules.

## Planned next

UI: inbox for proposals, knowledge tree (constellation view), second
opinion feed. Agents: meeting agent (transcripts), email-thread agent
(communication_silence findings), deal agent, hypothesis agent
(validation_gap), graph gardener.
