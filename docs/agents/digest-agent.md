# Digest Agent

## Status

- Attention dashboard source data: implemented
- Scheduled digest generation: planned
- Telegram delivery: planned
- LLM digest prose: planned

## Responsibilities

- Build digests only from evidence-backed scored items.
- Preserve links to sources and evidence refs.
- Avoid write actions unless future approval flow exists.

## Rules

- If evidence is missing, omit the item or mark insufficient evidence.
- LLM digest output must not create new facts.
- LLM must not directly mutate production data.
