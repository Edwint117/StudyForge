import { readFileSync } from 'node:fs';
import postgres from 'postgres';
import { z } from 'zod';
import { ConfigError, readEnvFile, validateEnvironment, type Config } from '../../packages/config/src/index.js';

/**
 * Production database access for release tooling. Connects through the Supabase session pooler (port 5432) with the
 * project's admin role, verifying the certificate chain AND hostname against the pinned Supabase CA. Session mode is
 * required for DDL, advisory locks and multi-statement scripts; the transaction pooler (6543) cannot run migrations.
 */
const poolerSchema = z
  .object({
    db_host: z.string().regex(/^[a-z0-9.-]+\.pooler\.supabase\.com$/),
    db_user: z.string().regex(/^postgres\.[a-z]{20}$/),
  })
  .loose();

export type Sql = postgres.Sql;
export interface ProdTarget {
  host: string;
  user: string;
}

export async function resolveProdTarget(
  config: Pick<Config, 'SUPABASE_PROJECT_REF' | 'SUPABASE_ACCESS_TOKEN'>,
): Promise<ProdTarget> {
  const response = await fetch(
    `https://api.supabase.com/v1/projects/${config.SUPABASE_PROJECT_REF}/config/database/pooler`,
    {
      headers: { Authorization: `Bearer ${config.SUPABASE_ACCESS_TOKEN}` },
      redirect: 'manual',
      signal: AbortSignal.timeout(20_000),
    },
  );
  if (!response.ok) throw new ConfigError(['SUPABASE_ACCESS_TOKEN'], 'pooler_lookup_failed');
  const parsed = z
    .array(poolerSchema)
    .min(1)
    .safeParse(await response.json());
  const first = parsed.success ? parsed.data[0] : undefined;
  if (!first || first.db_user !== `postgres.${config.SUPABASE_PROJECT_REF}`)
    throw new ConfigError(['SUPABASE_PROJECT_REF'], 'pooler_lookup_invalid');
  return { host: first.db_host, user: first.db_user };
}

export function caCertificate(): string {
  return readFileSync(new URL('../../certificates/supabase-prod-ca-2021.crt', import.meta.url), 'utf8');
}

export async function withProdDatabase<T>(
  config: Pick<Config, 'SUPABASE_PROJECT_REF' | 'SUPABASE_ACCESS_TOKEN' | 'SUPABASE_DB_PASSWORD'>,
  work: (sql: Sql, target: ProdTarget) => Promise<T>,
): Promise<T> {
  const target = await resolveProdTarget(config);
  const sql = postgres({
    host: target.host,
    port: 5432,
    database: 'postgres',
    username: target.user,
    password: config.SUPABASE_DB_PASSWORD,
    ssl: { ca: caCertificate(), rejectUnauthorized: true, servername: target.host },
    max: 1,
    connect_timeout: 20,
    idle_timeout: 10,
    prepare: false,
    onnotice: () => undefined,
  });
  try {
    return await work(sql, target);
  } catch (error) {
    // Driver messages can echo connection details; surface a fixed category only.
    if (error instanceof ConfigError) throw error;
    throw new ConfigError(['PRODUCTION_DATABASE'], 'production_database_error');
  } finally {
    await sql.end({ timeout: 5 });
  }
}

/**
 * Production config for release tooling. Agent-provisioned values (engine URL, engine DB URL, sandbox URL) may still be
 * empty before the first deploy: they live in Secret Manager or come from Terraform outputs, so they are `pending`,
 * not invalid. Anything else that fails validation stops the release.
 */
export function loadDeployConfig(): Config {
  const result = validateEnvironment(readEnvFile('.env.production'), 'production', 'bootstrap');
  if (result.invalid.length > 0) throw new ConfigError(result.invalid);
  return result.config;
}
