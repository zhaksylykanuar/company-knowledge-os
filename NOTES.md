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
→ Obsidian readable vault export

Current health on main:
- uv run ruff check . passes
- uv run pytest -q passes with 44 tests
- ./scripts/check_no_secrets.sh passes
- FastAPI routes: HAS_SEARCH True, HAS_ASK True, HAS_SCORE True

Latest merged work:
- Sprint 04D: deterministic knowledge scoring layer
- Sprint 04E: Obsidian vault exporter
- Hotfix: avoid Obsidian filename collisions
- Hotfix: fill Obsidian evidence frontmatter from evidence refs

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

### Sprint 04F — Daily briefing / attention dashboard foundation

Goal:
- use knowledge_scores.attention_score
- surface what matters today
- deterministic first, no LLM
- no write actions
- no external API actions
- build founder-facing summary from Postgres

Possible output:
- GET /v1/knowledge/attention
- top open tasks
- top risks
- recent decisions
- stale promises / follow-ups
- evidence-backed daily briefing payload

Later:
- Telegram morning digest
- Telegram Q&A
- approval flow for write actions
