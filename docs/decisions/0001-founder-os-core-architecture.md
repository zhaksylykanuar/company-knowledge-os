# 0001 FounderOS Core Architecture

## Status

implemented

## Context

FounderOS needs to ingest company information, preserve provenance, extract operational knowledge, and expose retrieval and briefing views without losing evidence.

## Decision

Use raw storage + Postgres as the source of truth.

Use Obsidian only as a readable export target.

Represent knowledge as evidence-backed source documents, chunks, source events, extracted tasks, risks, decisions, and deterministic scores.

## Consequences

- Every extracted task/risk/decision must have `evidence_refs`.
- Missing evidence means no persisted fact.
- LLM outputs used in pipelines must be strict JSON and validated before persistence.
- LLM must not directly mutate production data.
- Future behavior changes must update relevant docs in the same task.
