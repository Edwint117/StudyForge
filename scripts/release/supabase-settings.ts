import { runCli } from '../env/cli.js';
import { ConfigError, type Config } from '../../packages/config/src/index.js';
import { loadDeployConfig } from './prod.js';

/**
 * pnpm supabase:settings [--apply] (M0-16). Declares the production Supabase project's settings and reports drift.
 * Default is a read-only diff; --apply PATCHes only the keys that differ. Google OAuth provider credentials and email
 * hooks are M1 concerns and are deliberately not touched here. Values printed are limited to the non-secret keys below.
 */
const API = 'https://api.supabase.com/v1/projects';

export function desiredAuth(
  config: Pick<Config, 'APP_URL' | 'ALLOWED_ORIGINS'>,
): Record<string, string | number | boolean> {
  const origins = config.ALLOWED_ORIGINS.split(',')
    .map((o) => o.trim())
    .filter(Boolean);
  return {
    site_url: config.APP_URL,
    uri_allow_list: origins.map((o) => `${o}/**`).join(','),
    disable_signup: false,
    mailer_autoconfirm: false, // email verification is required (AUTH-01)
    password_min_length: 8, // AUTH-03: 8 minimum, no composition rules
    mfa_totp_enroll_enabled: true, // AUTH-04
    mfa_totp_verify_enabled: true,
    refresh_token_rotation_enabled: true, // rotating refresh tokens with reuse detection (doc 09 Token Handling)
    security_refresh_token_reuse_interval: 10,
    jwt_exp: 3600,
  };
}

async function call(config: Config, path: string, init: RequestInit = {}): Promise<unknown> {
  const response = await fetch(`${API}/${config.SUPABASE_PROJECT_REF}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${config.SUPABASE_ACCESS_TOKEN}`, 'content-type': 'application/json' },
    redirect: 'manual',
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) throw new ConfigError(['SUPABASE_MANAGEMENT_API'], `management_api_${response.status}`);
  return response.status === 204 ? {} : ((await response.json()) as unknown);
}

export function drift(current: Record<string, unknown>, wanted: Record<string, unknown>) {
  const unknownKeys = Object.keys(wanted).filter((key) => !(key in current));
  const differing = Object.entries(wanted).filter(([key, value]) => key in current && current[key] !== value);
  return { unknownKeys, differing };
}

runCli(import.meta.url, async () => {
  const apply = process.argv.slice(2).join(' ') === '--apply';
  if (process.argv.length > 3 || (process.argv.length === 3 && !apply)) throw new ConfigError(['CLI_OPTIONS']);
  const config = loadDeployConfig();
  let problems = 0;

  const auth = (await call(config, '/config/auth')) as Record<string, unknown>;
  const wanted = desiredAuth(config);
  const { unknownKeys, differing } = drift(auth, wanted);
  for (const key of unknownKeys) console.log(`  ? ${key}: not reported by this project/plan (skipped)`);
  for (const [key, value] of differing)
    console.log(`  ~ auth.${key}: ${JSON.stringify(auth[key])} -> ${JSON.stringify(value)}`);
  if (differing.length === 0) console.log('  auth settings already match');
  else if (apply) {
    await call(config, '/config/auth', { method: 'PATCH', body: JSON.stringify(Object.fromEntries(differing)) });
    console.log(`  applied ${differing.length} auth setting(s)`);
  } else problems++;

  const rest = (await call(config, '/postgrest')) as { db_schema?: string };
  const exposed = (rest.db_schema ?? '').split(',').map((s) => s.trim());
  const leaked = exposed.filter((s) => ['private', 'audit', 'pgmq', 'vault', 'extensions'].includes(s));
  console.log(`  Data API schemas: ${exposed.join(', ') || '(none reported)'}`);
  if (leaked.length > 0) {
    console.log(`  ! internal schema(s) exposed through the Data API: ${leaked.join(', ')}`);
    if (apply) {
      const safe = exposed.filter((s) => !leaked.includes(s)).join(',');
      await call(config, '/postgrest', { method: 'PATCH', body: JSON.stringify({ db_schema: safe }) });
      console.log('  removed them from the Data API');
    } else problems++;
  }

  const ssl = (await call(config, '/ssl-enforcement')) as { currentConfig?: { database?: boolean } };
  if (ssl.currentConfig?.database === true) console.log('  database SSL enforcement is on');
  else if (apply) {
    await call(config, '/ssl-enforcement', {
      method: 'PUT',
      body: JSON.stringify({ requestedConfig: { database: true } }),
    });
    console.log('  enabled database SSL enforcement');
  } else {
    console.log('  ~ database SSL enforcement is off (spec requires verify-full connections)');
    problems++;
  }

  console.log(problems === 0 ? 'Supabase settings: no drift.' : `Supabase settings: drift found; rerun with --apply.`);
  if (problems > 0) process.exitCode = 1;
});
