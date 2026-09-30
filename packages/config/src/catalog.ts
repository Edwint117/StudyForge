import { z } from 'zod';

export type Environment = 'local' | 'production';
export type Owner = 'human' | 'agent' | 'generated' | 'default';
const nonempty = z
  .string()
  .min(1)
  .max(8192)
  .refine((s) => s.trim().length > 0 && !/[\r\n\0]/.test(s));
const token = nonempty.refine((s) => !/\s/.test(s));
const origin = nonempty.refine((s) => {
  try {
    const u = new URL(s);
    return ['http:', 'https:'].includes(u.protocol) && u.origin === s && !u.username && !u.password;
  } catch {
    return false;
  }
});
const flag = z.enum(['true', 'false']);
const secret = token.regex(/^[A-Za-z0-9+/]{64}$/).refine((s) => Buffer.from(s, 'base64').length === 48);
const optional = (schema: z.ZodType<string> = token) => z.union([z.literal(''), schema]);
const jwt = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
const anonKey = token.refine((s) => s.startsWith('sb_publishable_') || jwt.test(s));
const serviceKey = token.refine((s) => s.startsWith('sb_secret_') || jwt.test(s));
type Definition = {
  schema: z.ZodType<string>;
  owner: Owner;
  environments: readonly Environment[];
  milestone: string;
  secret: boolean;
  purpose: string;
  source: string;
  initial: string;
  optional: boolean;
  group: string;
};
const field = (
  schema: z.ZodType<string>,
  owner: Owner,
  milestone: string,
  isSecret: boolean,
  purpose: string,
  source: string,
  initial = '',
  environments: readonly Environment[] = ['local', 'production'],
  isOptional = false,
  group = 'App',
): Definition => ({
  schema,
  owner,
  milestone,
  secret: isSecret,
  purpose,
  source,
  initial,
  environments,
  optional: isOptional,
  group,
});
const generated = (milestone: string, purpose: string) =>
  field(
    secret,
    'generated',
    milestone,
    true,
    purpose,
    'Agent: openssl rand -base64 48 (or crypto.randomBytes(48).toString("base64"))',
    '',
    undefined,
    false,
    'Security',
  );
const paid = (purpose: string, source: string) =>
  field(optional(), 'human', 'M4', true, purpose, source, '', undefined, true, 'Optional paid adapters');
const cloud = ['production'] as const;

export const catalog = {
  APP_NAME: field(nonempty, 'default', 'M0', false, 'Single product name', 'Repository configuration', 'StudyForge'),
  APP_ENV: field(
    z.enum(['development', 'production']),
    'default',
    'M0',
    false,
    'Runtime environment',
    'Agent: local=development; production=production',
    'development',
  ),
  APP_URL: field(
    origin,
    'default',
    'M0',
    false,
    'Web origin',
    'Agent: local http://localhost:3000; production http://localhost:3001',
    'http://localhost:3000',
  ),
  ALLOWED_ORIGINS: field(
    nonempty.refine((s) => s.split(',').every((v) => origin.safeParse(v.trim()).success)),
    'default',
    'M1',
    false,
    'CSRF/CORS allowlist',
    'Agent: normally APP_URL only',
    'http://localhost:3000',
  ),
  LOG_LEVEL: field(
    z.enum(['debug', 'info', 'warn', 'error']),
    'default',
    'M0',
    false,
    'Structured logger threshold',
    'Repository configuration',
    'info',
  ),
  BILLING_PROVIDER: field(
    z.literal('mock'),
    'default',
    'M3',
    false,
    'Zero-charge billing implementation',
    'Locked decision: doc07',
    'mock',
  ),
  EMAIL_PROVIDER: field(
    z.literal('outbox'),
    'default',
    'M1',
    false,
    'Database email delivery',
    'Locked decision: ADR-0015',
    'outbox',
  ),
  EMAIL_FROM: field(
    nonempty.refine((s) => /<[^<>\s]+@[^<>\s]+>$/.test(s)),
    'default',
    'M1',
    false,
    'Rendered sender placeholder; not an actual mailbox',
    'Company config placeholder; update centrally with business identity',
    'StudyForge <no-reply@studyforge.invalid>',
  ),
  BOT_CHECK_PROVIDER: field(
    z.literal('none'),
    'default',
    'M1',
    false,
    'BotCheck no-op until public hosting',
    'Locked decision: doc09',
    'none',
  ),
  CALENDAR_PUSH_ENABLED: field(
    flag,
    'default',
    'M5',
    false,
    'Enable public HTTPS calendar webhook; false uses five-minute polling',
    'Repository configuration; true only after public hosting',
    'false',
  ),
  NEXT_PUBLIC_SUPABASE_URL: field(
    origin,
    'human',
    'M0',
    false,
    'Supabase API origin',
    'Supabase project > Settings > API > Project URL; local via agent CLI sync',
    'http://127.0.0.1:54321',
    undefined,
    false,
    'Supabase',
  ),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: field(
    anonKey,
    'human',
    'M0',
    false,
    'Public Supabase client key',
    'Supabase project > Settings > API Keys > publishable or legacy anon; local via CLI sync',
    '',
    undefined,
    false,
    'Supabase',
  ),
  SUPABASE_SERVICE_ROLE_KEY: field(
    serviceKey,
    'human',
    'M0',
    true,
    'Restricted administrative client credential',
    'Supabase project > Settings > API Keys > secret or legacy service_role; local via CLI sync',
    '',
    undefined,
    false,
    'Supabase',
  ),
  SUPABASE_PROJECT_REF: field(
    token.regex(/^[a-z]{20}$/),
    'human',
    'M0',
    false,
    'Cloud project reference',
    'Supabase project > Settings > General > Reference ID',
    '',
    cloud,
    false,
    'Supabase',
  ),
  SUPABASE_ACCESS_TOKEN: field(
    token.min(20),
    'human',
    'M0',
    true,
    'Management API / deploy authentication',
    'Supabase account avatar > Account > Access Tokens',
    '',
    cloud,
    false,
    'Supabase',
  ),
  SUPABASE_DB_PASSWORD: field(
    nonempty,
    'human',
    'M0',
    true,
    'Cloud database operator password',
    'Password saved at project creation; project > Settings > Database to reset',
    '',
    cloud,
    false,
    'Supabase',
  ),
  ENGINE_DATABASE_URL: field(
    nonempty.refine((s) => {
      try {
        const u = new URL(s);
        return (
          ['postgresql:', 'postgres:'].includes(u.protocol) &&
          decodeURIComponent(u.username).split('.')[0] === 'engine_worker' &&
          !!u.password
        );
      } catch {
        return false;
      }
    }),
    'agent',
    'M0',
    true,
    'Least-privilege engine DB connection',
    'Agent: scripted role migration + secret generation; production sslmode=verify-full',
    '',
    undefined,
    false,
    'Supabase',
  ),
  ENGINE_URL: field(
    origin,
    'agent',
    'M0',
    false,
    'Signed engine endpoint',
    'Agent: Terraform output; local http://localhost:8080',
    'http://localhost:8080',
    undefined,
    false,
    'Cloud Run',
  ),
  ENGINE_RPC_SECRET: generated('M0', 'HMAC key for signed web-to-engine RPC'),
  ENGINE_WAKE_SECRET: generated('M0', 'HMAC key for DB wake; also provisioned into Vault'),
  ENGINE_POLL_MODE: field(
    z.enum(['0', '1']),
    'default',
    'M0',
    false,
    'Local queue poller only',
    'Agent: local=1; production=0',
    '1',
    undefined,
    false,
    'Cloud Run',
  ),
  // Empty in production until a sandbox host is chosen (ADR-0020 defers it; not required by the M0 gate).
  // Schema accepts empty so loadRuntimeConfig/start:prod don't hard-fail on a deliberately unbuilt M7 feature.
  SANDBOX_URL: field(
    optional(origin),
    'agent',
    'M0',
    false,
    'Sandbox foundation endpoint (code runner used in M7); empty until ADR-0020 is resolved',
    'Agent: Terraform output; local http://localhost:2000',
    'http://localhost:2000',
    undefined,
    true,
    'Cloud Run',
  ),
  GCP_PROJECT_ID: field(
    token.regex(/^[a-z][a-z0-9-]{4,28}[a-z0-9]$/),
    'human',
    'M0',
    false,
    'One cloud project identifier',
    'Google Cloud Console > project picker > Project ID',
    '',
    cloud,
    false,
    'Cloud Run',
  ),
  GCP_REGION: field(
    token.regex(/^[a-z]+-[a-z]+\d$/),
    'default',
    'M0',
    false,
    'Cloud resource region',
    'Agent: align with Supabase region',
    'us-east1',
    cloud,
    false,
    'Cloud Run',
  ),
  GCP_ARTIFACT_REPO: field(
    token.regex(/^[a-z][a-z0-9-]{0,62}$/),
    'default',
    'M0',
    false,
    'Artifact Registry repository name',
    'Agent: Terraform',
    'studyforge',
    cloud,
    false,
    'Cloud Run',
  ),
  GCP_DEPLOY_SERVICE_ACCOUNT: field(
    token.regex(/^[a-z][a-z0-9-]+@[a-z][a-z0-9-]+\.iam\.gserviceaccount\.com$/),
    'agent',
    'M0',
    false,
    'Impersonated deployer identity; never a key file',
    'Agent: Terraform sf-deployer service account output',
    '',
    cloud,
    false,
    'Cloud Run',
  ),
  TF_STATE_BUCKET: field(
    token.regex(/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/),
    'agent',
    'M0',
    false,
    'Locked/versioned Terraform state bucket',
    'Agent: scripted GCS bootstrap',
    '',
    cloud,
    false,
    'Cloud Run',
  ),
  CSRF_SECRET: generated('M1', 'CSRF signing secret'),
  MOCK_BILLING_WEBHOOK_SECRET: generated('M3', 'Mock billing event signature'),
  OAUTH_STATE_SECRET: generated('M5', 'Signed OAuth state and channel tokens'),
  ANTHROPIC_API_KEY: field(
    token.min(20),
    'human',
    'M4',
    true,
    'LLM adapter credential',
    'Anthropic Console > Settings > API Keys; set Limits > monthly spend cap',
    '',
    undefined,
    false,
    'AI',
  ),
  GLOBAL_AI_BUDGET_USD: field(
    token.refine((s) => /^\d+(\.\d{1,2})?$/.test(s) && Number(s) > 0),
    'default',
    'M4',
    false,
    'Initial global monthly AI budget',
    'Repository default; seed into admin provider config',
    '100',
    undefined,
    false,
    'AI',
  ),
  LANGFUSE_PUBLIC_KEY: field(
    token.min(10),
    'human',
    'M4',
    true,
    'Langfuse Basic auth public component (server-only)',
    'US Langfuse project > Settings > API Keys',
    '',
    undefined,
    false,
    'AI',
  ),
  LANGFUSE_SECRET_KEY: field(
    token.min(10),
    'human',
    'M4',
    true,
    'Langfuse Basic auth secret component',
    'US Langfuse project > Settings > API Keys',
    '',
    undefined,
    false,
    'AI',
  ),
  LANGFUSE_HOST: field(
    z.enum(['https://us.cloud.langfuse.com', 'https://cloud.langfuse.com']),
    'default',
    'M4',
    false,
    'Langfuse cloud API origin',
    'Project region from Langfuse dashboard',
    'https://us.cloud.langfuse.com',
    undefined,
    false,
    'AI',
  ),
  DEEPGRAM_API_KEY: paid('Optional STT', 'console.deepgram.com > API Keys'),
  ASSEMBLYAI_API_KEY: paid('Optional STT/diarization', 'assemblyai.com > Dashboard > API Keys'),
  MISTRAL_API_KEY: paid('Optional document OCR', 'console.mistral.ai > API Keys'),
  VOYAGE_API_KEY: paid('Optional embeddings', 'dash.voyageai.com > API Keys'),
  OPENAI_API_KEY: paid('Optional transcription/embeddings', 'platform.openai.com > API Keys'),
  NEXT_PUBLIC_VAPID_PUBLIC_KEY: field(
    token.refine(
      (s) =>
        /^[A-Za-z0-9_-]+$/.test(s) && Buffer.from(s, 'base64url').length === 65 && Buffer.from(s, 'base64url')[0] === 4,
    ),
    'generated',
    'M2',
    false,
    'Web push public P-256 key',
    'Agent: pnpm env:prepare (crypto.createECDH("prime256v1")); equivalent: npx web-push generate-vapid-keys',
    '',
    undefined,
    false,
    'Web push',
  ),
  VAPID_PRIVATE_KEY: field(
    token.refine((s) => /^[A-Za-z0-9_-]+$/.test(s) && Buffer.from(s, 'base64url').length === 32),
    'generated',
    'M2',
    true,
    'Web push private P-256 key',
    'Agent: pnpm env:prepare; generated together with public key, never rotate one alone',
    '',
    undefined,
    false,
    'Web push',
  ),
  VAPID_SUBJECT: field(
    nonempty.refine((s) => /^mailto:[^\s@]+@[^\s@]+$/.test(s) || /^https:\/\//.test(s)),
    'default',
    'M2',
    false,
    'Web push contact placeholder',
    'Business contact in company config before go-live',
    'mailto:admin@studyforge.invalid',
    undefined,
    false,
    'Web push',
  ),
  GOOGLE_OAUTH_CLIENT_ID: field(
    token.regex(/^\d+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/),
    'human',
    'M1',
    false,
    'One OAuth client for login/calendar',
    'Google Cloud > APIs & Services > Credentials > OAuth client (Web application)',
    '',
    undefined,
    false,
    'Google OAuth',
  ),
  GOOGLE_OAUTH_CLIENT_SECRET: field(
    token.min(12),
    'human',
    'M1',
    true,
    'OAuth client authentication',
    'Same OAuth client details > Client secret',
    '',
    undefined,
    false,
    'Google OAuth',
  ),
  NEXT_PUBLIC_SENTRY_DSN: field(
    nonempty.refine((s) => {
      try {
        const u = new URL(s);
        return (
          u.protocol === 'https:' &&
          /^[a-f0-9]{32}$/i.test(u.username) &&
          !u.password &&
          /(^|\.)ingest\.[a-z]+\.sentry\.io$|(^|\.)ingest\.sentry\.io$/.test(u.hostname) &&
          /^\/\d+$/.test(u.pathname) &&
          !u.search &&
          !u.hash
        );
      } catch {
        return false;
      }
    }),
    'human',
    'M0',
    false,
    'One Sentry project for web/engine',
    'sentry.io > project > Settings > Client Keys (DSN)',
    '',
    undefined,
    false,
    'Observability',
  ),
  SENTRY_AUTH_TOKEN: field(
    optional(),
    'human',
    'M0',
    true,
    'Optional sourcemap upload auth',
    'sentry.io > Settings > Auth Tokens',
    '',
    undefined,
    true,
    'Observability',
  ),
  SENTRY_ORG: field(
    optional(token.regex(/^[a-z0-9_-]+$/)),
    'human',
    'M0',
    false,
    'Sourcemap organization slug when token supplied',
    'sentry.io > Settings > Organization > slug',
    '',
    undefined,
    true,
    'Observability',
  ),
  SENTRY_PROJECT: field(
    optional(token.regex(/^[a-z0-9_-]+$/)),
    'default',
    'M0',
    false,
    'Sourcemap project slug when token supplied',
    'sentry.io > project > Settings > General > slug',
    'studyforge',
    undefined,
    true,
    'Observability',
  ),
  NEXT_PUBLIC_POSTHOG_KEY: field(
    token.regex(/^phc_[A-Za-z0-9_-]+$/),
    'human',
    'M2',
    false,
    'Consent-gated project ingestion key',
    'PostHog > Project Settings > Project API key; Session Replay OFF',
    '',
    undefined,
    false,
    'Observability',
  ),
  NEXT_PUBLIC_POSTHOG_HOST: field(
    z.enum(['https://us.i.posthog.com', 'https://eu.i.posthog.com']),
    'default',
    'M2',
    false,
    'Public ingestion origin; private API origin derived',
    'PostHog project region',
    'https://us.i.posthog.com',
    undefined,
    false,
    'Observability',
  ),
  POSTHOG_PERSONAL_API_KEY: field(
    token.min(10),
    'human',
    'M10',
    true,
    'Read project metadata and delete user analytics',
    'PostHog avatar > Account settings > Personal API Keys; project read + required rights scopes',
    '',
    undefined,
    false,
    'Observability',
  ),
  POSTHOG_PROJECT_ID: field(
    token.regex(/^\d+$/),
    'human',
    'M2',
    false,
    'Analytics project ID',
    'PostHog > Project Settings > Project ID',
    '',
    undefined,
    false,
    'Observability',
  ),
  BETTERSTACK_API_TOKEN: field(
    token.min(10),
    'human',
    'M2',
    true,
    'Uptime monitors/status-page administration',
    'betterstack.com > Uptime > Settings > API tokens',
    '',
    cloud,
    false,
    'Observability',
  ),
  STRIPE_SECRET_KEY: field(
    optional(),
    'human',
    'future',
    true,
    'Unused until real billing',
    'Stripe > Developers > API Keys; leave blank',
    '',
    undefined,
    true,
    'Future billing',
  ),
  STRIPE_WEBHOOK_SECRET: field(
    optional(),
    'human',
    'future',
    true,
    'Unused until real billing',
    'Stripe > Developers > Webhooks > signing secret; leave blank',
    '',
    undefined,
    true,
    'Future billing',
  ),
  NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY: field(
    optional(),
    'human',
    'future',
    false,
    'Unused until real billing',
    'Stripe > Developers > API Keys; leave blank',
    '',
    undefined,
    true,
    'Future billing',
  ),
} as const;

export type EnvKey = keyof typeof catalog;
export type Config = Record<EnvKey, string>;
export const envKeys = Object.keys(catalog) as EnvKey[];
export const environmentSchema = z.object(Object.fromEntries(envKeys.map((key) => [key, z.string()]))).strict();
export const humanKeyMapping = {
  SUPABASE_URL: ['NEXT_PUBLIC_SUPABASE_URL', 'production'],
  SUPABASE_ANON_KEY: ['NEXT_PUBLIC_SUPABASE_ANON_KEY', 'production'],
  SUPABASE_SERVICE_ROLE_KEY: ['SUPABASE_SERVICE_ROLE_KEY', 'production'],
  SUPABASE_PROJECT_REF: ['SUPABASE_PROJECT_REF', 'production'],
  SUPABASE_DB_PASSWORD: ['SUPABASE_DB_PASSWORD', 'production'],
  SUPABASE_ACCESS_TOKEN: ['SUPABASE_ACCESS_TOKEN', 'production'],
  GCP_PROJECT_ID: ['GCP_PROJECT_ID', 'production'],
  BETTERSTACK_API_TOKEN: ['BETTERSTACK_API_TOKEN', 'production'],
  GOOGLE_OAUTH_CLIENT_ID: ['GOOGLE_OAUTH_CLIENT_ID', 'both'],
  GOOGLE_OAUTH_CLIENT_SECRET: ['GOOGLE_OAUTH_CLIENT_SECRET', 'both'],
  ANTHROPIC_API_KEY: ['ANTHROPIC_API_KEY', 'both'],
  SENTRY_DSN: ['NEXT_PUBLIC_SENTRY_DSN', 'both'],
  POSTHOG_PROJECT_API_KEY: ['NEXT_PUBLIC_POSTHOG_KEY', 'both'],
  POSTHOG_PERSONAL_API_KEY: ['POSTHOG_PERSONAL_API_KEY', 'both'],
  POSTHOG_PROJECT_ID: ['POSTHOG_PROJECT_ID', 'both'],
  LANGFUSE_PUBLIC_KEY: ['LANGFUSE_PUBLIC_KEY', 'both'],
  LANGFUSE_SECRET_KEY: ['LANGFUSE_SECRET_KEY', 'both'],
  DEEPGRAM_API_KEY: ['DEEPGRAM_API_KEY', 'both'],
  ASSEMBLYAI_API_KEY: ['ASSEMBLYAI_API_KEY', 'both'],
  MISTRAL_API_KEY: ['MISTRAL_API_KEY', 'both'],
  VOYAGE_API_KEY: ['VOYAGE_API_KEY', 'both'],
  OPENAI_API_KEY: ['OPENAI_API_KEY', 'both'],
} as const satisfies Record<string, readonly [EnvKey, 'production' | 'both']>;

export function ownerKey(key: EnvKey): string {
  return Object.entries(humanKeyMapping).find(([, [destination]]) => destination === key)?.[0] ?? key;
}
