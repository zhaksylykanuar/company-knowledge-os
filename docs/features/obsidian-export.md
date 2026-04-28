# Feature: Obsidian Export

## Status

- Export extracted entities to markdown: implemented
- Index files: implemented
- Score metadata export: implemented
- Obsidian as source of truth: disallowed by policy

## Current Behavior

- Tasks, risks, and decisions can be exported from Postgres into markdown.
- Exported files include metadata, scores, score reasons, and evidence refs.
- Filenames include stable suffixes to avoid collisions.

## Invariants

- Obsidian is export-only.
- Raw storage + Postgres are the source of truth.
- Generated vault files must not be edited as source data.
- Export should preserve evidence refs and source identifiers.

## Known Gaps

- Export cleanup or tombstone handling is unknown.
- Obsidian import back into Postgres is not implemented.
