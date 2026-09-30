# ADR-0010: Provider adapters and cost control

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

All AI/ML calls use packages/llm-gateway or engine/adapters. Check entitlements/quotas before calls and append usage after. Use one global embedding model. Free tutors use Haiku and 13 messages/day; mock build/grade/regrade are daily-cap exempt but retain monthly/global limits.

## Alternatives and consequences

Reuse Claude's routing/budget/catalog/breaker modules. Prompt and schema artifacts are versioned. Provider metadata/list checks are not inference, quality, or billing validation. Optional paid adapters remain disabled without keys.

## Revisit and validation

Revisit routing only with evaluated quality, measured cost and explicit policy changes; no silent provider fallback that violates a plan.
