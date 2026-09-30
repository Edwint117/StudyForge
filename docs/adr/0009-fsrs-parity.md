# ADR-0009: FSRS-6 dual-runtime parity

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Use ts-fsrs for the online scheduling path and py-fsrs for optimization. The engine-core mathematical and crunch/interleaving references are authoritative inputs to the TS ports. Both runtimes must consume the same shared JSON fixtures.

## Alternatives and consequences

Do not independently invent TypeScript learning algorithms. Concrete FSRS library pins, DEFAULT_DECAY compatibility and optimizer behavior are verified in M7; merging pure references alone does not establish scheduling parity.

## Revisit and validation

Revisit library upgrades only with named parity fixtures and review of state migration effects.
