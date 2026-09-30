# ADR-0019: Local plus one cloud environment

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Use local Docker/Supabase with synthetic data and a single production cloud environment. Do not create a staging account/project. Rehearse releases against a disposable local database reconstructed from production schema only, and use canary traffic and tested rollback.

## Alternatives and consequences

Load tests run locally. Production smoke tests use only the dedicated smoke@studyforge.invalid account and clean up afterward. One OAuth client and the specified single projects follow the owner's credential workflow; no duplicate credential requests.

## Revisit and validation

Revisit when release risk or team size warrants staging. Pending rehearsal, canary and rollback evidence must remain visible; local unit success is not a substitute.
