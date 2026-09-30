import { catalog, envKeys } from './catalog.js';
import { prepareText } from '../../../scripts/env/prepare.js';
import { parseEnvText } from './index.js';
import type { Config, Environment } from './catalog.js';

export function fixture(environment: Environment = 'local'): Config {
  const initial = Object.fromEntries(envKeys.map((key) => [key, catalog[key].initial]));
  const data = { ...initial, ...parseEnvText(prepareText('', environment)) };
  Object.assign(data, {
    NEXT_PUBLIC_SUPABASE_ANON_KEY: 'sb_publishable_' + 'fixture'.repeat(4),
    SUPABASE_SERVICE_ROLE_KEY: 'sb_secret_' + 'fixture'.repeat(4),
    ENGINE_DATABASE_URL: 'postgresql://engine_worker:fixture@127.0.0.1:54322/postgres',
    GOOGLE_OAUTH_CLIENT_ID: '123456789-fixture.apps.googleusercontent.com',
    GOOGLE_OAUTH_CLIENT_SECRET: 'fixture'.repeat(4),
    ANTHROPIC_API_KEY: 'fixture'.repeat(4),
    LANGFUSE_PUBLIC_KEY: 'fixture'.repeat(4),
    LANGFUSE_SECRET_KEY: 'fixture'.repeat(4),
    NEXT_PUBLIC_SENTRY_DSN: `https://${'a'.repeat(32)}@o1.ingest.us.sentry.io/1`,
    NEXT_PUBLIC_POSTHOG_KEY: 'phc_' + 'fixture'.repeat(4),
    POSTHOG_PERSONAL_API_KEY: 'fixture'.repeat(4),
    POSTHOG_PROJECT_ID: '1',
  });
  if (environment === 'production')
    Object.assign(data, {
      NEXT_PUBLIC_SUPABASE_URL: `https://${'a'.repeat(20)}.supabase.co`,
      SUPABASE_PROJECT_REF: 'a'.repeat(20),
      SUPABASE_ACCESS_TOKEN: 'fixture'.repeat(4),
      SUPABASE_DB_PASSWORD: 'fixture',
      ENGINE_DATABASE_URL: `postgresql://engine_worker:fixture@db.${'a'.repeat(20)}.supabase.co:5432/postgres?sslmode=verify-full`,
      ENGINE_URL: 'https://sf-engine-fixture.run.app',
      SANDBOX_URL: 'https://sf-sandbox-fixture.run.app',
      GCP_PROJECT_ID: 'studyforge-fixture',
      GCP_DEPLOY_SERVICE_ACCOUNT: 'sf-deployer@studyforge-fixture.iam.gserviceaccount.com',
      TF_STATE_BUCKET: 'studyforge-fixture-state',
      BETTERSTACK_API_TOKEN: 'fixture'.repeat(4),
    });
  return data as Config;
}
