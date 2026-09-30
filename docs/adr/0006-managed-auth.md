# ADR-0006: Managed password authentication

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Use Supabase Auth rather than introducing an application password database or custom Argon2id verifier. Password validation, breached-password checks, progressive rate limits, TOTP and recovery controls are application acceptance requirements.

## Alternatives and consequences

Managed auth reduces credential-handling code but does not remove responsibility for project settings, enumeration resistance, cookie security, email verification or account recovery. Do not store passwords in application logs or tables.

## Revisit and validation

Revisit only if a documented managed-auth limitation prevents required identity controls. Verify behavior against the actual project in M1.
