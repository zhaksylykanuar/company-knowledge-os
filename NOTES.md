# FounderOS Progress

## Done

### Foundation
- FastAPI backend
- Postgres + Redis via Docker Compose
- Alembic migrations
- audit logs
- secret scan script
- ruff/pytest health checks

### Evidence / source of truth
- raw payload is saved before processing
- source_documents and document_chunks are Postgres source of truth
- extracted tasks/risks/decisions keep evidence_refs
- Obsidian is export/readable vault only, not source of truth

### Ingestion
- Google Drive AI_INBOX read-only ingestion
- Gmail read-only ingestion foundation
- manual text ingestion: POST /v1/knowledge/ingest-text
- normalized source_events foundation for future GitHub/Jira/Telegram event ingestion

### Extraction
- deterministic rule-based extractor
- extraction processor: POST /v1/extraction/process-document
- extracted_tasks
- extracted_risks
- extracted_decisions
- evidence validator

### Search / Q&A
- deterministic search: GET /v1/knowledge/search?q=...
- deterministic Q&A: POST /v1/knowledge/ask
- search covers chunks, tasks, risks, and decisions

### Scoring / prioritization
- Sprint 04D completed
- knowledge_scores table added
- deterministic explainable scores: importance, urgency, risk, confidence, attention
- score reasons are stored as JSON
- scores preserve evidence_refs
- scoring endpoint: POST /v1/knowledge/score
- search results include score payloads
- Q&A prioritizes by attention_score

### Obsidian export
- Sprint 04E completed
- local exporter script: uv run python scripts/export_obsidian_vault.py --vault-path obsidian_vault --refresh-scores
- exports tasks, risks, and decisions into markdown
- exports readable indexes: FounderOS.md, Tasks/_Index.md, Risks/_Index.md, Decisions/_Index.md
- exported markdown includes metadata, scores, score reasons, evidence_refs, source_document_id, and chunk_id
- duplicate titles are safe because filenames include stable suffix: <title> -- <entity_type>-<entity_id>.md
- frontmatter falls back to evidence_refs when entity fields are missing
- latest local export produced 2 tasks, 1 risk, 1 decision, 4 index files, 8 files total

### Attention / briefing
- Sprint 04F completed
- deterministic attention dashboard added
- endpoint: GET /v1/knowledge/attention
- builds founder-facing summary from Postgres
- uses scored entities and evidence-backed extracted items
- returns top_items, top_tasks, top_risks, recent_decisions, sources, and metadata
- no LLM
- no external API actions
- no write actions
- no scoring auto-refresh

### Integration event foundation
- Sprint 04G completed
- source_events table added
- source_events.ingested_event_id links back to ingested_events.event_id
- deterministic IngestedEvent -> SourceEvent normalizer added
- source_events preserve raw_object_ref and evidence_refs
- foundation prepared for future GitHub/Jira/Telegram connector payloads
- no external API calls, tokens, webhooks, or write actions

### Integration source registry / contracts
- Sprint 04H completed
- integration source registry added
- registered sources: Drive, Gmail, GitHub, Jira, Telegram, Internal
- registry defines source kinds, object contracts, event types, and required payload fields
- source specs are read-only first
- write actions require future approval flow
- connector-layer-only is enforced by source specs
- LLM direct access to integration sources is disabled by source specs
- SourceEvent normalization now validates against integration contracts
- invalid source events are rejected before source_events rows are created
- no DB changes, migrations, external API calls, tokens, webhooks, or write actions

### Connector payload fixtures / normalization coverage
- Sprint 04I completed
- safe connector payload fixtures added for GitHub, Jira, and Telegram
- total fixtures: 10
- GitHub fixtures cover pull_request, issue, commit, and check_run
- Jira fixtures cover issue status change, issue comment, and sprint start
- Telegram fixtures cover command, message, and approval response
- deterministic fixture loader added
- fixtures pass integration source registry contract validation
- normalization tests prove fixture → IngestedEvent → SourceEvent flow
- normalization tests cover all 10 fixtures automatically
- source_events preserve raw_object_ref and evidence_refs for fixture-based events
- no production code changes, DB changes, migrations, API changes, external API calls, tokens, webhooks, or write actions

### Connector payload mapper / ingestion boundary
- Sprint 04J completed
- deterministic connector payload mapper added
- connector payload dicts now map to IngestedEvent-ready fields
- stable deterministic event_id generation added
- mapper validates source_system, source_object_type, event_type, idempotency_key, raw_object_ref, and payload
- mapper reuses integration source registry contracts
- invalid connector payloads fail before DB writes
- deterministic fallback correlation_id and trace_id added
- internal connector ingestion boundary added
- connector payload dict → mapper → IngestedEvent DB row → SourceEvent DB row is now tested
- repeated payload ingestion is idempotent
- all 10 connector fixtures are covered
- no API endpoint changes, migrations, real external API calls, tokens, webhooks, external write actions, or LLM access to connector layer




## Current state

FounderOS can now run this working pipeline:

Google Drive AI_INBOX / manual text
→ raw_storage
→ source_documents
→ document_chunks
→ extraction_processor
→ extracted_tasks / extracted_risks / extracted_decisions
→ knowledge_scores
→ knowledge search
→ deterministic Q&A
→ deterministic attention dashboard
→ Obsidian readable vault export

FounderOS now also has this integration-event foundation:

GitHub / Jira / Telegram connector payload later
→ raw_storage
→ connector payload mapper
→ ingested_events
→ integration source registry contract validation
→ source_events
→ future extracted development entities / scoring / attention

Connector payload test coverage now proves:

safe fixture payload
→ IngestedEvent
→ integration source registry contract validation
→ SourceEvent
→ evidence_refs / raw_object_ref preserved

Connector ingestion boundary now proves:

connector payload dict
→ deterministic mapper
→ IngestedEvent DB row
→ SourceEvent DB row
→ idempotent repeated ingestion



Current health on main:
- uv run ruff check . passes
- uv run pytest -q passes with 97 tests
- ./scripts/check_no_secrets.sh passes
- FastAPI routes: HAS_SEARCH True, HAS_ASK True, HAS_SCORE True, HAS_ATTENTION True
- Alembic current/head: 8c2b0a4d9f1e
- source_events metadata check passes
- PR #9 merged with merge commit c0b936f
- PR #11 merged with merge commit 0daecf6
- PR #12 merged with merge commit 45e8ee5
- PR #14 merged with merge commit c0dd599
- PR #15 merged with merge commit 948707a
- PR #16 merged with merge commit 21b953d
- PR #18 merged with merge commit 870f55a
- PR #19 merged with merge commit 20bafd7

Latest merged work:
- Sprint 04D: deterministic knowledge scoring layer
- Sprint 04E: Obsidian vault exporter
- Hotfix: avoid Obsidian filename collisions
- Hotfix: fill Obsidian evidence frontmatter from evidence refs
- Sprint 04F: deterministic daily briefing / attention dashboard foundation
- Sprint 04G: source_events foundation for future integration-aware event ingestion
- Sprint 04H: integration source registry and source event contract validation
- Sprint 04I: connector payload fixtures and normalization coverage
- Sprint 04J: connector payload mapper and raw event ingestion boundary

## Useful commands

Health checks:
- uv run ruff check .
- uv run pytest -q
- ./scripts/check_no_secrets.sh

Refresh scores:
- curl -X POST http://localhost:8000/v1/knowledge/score -H "Content-Type: application/json" -d "{}"

Export Obsidian vault:
- uv run python scripts/export_obsidian_vault.py --vault-path obsidian_vault --refresh-scores

## Next

Recommended next sprint:

### Sprint 04K — SourceEvent read model and development event projection

Goal:
- make source_events easier to query and inspect
- add deterministic read/query helpers for source_events
- prepare development projections from GitHub/Jira/Telegram SourceEvents
- keep all projections evidence-backed
- preserve raw_object_ref and evidence_refs
- keep extraction deterministic first
- no real external API calls
- no tokens
- no webhooks yet
- no external write actions
- no LLM in connector layer

Possible output:
- source_events query service
- tests for filtering by source_system, source_object_type, event_type, and source_object_id
- deterministic development event projection DTOs
- tests mapping GitHub/Jira/Telegram SourceEvents into read-friendly development facts
- no real API calls
- no webhook server yet unless explicitly approved
- no NOTES.md changes without separate approval

Later:
- GitHub read-only polling/webhook connector
- Jira read-only polling/webhook connector
- Telegram morning digest
- Telegram Q&A
- approval flow for write actions
- proposed_actions / approvals / action_executions
- GitHub/Jira/Telegram write actions only after explicit approval flow
