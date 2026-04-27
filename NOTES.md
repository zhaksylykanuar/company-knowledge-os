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
→ ingested_events
→ source_events
→ future extracted development entities / scoring / attention

Current health on main:
- uv run ruff check . passes
- uv run pytest -q passes with 50 tests
- ./scripts/check_no_secrets.sh passes
- FastAPI routes: HAS_SEARCH True, HAS_ASK True, HAS_SCORE True, HAS_ATTENTION True
- Alembic current/head: 8c2b0a4d9f1e
- source_events metadata check passes
- PR #9 merged with merge commit c0b936f

Latest merged work:
- Sprint 04D: deterministic knowledge scoring layer
- Sprint 04E: Obsidian vault exporter
- Hotfix: avoid Obsidian filename collisions
- Hotfix: fill Obsidian evidence frontmatter from evidence refs
- Sprint 04F: deterministic daily briefing / attention dashboard foundation
- Sprint 04G: source_events foundation for future integration-aware event ingestion

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

### Sprint 04H — Integration source registry and connector contracts

Goal:
- keep GitHub/Jira/Telegram read-only first
- define integration source registry without secrets in code
- define connector event contracts for GitHub/Jira/Telegram payloads
- keep raw payload saved before normalization
- keep LLM out of connector layer
- keep source_events evidence-backed and traceable to ingested_events
- avoid external write actions

Possible output:
- integration source enum/registry
- deterministic source event contract tests
- GitHub/Jira/Telegram sample payload fixtures with no secrets
- source_events normalization coverage for pull requests, Jira issues, and Telegram commands
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
