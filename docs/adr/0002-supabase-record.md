# ADR-0002: Supabase system of record

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Use Supabase Postgres, Auth, Storage and Queues. Tenant means user. Every user-data table has user_id, indexed ownership, enabled/forced RLS, four policies and isolation tests. Composite ownership foreign keys prevent cross-user parent references.

## Alternatives and consequences

Separate databases per user add operational cost. Shared tables require deliberate column grants and narrow server functions; ADR-0007 defines the worker role. Public API exposure is public schema only.

## Revisit and validation

Revisit tenancy for institutional requirements; never loosen existing user isolation as an optimization.
