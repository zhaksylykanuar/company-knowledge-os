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

## Planned next

UI: knowledge tree (constellation view), inbox for proposals, second
opinion feed (declared-vs-observed conflicts). Agents: meeting agent
(transcripts), email-thread agent, deal agent, cross-script person
merge candidates (Cyrillic vs Latin logins), graph gardener.
