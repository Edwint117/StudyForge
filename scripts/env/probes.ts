import postgres from 'postgres';
import { readFileSync } from 'node:fs';
import { z } from 'zod';
import { catalog } from '../../packages/config/src/index.js';
import type { Config, Environment, EnvKey } from '../../packages/config/src/index.js';
import { gcloud } from './process.js';
import { ProbeError, project, readOnlyGet } from './http.js';

export type ProbeRow = {
  check: string;
  status: 'PASS' | 'FAIL' | 'PENDING' | 'SKIP';
  detail: string;
  fields: string[];
};
type Deps = {
  get: typeof readOnlyGet;
  cloud: typeof gcloud;
  database: (options: postgres.Options<Record<string, postgres.PostgresType>>) => Promise<void>;
};
const database: Deps['database'] = async (options) => {
  const sql = postgres({
    ...options,
    connect_timeout: 10,
    idle_timeout: 1,
    max_lifetime: 15,
    max: 1,
    prepare: false,
    onnotice: () => {},
    debug: false,
  });
  try {
    // CROSS-TENANT-REVIEWED: operator connectivity probe returns a constant, never application rows.
    await sql.begin('read only', async (tx) => {
      await tx`select 1 as connected`;
    });
  } catch (error) {
    // Only allowlisted machine codes may escape the driver; messages can include credentials.
    const code = typeof error === 'object' && error !== null && 'code' in error ? error.code : undefined;
    if (code === '28P01') throw new ProbeError('auth_rejected');
    if (
      code === 'SELF_SIGNED_CERT_IN_CHAIN' ||
      code === 'UNABLE_TO_VERIFY_LEAF_SIGNATURE' ||
      code === 'CERT_HAS_EXPIRED'
    )
      throw new ProbeError('database_certificate_rejected');
    if (code === 'CONNECT_TIMEOUT' || code === 'ETIMEDOUT' || code === 'ECONNREFUSED' || code === 'ENOTFOUND')
      throw new ProbeError('database_unreachable');
    throw new ProbeError('database_connection_failed');
  } finally {
    await sql.end({ timeout: 1 });
  }
};
export async function connectivity(
  config: Config,
  environment: Environment,
  invalid: readonly EnvKey[],
  dependencies: Partial<Deps> = {},
): Promise<ProbeRow[]> {
  const deps: Deps = { get: readOnlyGet, cloud: gcloud, database, ...dependencies };
  const rows: ProbeRow[] = [];
  const usable = (keys: EnvKey[]) =>
    keys.every((k) => !invalid.includes(k) && !!config[k] && catalog[k].schema.safeParse(config[k]).success);
  const probe = async (name: string, fields: EnvKey[], action: () => Promise<string | void>) => {
    if (!usable(fields)) {
      rows.push({ check: name, status: 'SKIP', detail: 'required_fields_not_ready', fields });
      return;
    }
    try {
      const detail = await action();
      rows.push({ check: name, status: 'PASS', detail: detail ?? 'read_only_authenticated', fields });
    } catch (error) {
      rows.push({
        check: name,
        status: 'FAIL',
        detail: error instanceof ProbeError ? error.code : 'probe_failed',
        fields,
      });
    }
  };
  await probe('Supabase auth health', ['NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_ANON_KEY'], async () => {
    await deps.get(`${config.NEXT_PUBLIC_SUPABASE_URL}/auth/v1/health`, {
      apikey: config.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    });
  });
  for (const key of ['NEXT_PUBLIC_SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY'] as const) {
    await probe(
      key === 'SUPABASE_SERVICE_ROLE_KEY' ? 'Supabase server key' : 'Supabase public key',
      ['NEXT_PUBLIC_SUPABASE_URL', key],
      async () => {
        // Auth settings metadata only; never use the service key to query user tables here.
        await deps.get(`${config.NEXT_PUBLIC_SUPABASE_URL}/auth/v1/settings`, { apikey: config[key] });
      },
    );
  }
  if (environment === 'production') {
    await probe('Supabase management', ['SUPABASE_ACCESS_TOKEN', 'SUPABASE_PROJECT_REF'], async () => {
      const data = await deps.get(`https://api.supabase.com/v1/projects/${config.SUPABASE_PROJECT_REF}`, {
        Authorization: `Bearer ${config.SUPABASE_ACCESS_TOKEN}`,
      });
      project(data, z.object({ id: z.string(), status: z.string() }).strict(), ['id', 'status']);
    });
    await probe(
      'Supabase DB password / TLS',
      ['SUPABASE_ACCESS_TOKEN', 'SUPABASE_PROJECT_REF', 'SUPABASE_DB_PASSWORD'],
      async () => {
        const data = await deps.get(
          `https://api.supabase.com/v1/projects/${config.SUPABASE_PROJECT_REF}/config/database/pooler`,
          { Authorization: `Bearer ${config.SUPABASE_ACCESS_TOKEN}` },
        );
        if (!Array.isArray(data)) throw new ProbeError('invalid_response');
        const poolSchema = z
          .object({
            db_host: z.string().regex(/^[a-z0-9.-]+\.pooler\.supabase\.com$/),
            db_port: z.number().int().min(1).max(65535),
            db_user: z.string().regex(/^postgres\.[a-z]{20}$/),
            db_name: z.literal('postgres'),
            pool_mode: z.enum(['session', 'transaction']),
          })
          .strict();
        const pools = data.map((value: unknown) =>
          project(value, poolSchema, ['db_host', 'db_port', 'db_user', 'db_name', 'pool_mode']),
        );
        const pool = pools.find((p) => p.pool_mode === 'session') ?? pools[0];
        if (!pool || pool.db_user !== `postgres.${config.SUPABASE_PROJECT_REF}`)
          throw new ProbeError('invalid_response');
        const ca = readFileSync(new URL('../../certificates/supabase-prod-ca-2021.crt', import.meta.url), 'utf8');
        await deps.database({
          host: pool.db_host,
          port: pool.db_port,
          database: pool.db_name,
          username: pool.db_user,
          password: config.SUPABASE_DB_PASSWORD,
          ssl: { ca, rejectUnauthorized: true, servername: pool.db_host },
        });
      },
    );
  }
  await probe('Anthropic models', ['ANTHROPIC_API_KEY'], async () => {
    const data = await deps.get('https://api.anthropic.com/v1/models?limit=100', {
      'x-api-key': config.ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
    });
    const models = project(data, z.object({ data: z.array(z.unknown()) }).strict(), ['data']);
    if (!models.data.length) throw new ProbeError('invalid_response');
    return 'models_list_only_no_inference';
  });
  await probe(
    'PostHog project / ingestion key',
    ['POSTHOG_PERSONAL_API_KEY', 'POSTHOG_PROJECT_ID', 'NEXT_PUBLIC_POSTHOG_KEY', 'NEXT_PUBLIC_POSTHOG_HOST'],
    async () => {
      const host =
        config.NEXT_PUBLIC_POSTHOG_HOST === 'https://eu.i.posthog.com'
          ? 'https://eu.posthog.com'
          : 'https://us.posthog.com';
      const data = await deps.get(`${host}/api/projects/${config.POSTHOG_PROJECT_ID}/`, {
        Authorization: `Bearer ${config.POSTHOG_PERSONAL_API_KEY}`,
      });
      const projectData = project(
        data,
        z
          .object({ id: z.number().int(), api_token: z.string(), session_recording_opt_in: z.boolean().optional() })
          .strict(),
        ['id', 'api_token', 'session_recording_opt_in'],
      );
      if (
        String(projectData.id) !== config.POSTHOG_PROJECT_ID ||
        projectData.api_token !== config.NEXT_PUBLIC_POSTHOG_KEY
      )
        throw new ProbeError('auth_rejected');
      if (projectData.session_recording_opt_in) return 'keys_valid_disable_session_replay_before_M2';
    },
  );
  await probe('Langfuse project', ['LANGFUSE_HOST', 'LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY'], async () => {
    const auth = Buffer.from(`${config.LANGFUSE_PUBLIC_KEY}:${config.LANGFUSE_SECRET_KEY}`).toString('base64');
    const data = await deps.get(`${config.LANGFUSE_HOST}/api/public/projects`, { Authorization: `Basic ${auth}` });
    const result = project(data, z.object({ data: z.array(z.unknown()).min(1) }).strict(), ['data']);
    if (!result.data.length) throw new ProbeError('invalid_response');
  });
  if (environment === 'production') {
    await probe('Better Stack monitors', ['BETTERSTACK_API_TOKEN'], async () => {
      const data = await deps.get('https://uptime.betterstack.com/api/v2/monitors?per_page=1', {
        Authorization: `Bearer ${config.BETTERSTACK_API_TOKEN}`,
      });
      project(data, z.object({ data: z.array(z.unknown()) }).strict(), ['data']);
    });
    if (usable(['GCP_PROJECT_ID'])) {
      try {
        const token = (await deps.cloud(['auth', 'print-access-token'])).trim();
        if (!token || /\s/.test(token)) throw new ProbeError('invalid_response');
        const data = await deps.get(
          `https://cloudresourcemanager.googleapis.com/v3/projects/${config.GCP_PROJECT_ID}`,
          { Authorization: `Bearer ${token}` },
        );
        const resource = project(data, z.object({ projectId: z.string(), state: z.string() }).strict(), [
          'projectId',
          'state',
        ]);
        if (resource.projectId !== config.GCP_PROJECT_ID || resource.state !== 'ACTIVE')
          throw new ProbeError('invalid_response');
        rows.push({
          check: 'Google Cloud operator/project',
          status: 'PASS',
          detail: 'read_only_authenticated',
          fields: ['GCP_PROJECT_ID'],
        });
      } catch (error) {
        rows.push({
          check: 'Google Cloud operator/project',
          status: 'FAIL',
          detail: error instanceof ProbeError ? error.code : 'gcloud_install_or_browser_login_required',
          fields: ['GCLOUD_LOGIN'],
        });
      }
    }
    if (usable(['GCP_DEPLOY_SERVICE_ACCOUNT'])) {
      await probe('Google Cloud deployer impersonation', ['GCP_DEPLOY_SERVICE_ACCOUNT'], async () => {
        const token = (
          await deps.cloud([
            'auth',
            'print-access-token',
            `--impersonate-service-account=${config.GCP_DEPLOY_SERVICE_ACCOUNT}`,
          ])
        ).trim();
        if (!token || /\s/.test(token)) throw new ProbeError('invalid_response');
      });
    } else
      rows.push({
        check: 'Google Cloud deployer impersonation',
        status: 'PENDING',
        detail: 'agent_provisions_in_M0',
        fields: ['GCP_DEPLOY_SERVICE_ACCOUNT'],
      });
  }
  await probe('Sentry DSN', ['NEXT_PUBLIC_SENTRY_DSN'], async () => 'format_only_no_event_sent');
  await probe(
    'Google OAuth',
    ['GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET'],
    async () => 'format_only_browser_consent_required_M1',
  );
  for (const key of [
    'DEEPGRAM_API_KEY',
    'ASSEMBLYAI_API_KEY',
    'MISTRAL_API_KEY',
    'VOYAGE_API_KEY',
    'OPENAI_API_KEY',
  ] as const) {
    rows.push({
      check: key,
      status: 'SKIP',
      detail: config[key] ? 'configured_adapter_contract_and_live_test_in_M4' : 'optional_not_configured',
      fields: [key],
    });
  }
  return rows;
}
