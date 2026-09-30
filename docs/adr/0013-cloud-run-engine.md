# ADR-0013: Cloud Run service and batch jobs

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Run the engine on Cloud Run with min instances zero, bounded concurrency/instances and a 60-minute request ceiling. Drain short work inside the wake request for at most 50 minutes. Hand long work to Cloud Run Jobs using the same image and a fenced lease transfer.

## Alternatives and consequences

Cloud Run cannot guarantee CPU after responding, so no background drain after HTTP completion. Online SymPy parsing and sampling run in a killable process with a 1.8-second bound; cold starts or symbolic fallback that cannot finish return undetermined for self-grading. Sandbox compatibility is separately blocked by ADR-0020.

## Revisit and validation

Revisit when measured cold starts require a minimum instance or job duration exceeds configured limits. No production execution or containment evidence is claimed yet.
