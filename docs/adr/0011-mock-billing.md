# ADR-0011: Mock billing provider

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Implement the specified BillingProvider interface with mock $0 checkout and signed lifecycle events. Use list-price arithmetic plus a beta adjustment, with no card data. Port Claude's billing reference and run the identical JSON fixtures in Vitest.

## Alternatives and consequences

The mock preserves subscription/invoice/quota flows without introducing a real payment processor. Stripe is a future adapter and migration project, not an M0 account requirement. Customer-visible beta credits have no cash value.

## Revisit and validation

Revisit before enabling real billing, tax, chargebacks or payment methods; M3 owns current implementation.
