# ADR-0001: Modular monolith

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Next.js owns HTTP/UI and TypeScript services; Python owns queued engine capabilities. Postgres is the durable coordination boundary. Only signed low-latency SymPy and code-run RPCs bypass the job queue.

## Alternatives and consequences

Independent feature microservices would multiply deployment, tracing and authorization boundaries. Keep domain boundaries inside the packages and engine modules; never add direct web-to-engine calls for heavy work.

## Revisit and validation

Revisit if independent scaling or ownership cannot be met by the existing service and batch-job deployments.
