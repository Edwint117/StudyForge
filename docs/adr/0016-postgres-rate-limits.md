# ADR-0016: Atomic Postgres token buckets

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Use unlogged private.rate_limit_buckets and the atomic private.rate_limit_hit function. Store HMAC-hashed subjects, not raw IPs or tokens. Replenish consumed capacity continuously and expire idle buckets with pg_cron. A RateLimiter interface permits replacing the backend.

## Alternatives and consequences

A role with only execute grants cannot browse bucket contents. Database errors fail closed. Unlogged data is intentionally ephemeral and may reset after a crash; authenticated abuse controls must not rely solely on this transient state.

## Revisit and validation

Revisit when measured limiter load justifies a separate cache. Concurrency, refill boundaries and failure behavior remain in the deferred review suite.
