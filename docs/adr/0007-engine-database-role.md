# ADR-0007: Engine database access through narrow grants

- Status: accepted
- Date: 2026-09-28
- Checklist: tenant isolation, least privilege, database security

## Context

Doc 02 requests BYPASSRLS only on selected job tables. PostgreSQL makes BYPASSRLS a role-wide attribute, so that literal configuration does not exist. See [PostgreSQL row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

## Decision

Use `engine_worker` with LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS and no inherited memberships. Grant only schema usage and explicitly named functions. Trusted SECURITY DEFINER functions use an empty search_path, qualified names and validated parameters. Global queue discovery/security bookkeeping is marked CROSS-TENANT-REVIEWED; subsequent user-data operations must filter by user_id. The worker never receives blanket grants on auth, storage, billing, public or private tables. Password provisioning is outside migrations and never written to source.

Every user-data table has user_id, enabled and forced RLS, four authenticated policies and pgTAP coverage. For server-owned records, SELECT checks ownership and INSERT/UPDATE/DELETE policies deny access; SQL write privileges are also revoked. This resolves doc 03's select-only shorthand without weakening the owner's four-policy rule.

## Alternatives and consequences

Role-wide BYPASSRLS or the Supabase service role broadens the damage of a missing predicate and is rejected. Narrow functions require an explicit grant and authorization review when adding a capability. No role change alone proves isolation: execute the privilege and cross-user tests on the actual migrated database.

## Revisit

Revisit if a required queue operation cannot be expressed by a narrowly granted function. Do not silently broaden privileges.
