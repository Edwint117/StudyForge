import { randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import postgres from 'postgres';
import { runCli } from '../env/cli.js';
import { updateEnvText, writePrivateFile } from '../env/files.js';
import { ConfigError, parseEnvText } from '../../packages/config/src/index.js';
import { caCertificate, loadDeployConfig, resolveProdTarget, withProdDatabase } from './prod.js';

/**
 * pnpm env:provision-prod-engine (M0-16). Creates (or re-passwords) the production `engine_worker` role, generates the
 * engine's connection string and the two HMAC secrets, and writes them to the private .env.production. Nothing is
 * printed. Idempotent: an existing password/secret is kept, never rotated implicitly. Afterwards:
 *   pnpm env:push-secrets production     (uploads new versions to Secret Manager)
 *
 * Role attributes match supabase/migrations/20260928000100_engine_security.sql, which later adds the grants; creating
 * the role first breaks the chicken-and-egg between "secrets must exist before deploy" and "migrations run in deploy".
 * The URL uses the session pooler (port 5432; psycopg prepares statements, which transaction pooling would break),
 * verify-full, and the CA file baked into the engine image.
 */
export const IMAGE_CA_PATH = '/app/certs/supabase-prod-ca-2021.crt';
const HEX_PASSWORD = /^[0-9a-f]{72}$/;

export function engineUrl(ref: string, host: string, password: string): string {
  const url = new URL(`postgresql://placeholder@${host}:5432/postgres`);
  url.username = `engine_worker.${ref}`;
  url.password = password;
  url.searchParams.set('sslmode', 'verify-full');
  url.searchParams.set('sslrootcert', IMAGE_CA_PATH);
  return url.toString();
}

runCli(import.meta.url, async () => {
  if (process.argv.length !== 2) throw new ConfigError(['CLI_OPTIONS']);
  const config = loadDeployConfig();
  const text = readFileSync('.env.production', 'utf8');
  const current = parseEnvText(text);

  let password = randomBytes(36).toString('hex');
  if (current.ENGINE_DATABASE_URL) {
    const existing = decodeURIComponent(new URL(current.ENGINE_DATABASE_URL).password);
    if (HEX_PASSWORD.test(existing)) password = existing;
  }
  const rpc =
    (current.ENGINE_RPC_SECRET ?? '').length >= 32 ? current.ENGINE_RPC_SECRET! : randomBytes(32).toString('hex');
  let wake =
    (current.ENGINE_WAKE_SECRET ?? '').length >= 32 ? current.ENGINE_WAKE_SECRET! : randomBytes(32).toString('hex');
  if (wake === rpc) wake = randomBytes(32).toString('hex'); // scopes must never share a key

  const target = await withProdDatabase(config, async (sql, resolved) => {
    // `password` is hex by construction (validated above), so inlining it is safe; ALTER ROLE cannot bind parameters.
    await sql.unsafe(`
      do $$ begin
        if not exists (select 1 from pg_roles where rolname = 'engine_worker') then
          create role engine_worker login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
        end if;
      end $$;
      alter role engine_worker with login nobypassrls password '${password}'`);
    return resolved;
  });

  // Prove the credentials work through the pooler, with certificate AND hostname verification, before saving.
  const proof = postgres({
    host: target.host,
    port: 5432,
    database: 'postgres',
    username: `engine_worker.${config.SUPABASE_PROJECT_REF}`,
    password,
    ssl: { ca: caCertificate(), rejectUnauthorized: true, servername: target.host },
    max: 1,
    connect_timeout: 20,
    prepare: false,
  });
  try {
    const [row] = await proof<{ u: string }[]>`select current_user as u`;
    if (row?.u !== 'engine_worker') throw new ConfigError(['ENGINE_DATABASE_URL'], 'connected_as_unexpected_role');
  } catch (error) {
    if (error instanceof ConfigError) throw error;
    throw new ConfigError(['ENGINE_DATABASE_URL'], 'worker_login_through_pooler_failed');
  } finally {
    await proof.end({ timeout: 5 });
  }

  const resolved = await resolveProdTarget(config);
  writePrivateFile(
    '.env.production',
    updateEnvText(text, {
      ENGINE_DATABASE_URL: engineUrl(config.SUPABASE_PROJECT_REF, resolved.host, password),
      ENGINE_RPC_SECRET: rpc,
      ENGINE_WAKE_SECRET: wake,
    }),
  );
  console.log(
    'Production engine role verified through the pooler; ENGINE_DATABASE_URL and HMAC secrets saved (values suppressed).',
  );
  console.log('Next: pnpm env:push-secrets production');
});
