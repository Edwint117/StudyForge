# ADR-0018: Backup deferral and honest recovery limits

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Honor the owner's deferral of off-platform backups/PITR. Local release rehearsal restores a schema-only snapshot into a disposable database. Revision rollback restores application code, not deleted or corrupted user data.

## Alternatives and consequences

Do not describe a schema reconstruction as a data restore. A guaranteed data-loss RPO/RTO is unavailable under this decision. Restore-from-backup checklist items remain deferred until real backups are enabled; retain schema/rehearsal and operational recovery work now.

## Revisit and validation

Enable backups and measure restore outcomes before promising data recovery guarantees or when the owner's go-live risk decision requires them.
