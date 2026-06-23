# Validation Agent

## Status

- Evidence validation: implemented
- Source registry contract validation: implemented
- API auth/rate-limit/signature validation: planned

## Responsibilities

- Validate evidence refs before extracted facts are persisted.
- Validate source events against source registry contracts.
- Fail invalid payloads before downstream writes.
- Keep validation behavior explicit and documented.

## Rules

- Missing evidence means no persisted fact.
- Contract-invalid source events must not be persisted.
- Do not bypass validation for convenience.
