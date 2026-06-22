# Knowledge Graph Core

Foundation of the agent-driven second-opinion platform: every UI block
is a query over an evidence-backed entity graph that agents populate
from company sources. Humans only confirm uncertain facts and set goals.

## Current Implementation Status

- Implemented foundations: graph entities/links, evidence refs, deterministic
  lift agents, metric snapshots, proposal queue, identity/merge proposals,
  second-opinion findings, data availability, confidence factors, and guarded
  read-model endpoints.
- Preview/read-model surfaces: decision center, second-opinion feed, task/team
  product views, and Action Center are bounded UI/read-model slices over stored
  evidence.
- Target direction: cron-driven agents, full multi-view founder/team/investor
  surfaces, deal-agent enrichment, and broader autonomous graph maintenance are
  not the current runtime contract.

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

## Stage 2: decision center UI

- Inbox (`/v1/inbox`, UI section): pending proposals with
  product-facing fields (`proposal_type`, `reviewer_id`), confidence
  hint, "why" (source_snapshot) and consequences of accepting;
  Accept/Reject applies merges immediately. Disputed graph links
  (confidence < 0.7) are reviewed here too (confirm/remove).
- Second opinion feed (`/v1/founder/second-opinion`): central conflict
  feed with declared vs observed, severity, explainable confidence,
  evidence, suggested action and lifecycle buttons
  (accept/dismiss/resolve/snooze/note). Severity ordering in SQL;
  snoozed findings are hidden until due.
- Knowledge tree (`/v1/graph/tree`): constellation canvas — node glow =
  freshness, link width/alpha = confidence, dashed = disputed; merged
  nodes fold into their canonical survivor; node click shows details,
  links and source accounts.
- Scanner hardening: `scan_second_opinion` rebuilds project snapshots
  itself with a real clock (persisted snapshots may carry a synthetic
  test clock) and auto-resolves findings it no longer observes
  (reconciliation), so the feed never accumulates orphans.

## Stage 3: trust layer + source agents

Trust layer (built before new UI so second opinion is provable):

- Evidence drill-down (`evidence_trail.py`, `GET …/{finding_key}/trail`):
  resolves a finding's evidence refs back through the verifiable chain
  source event → normalized event → graph node → finding → inbox
  decision. Returns reasoning (the rule), confidence explanation with
  factors, evidence timeline (with raw_object_ref), related graph nodes,
  suggested action and decision history. UI renders it as a panel.
- Audit trail (`inbox_audit.py`): every human decision (proposal
  accept/reject, link confirm/remove, finding status/snooze/note) writes
  an `audit_logs` row with actor, previous_state/next_state and
  reversibility. `decision_history` in the trail is sourced from it.
- Visibility enforcement (`visibility.py` `redact_finding` + API `view`
  param): audience-based, not hierarchical. Founder sees all; team sees
  only team-scoped working findings (notes + source_refs stripped);
  investor sees only investor-curated findings reduced to safe fields.
  Trail, inbox and graph tree are founder-only / non-investor by API
  guard. Execution/stale/ownership findings are team-scoped; email
  communication-silence is founder-scoped.

Source agents (deterministic, idempotent, evidence-strict):

- Meeting agent (`meeting_agent.py`): documents with marker lines
  (Decision:/Action:/Risk:/…) become `meeting` nodes via the existing
  meeting extractor, with decisions (`decided_in`), action items (tasks
  with owners/deadlines, `next_step_of`) and risks (`affects` project).
  Short hashed ids keep link ids under the 120-char column limit.
- Email-thread agent (`email_thread_agent.py`): reads persisted
  `email_thread_states` (rebuilt from stored gmail, no provider calls)
  and emits `communication_silence` findings — inbound waiting for my
  reply ≥3d (strong), or external silence ≥7d (weak → inbox proposal).
- Declaration agents (`declaration_agents.py` + `founder_declarations`):
  the founder declares focus and hypotheses (server-stored, UI-edited).
  Hypothesis agent emits `validation_gap` (declared validated, no
  supporting evidence) and `evidence_contradiction` (stored risks
  contradict, with `refutes` links). Focus-drift agent emits
  `focus_drift` when 7-day activity diverges from the declared focus.

Generator trust rules (`emit_finding_or_proposal`): no evidence → no
finding; confidence below 0.45 → inbox proposal instead of a finding;
all generators idempotent; a resolved finding only reopens on genuinely
new evidence (different observed state or evidence refs).

## Stage 4: sales signals, gardener, availability UI, explorer, command center

Run-summary hardening (`agent_run_logs` + `last_update_reason`):
`upsert_finding` now distinguishes `updated_from_new_evidence` from
`updated_from_clock_recalculation` (same evidence, only the observed age
moved). Each finding/metric stores a `last_update_reason`
(`new_evidence` / `stale_window_recalculation` / `visibility_rescope` /
`auto_resolved_no_longer_observed` / `manual_decision` /
`source_backfill`). The pipeline writes one `agent_run_logs` row per
agent per run with the standardized buckets, run timestamps,
`agent_version` and `input_watermark` — so a day-rollover never reads as
a new discovery. `GET /v1/founder/agent-runs` exposes the log.

- Sales signal agent (`sales_signal_agent.py`): builds the sales graph
  from email threads — companies become `client` nodes, external
  participants `person` contacts `employed_by` them, each account a
  `deal` *signal* entity `belongs_to` the company. No finance ever:
  `deal` carries warmth, never an amount. Free-mail domains are skipped.
  A previously two-way-active account gone silent past a threshold is a
  founder-scoped `communication_silence` finding (weak → inbox proposal).
- Graph gardener (`graph_gardener.py`): hygiene checks (orphan nodes,
  people without source evidence, edges without evidence, duplicate
  accounts, findings that lost evidence) that file inbox proposals only
  — it never deletes or merges on its own. Stable dedupe keys mean a
  rejected cleanup will not resurface.
- Data-availability chips (UI): every metric/feed widget (Second
  Opinion, Inbox, Knowledge Tree, Team, Tasks, Metrics, Activity) shows
  its `data_availability` state (ready / collecting / insufficient /
  stale / no_data) — no number is painted without a backing series.
- Source / evidence explorer (`evidence_explorer.py`,
  `/v1/source-events`): browse the sanitized source events behind the
  graph (never raw bodies) with normalized events, linked nodes and the
  findings generated from each. Founder sees `raw_object_ref`; team sees
  working fields only; investor is blocked. The trail timeline links
  into it.
- Command center read model (`command_center.py`,
  `/v1/founder/command-center`): startup health (no finance),
  second-opinion summary + top conflicts, focus vs activity, risks,
  stale work, real team load (open Jira issues per assignee), knowledge
  freshness, data-availability summary and next actions. Read model
  only — the final Command Center UI comes later.

## Stage 5: Command Center UI, Sales Signals UI, gardener inbox

Traceability hardening: a per-run `run_id` (contextvar set by the
pipeline) stamps `second_opinion_findings.last_run_id` and
`agent_proposals.run_id`, so the evidence trail now answers not just
"what evidence" but "which agent run produced this" (`produced_by_run`
resolves the matching `agent_run_logs` row with agent_version and
watermark). Unassigned work is an operational bucket in the command
center team block (`unassigned_work_count` / `stale_unassigned_work` /
`high_priority_unassigned` + suggested action), never a fake person.

- Command Center UI (`/v1/founder/command-center`): premium founder
  dashboard — health ring, operational substates (second-opinion
  pressure, high severity, stale work, team load, unassigned, data
  readiness), focus week with focus-vs-activity drift callout, top
  conflicts ("what AI sees differently") with trail buttons, threat
  board, team stamina bars + unassigned bucket, knowledge freshness,
  data-availability summary, business map. No finance.
- Sales Signals UI (`/v1/founder/sales-signals`, `sales_view.py`):
  account cards with warmth, contacts, and relationship signals as
  "what AI sees differently" blocks — no amounts, no revenue, no money
  pipeline. Signals open to the evidence trail / source explorer.
- Graph gardener inbox group: `build_inbox` splits `identity_proposals`
  from `gardener_proposals`; each gardener card shows what is wrong,
  why it matters, evidence, consequences of Accept and the note that a
  Reject will not resurface without new evidence.
- "What AI sees differently" blocks reused across Command Center,
  Product, Team, Tasks, Metrics and Sales — fed by the open findings
  index, shown only where relevant findings exist (no data, no block).
- Game-like infographic: health rings, threat board, stamina bars,
  quest log, graph constellation, evidence/confidence chips, data
  availability chips — all backed by real series.

## Stage 6: Execution OS + lineage/gardener hardening

Full run_id lineage now spans source event -> normalized event -> graph
node/edge -> finding -> proposal -> audit decision: `created_by_run_id`
on source_events / entities / entity_links, `run_id` on
normalized_activity_items, `agent_run_id` on audit_logs (threaded from
the decided-on item). The evidence trail surfaces `created_by_run_id`
per chain element plus a `lineage_run_ids` summary.

Graph gardener apply flow (`gardener_apply.py`): accepting a gardener
proposal applies a safe action and is audited, never a silent delete —
orphan/no-evidence node -> archived (hidden, skipped by future runs);
edge-without-evidence -> removed with a recreatable snapshot;
duplicate-account -> files an explicit `entity_merge_proposal`;
finding-without-evidence -> suppressed. Reject keeps the stable dedupe
key; the pipeline batch-applies accepted proposals.

Execution OS read models (founder-scoped; investor blocked):

- Execution / Quest Log (`execution_view.py`, `/v1/founder/execution`):
  real Jira issues bucketed into main quest (the declared focus), side
  / blocked / stale / ownerless / overdue quests, with per-project
  done/total health rings (only when total > 0 — no fake progress) and
  the findings attached to each issue. Task detail
  (`/v1/founder/execution/tasks/{key}`) assembles source refs, related
  nodes, related findings, status history (with run ids) and next
  action.
- Team load (`team_view.py`, `/v1/founder/team-load`): operational load
  map — open/stale/overdue per person with a suggested operational
  action when overloaded; never a productivity score or ranking;
  unassigned work is a separate bucket; ownership_gap findings listed.
- Product system (`product_view.py`, `/v1/founder/product`): hypotheses
  with declared status vs supporting evidence (knowledge mentions) and
  contradicting evidence (stored risks), the validation_gap /
  evidence_contradiction findings, and a flagged state when a declared
  "validated" lacks support. No invented roadmap dates.
- Action Center (`action_center.py`, `/v1/founder/action-center`): one
  ranked next-actions layer aggregating second-opinion findings,
  gardener proposals, stale/ownerless/blocked/overdue tasks, sales
  relationship signals and data-availability problems. Read-only — each
  action's CTA routes to an existing decision endpoint; AI proposes,
  the human confirms.

UI: Tasks rebuilt as the quest log with health rings, quest cards and a
task detail drawer; Team rebuilt as the stamina/load map with the
unassigned bucket; Product gains the hypothesis validation map; a new
Action Center section. All reuse the shared visual language (health
rings, quest cards, stamina bars, evidence/confidence/availability
chips, trail and source-explorer buttons) and the "what AI sees
differently" blocks.

## Planned next

Cron-driven agent runs, multi-view (team/investor) UI surfaces, deal-
agent enrichment from meetings/tasks.
