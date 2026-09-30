# ADR-0015: Outbox email provider

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Use an EmailProvider interface backed by real rendered HTML/text in email_outbox and mirrored notifications. Route managed-auth emails through the supported Send Email database hook, or the specified managed test-email fallback if unavailable. Local auth mail uses Supabase's catcher.

## Alternatives and consequences

No external mail vendor/domain is required for M0. Templates, preferences and suppression logic remain real implementation tasks. Outbox storage is user-owned and accessible only through reviewed routes/admin views.

## Revisit and validation

Revisit when actual delivery is authorized; add a provider adapter without rewriting templates. Verify hook availability during M1.
