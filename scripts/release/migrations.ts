import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { ConfigError } from '../../packages/config/src/index.js';
import type { Sql } from './prod.js';

/**
 * Scripted migration runner (hard rule 10: migrations only ship through the pipeline). It writes the same
 * supabase_migrations.schema_migrations table the Supabase CLI uses, so local `supabase migration up` and this runner
 * agree on what has been applied.
 */
export interface Migration {
  version: string;
  name: string;
  file: string;
  sql: string;
}

const FILE = /^(\d{14})_([a-z0-9_]+)\.sql$/;
// Contract-phase statements: they can break the previous release, so they never run unattended.
const DESTRUCTIVE =
  /\b(drop\s+(table|column|schema|type)\b|truncate\b|alter\s+table\s+\S+\s+(rename|drop\s+column)\b|alter\s+column\s+\S+\s+(set\s+data\s+)?type\b)/i;
export const CONTRACT_MARKER = /^\s*--\s*@contract\b/m;

export function listMigrations(dir = 'supabase/migrations'): Migration[] {
  const found = readdirSync(dir)
    .filter((file) => file.endsWith('.sql'))
    .map((file) => {
      const match = FILE.exec(file);
      if (!match?.[1] || !match[2]) throw new ConfigError(['MIGRATION_NAME'], `migration_name_invalid: ${file}`);
      return { version: match[1], name: match[2], file, sql: readFileSync(join(dir, file), 'utf8') };
    })
    .sort((a, b) => a.version.localeCompare(b.version));
  if (new Set(found.map((m) => m.version)).size !== found.length)
    throw new ConfigError(['MIGRATION_NAME'], 'duplicate_migration_version');
  return found;
}

/** Strip comments and string literals so keywords inside them do not trigger the destructive scan. */
function code(sql: string): string {
  return sql
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/--.*$/gm, ' ')
    .replace(/\$([a-z_]*)\$[\s\S]*?\$\1\$/gi, ' ')
    .replace(/'(?:[^']|'')*'/g, "''");
}

export function classify(migration: Migration): 'expand' | 'contract' | 'unmarked-contract' {
  const marked = CONTRACT_MARKER.test(migration.sql);
  const destructive = DESTRUCTIVE.test(code(migration.sql));
  if (marked) return 'contract';
  return destructive ? 'unmarked-contract' : 'expand';
}

export function pending(all: Migration[], applied: ReadonlySet<string>): Migration[] {
  const missing = [...applied].filter((version) => !all.some((m) => m.version === version));
  // The database knows a migration this checkout does not: never guess, the branch is behind or diverged.
  if (missing.length > 0) throw new ConfigError(['MIGRATION_HISTORY'], 'database_has_migrations_missing_locally');
  return all.filter((m) => !applied.has(m.version));
}

export async function appliedVersions(sql: Sql): Promise<Set<string>> {
  const [exists] = await sql<
    { t: string | null }[]
  >`select to_regclass('supabase_migrations.schema_migrations')::text as t`;
  if (!exists?.t) return new Set();
  const rows = await sql<{ version: string }[]>`select version from supabase_migrations.schema_migrations`;
  return new Set(rows.map((r) => r.version));
}

const LOCK_KEY = 7_302_001; // arbitrary constant: one migration run at a time per database

/** Apply migrations in order, each in its own transaction together with its bookkeeping row. */
export async function applyMigrations(sql: Sql, migrations: Migration[]): Promise<string[]> {
  const applied: string[] = [];
  await sql`select pg_advisory_lock(${LOCK_KEY})`;
  try {
    await sql`create schema if not exists supabase_migrations`;
    await sql`create table if not exists supabase_migrations.schema_migrations (
      version text not null primary key, statements text[], name text)`;
    const done = await appliedVersions(sql);
    for (const migration of migrations) {
      if (done.has(migration.version)) continue;
      await sql.begin(async (tx) => {
        await tx.unsafe(migration.sql);
        await tx`insert into supabase_migrations.schema_migrations (version, name, statements)
                 values (${migration.version}, ${migration.name}, ${[migration.sql]})`;
      });
      applied.push(migration.version);
    }
  } finally {
    await sql`select pg_advisory_unlock(${LOCK_KEY})`;
  }
  return applied;
}
