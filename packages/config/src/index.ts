import { createECDH } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { parse } from 'dotenv';
import { catalog, environmentSchema, envKeys } from './catalog.ts';
import type { Config, Environment, EnvKey } from './catalog.ts';
export * from './catalog.ts';

export class ConfigError extends Error {
  constructor(
    public readonly fields: readonly string[],
    public readonly code = 'invalid_configuration',
  ) {
    super(`${code}: ${fields.join(', ')}`);
    this.name = 'ConfigError';
  }
}
export function parseEnvText(text: string): Record<string, string> {
  // dotenv supports comments and quoted values without executing expansion/substitution.
  const seen = new Set<string>();
  for (const line of text.split(/\r?\n/)) {
    const match = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=/.exec(line);
    if (match?.[1]) {
      if (seen.has(match[1])) throw new ConfigError(['ENV_FILE'], 'duplicate_assignment');
      seen.add(match[1]);
    } else if (line.trim() && !line.trim().startsWith('#')) throw new ConfigError(['ENV_FILE'], 'invalid_env_syntax');
  }
  const values = parse(text);
  if (Object.values(values).some((v) => /[\r\n\0]/.test(v)))
    throw new ConfigError(['ENV_FILE'], 'multiline_value_not_allowed');
  return values;
}
export function readEnvFile(path: string): Record<string, string> {
  try {
    return parseEnvText(readFileSync(path, 'utf8'));
  } catch (error) {
    if (error instanceof ConfigError) throw error;
    throw new ConfigError(['ENV_FILE'], 'env_file_unreadable');
  }
}
export type Validation = { config: Config; invalid: EnvKey[]; pending: EnvKey[] };
export function validateEnvironment(
  input: Record<string, string>,
  environment: Environment,
  mode: 'runtime' | 'bootstrap' = 'runtime',
): Validation {
  if (Object.keys(input).some((key) => !envKeys.includes(key as EnvKey))) throw new ConfigError(['UNKNOWN_VARIABLE']);
  const values = Object.fromEntries(envKeys.map((key) => [key, input[key] ?? '']));
  const parsed = environmentSchema.safeParse(values);
  if (!parsed.success) throw new ConfigError(['ENV_FILE']);
  const config = parsed.data as Config;
  const invalid = new Set<EnvKey>();
  const pending: EnvKey[] = [];
  for (const key of envKeys) {
    const spec = catalog[key];
    const value = config[key];
    if (!spec.environments.includes(environment) && !value) continue;
    const localAgent =
      environment === 'local' && ['NEXT_PUBLIC_SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY'].includes(key);
    if (!value && !spec.optional && mode === 'bootstrap' && (spec.owner === 'agent' || localAgent)) {
      pending.push(key);
      continue;
    }
    if (!spec.schema.safeParse(value).success) invalid.add(key);
  }
  const expected = environment === 'local' ? 'development' : 'production';
  if (config.APP_ENV !== expected) invalid.add('APP_ENV');
  if (config.ENGINE_POLL_MODE !== (environment === 'local' ? '1' : '0')) invalid.add('ENGINE_POLL_MODE');
  if (
    !config.ALLOWED_ORIGINS.split(',')
      .map((s) => s.trim())
      .includes(config.APP_URL)
  )
    invalid.add('ALLOWED_ORIGINS');
  const isLoopback = (s: string) => {
    try {
      return ['localhost', '127.0.0.1', '[::1]'].includes(new URL(s).hostname);
    } catch {
      return false;
    }
  };
  if (environment === 'local' && !isLoopback(config.NEXT_PUBLIC_SUPABASE_URL)) invalid.add('NEXT_PUBLIC_SUPABASE_URL');
  if (environment === 'production') {
    if (config.NEXT_PUBLIC_SUPABASE_URL !== `https://${config.SUPABASE_PROJECT_REF}.supabase.co`)
      invalid.add('NEXT_PUBLIC_SUPABASE_URL');
    for (const key of ['ENGINE_URL', 'SANDBOX_URL'] as const)
      if (config[key] && !/^https:\/\/[a-z0-9.-]+\.run\.app$/.test(config[key])) invalid.add(key);
    if (config.ENGINE_DATABASE_URL) {
      try {
        const url = new URL(config.ENGINE_DATABASE_URL);
        if (url.searchParams.get('sslmode') !== 'verify-full' || !/(^|\.)supabase\.(co|com)$/.test(url.hostname))
          invalid.add('ENGINE_DATABASE_URL');
      } catch {
        invalid.add('ENGINE_DATABASE_URL');
      }
    }
    if (
      config.GCP_DEPLOY_SERVICE_ACCOUNT &&
      !config.GCP_DEPLOY_SERVICE_ACCOUNT.endsWith(`@${config.GCP_PROJECT_ID}.iam.gserviceaccount.com`)
    )
      invalid.add('GCP_DEPLOY_SERVICE_ACCOUNT');
  } else if (config.ENGINE_DATABASE_URL && !isLoopback(config.ENGINE_DATABASE_URL)) invalid.add('ENGINE_DATABASE_URL');
  if (config.CALENDAR_PUSH_ENABLED === 'true' && (!config.APP_URL.startsWith('https:') || isLoopback(config.APP_URL)))
    invalid.add('CALENDAR_PUSH_ENABLED');
  if (config.SENTRY_AUTH_TOKEN && (!config.SENTRY_ORG || !config.SENTRY_PROJECT)) invalid.add('SENTRY_ORG');
  if (config.VAPID_PRIVATE_KEY && config.NEXT_PUBLIC_VAPID_PUBLIC_KEY) {
    try {
      const ecdh = createECDH('prime256v1');
      ecdh.setPrivateKey(Buffer.from(config.VAPID_PRIVATE_KEY, 'base64url'));
      if (ecdh.getPublicKey().toString('base64url') !== config.NEXT_PUBLIC_VAPID_PUBLIC_KEY)
        invalid.add('NEXT_PUBLIC_VAPID_PUBLIC_KEY');
    } catch {
      invalid.add('VAPID_PRIVATE_KEY');
    }
  }
  // A legacy JWT's role must match its use, even before the remote key check.
  for (const [key, role] of [
    ['NEXT_PUBLIC_SUPABASE_ANON_KEY', 'anon'],
    ['SUPABASE_SERVICE_ROLE_KEY', 'service_role'],
  ] as const) {
    if (config[key].startsWith('eyJ')) {
      try {
        const payload: unknown = JSON.parse(Buffer.from(config[key].split('.')[1] ?? '', 'base64url').toString());
        if (typeof payload !== 'object' || payload === null || !('role' in payload) || payload.role !== role)
          invalid.add(key);
      } catch {
        invalid.add(key);
      }
    }
  }
  return { config, invalid: [...invalid], pending };
}
export function loadRuntimeConfig(path: string, environment: Environment): Config {
  const result = validateEnvironment(readEnvFile(path), environment);
  if (result.invalid.length) throw new ConfigError(result.invalid);
  return result.config;
}
