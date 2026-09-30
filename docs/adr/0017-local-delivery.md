# ADR-0017: Local verification and release provenance

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Use local hooks and pnpm verify instead of hosted CI. Reports identify the exact candidate SHA and stage outcomes. Production deployment requires a clean main checkout, verified candidate provenance, schema rehearsal and explicit release confirmation; immutable images and numeric secret versions permit rollback.

## Alternatives and consequences

Resolve doc08 ordering: verify on the milestone branch, integrate the verified candidate into main for the main-only deployment script, then deploy/smoke and mark/tag the milestone only after all gates pass. A report-only commit may follow verification if its diff contains only the verification report. Main integration is not milestone completion.

## Revisit and validation

Revisit if hosted collaboration or CI is introduced. The 2026-09-28 test deferral permits implementation work but does not produce a green report or authorize bypassing deploy guards.
