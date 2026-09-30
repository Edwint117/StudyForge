# ADR-0005: Conditional passkey integration

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

M1 will verify native Supabase WebAuthn availability on the actual project. If GA and supported, use it; otherwise use SimpleWebAuthn with a user-owned credential table, four RLS policies and audit coverage. TOTP is the MFA baseline; do not add SMS.

## Alternatives and consequences

This records the specified selection rule, not a claim that native WebAuthn is available. Capability evidence, credential lifecycle and recovery tests belong to M1.

## Revisit and validation

Select and document the concrete integration during M1 before implementing enrollment. Revisit on provider support or recovery-model changes.
