# ADR-0003: REST with typed contracts

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Use REST under /api/v1, strict zod boundary schemas and generated OpenAPI. Route handlers authenticate, parse, call core services and return problem+json errors. Mutations carry Idempotency-Key.

## Alternatives and consequences

GraphQL is unnecessary for one first-party client and would add query-cost and authorization complexity. Keep RPC limited to reviewed database helpers and signed internal engine operations.

## Revisit and validation

Revisit if externally supported clients need query capabilities that REST cannot reasonably express. OpenAPI generation and route inventory enforcement remain M1 wiring.
