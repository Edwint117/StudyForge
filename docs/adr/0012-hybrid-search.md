# ADR-0012: Hybrid retrieval

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Use Postgres full-text search plus pgvector HNSW and reciprocal-rank fusion with k=60. Start with the specified 384-dimensional bge-small embeddings and one model globally. Persist model/version metadata and run a re-embed job when switching.

## Alternatives and consequences

Reuse engine retrieval/chunking references; database candidates and every source lookup must filter user_id. No multi-tenant vector result is trusted merely because its ID exists. Vendor migration must preserve citation provenance.

## Revisit and validation

Revisit dimensionality/provider only with an evaluated migration, cost evidence and retrieval quality gates in M4.
