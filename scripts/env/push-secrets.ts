import { ConfigError, type EnvKey } from '../../packages/config/src/index.js';
import { loadDeployConfig } from '../release/prod.js';
import { gcloud } from './process.js';
import { runCli } from './cli.js';

// Deliberate least-privilege inventory. Never upload the operator access token, DB password,
// PostHog admin key or future Stripe credentials to the engine service.
// Engine secret name -> config key. The engine reads SENTRY_DSN; the operator file stores it as NEXT_PUBLIC_SENTRY_DSN.
// A DSN is not credential-grade, but it stays in Secret Manager so it never lands in git or Terraform state.
export const engineSecretSources = {
  ENGINE_DATABASE_URL: 'ENGINE_DATABASE_URL',
  SUPABASE_SERVICE_ROLE_KEY: 'SUPABASE_SERVICE_ROLE_KEY',
  ENGINE_RPC_SECRET: 'ENGINE_RPC_SECRET',
  ENGINE_WAKE_SECRET: 'ENGINE_WAKE_SECRET',
  ANTHROPIC_API_KEY: 'ANTHROPIC_API_KEY',
  LANGFUSE_PUBLIC_KEY: 'LANGFUSE_PUBLIC_KEY',
  LANGFUSE_SECRET_KEY: 'LANGFUSE_SECRET_KEY',
  DEEPGRAM_API_KEY: 'DEEPGRAM_API_KEY',
  ASSEMBLYAI_API_KEY: 'ASSEMBLYAI_API_KEY',
  MISTRAL_API_KEY: 'MISTRAL_API_KEY',
  VOYAGE_API_KEY: 'VOYAGE_API_KEY',
  OPENAI_API_KEY: 'OPENAI_API_KEY',
  SENTRY_DSN: 'NEXT_PUBLIC_SENTRY_DSN',
} as const satisfies Record<string, EnvKey>;
export const engineSecretKeys = Object.keys(engineSecretSources) as (keyof typeof engineSecretSources)[];
type Config = ReturnType<typeof loadDeployConfig>;
export interface PushResult {
  added: number;
  unchanged: number;
  missingSlots: string[]; // Terraform has not created the Secret Manager slot yet
}
export async function pushSecrets(config: Config, invoke = gcloud): Promise<PushResult> {
  const result: PushResult = { added: 0, unchanged: 0, missingSlots: [] };
  for (const key of engineSecretKeys) {
    const value = config[engineSecretSources[key]];
    if (!value) continue;
    const secret = `sf-${key.toLowerCase().replaceAll('_', '-')}`;
    const common = [
      `--project=${config.GCP_PROJECT_ID}`,
      `--impersonate-service-account=${config.GCP_DEPLOY_SERVICE_ACCOUNT}`,
    ];
    try {
      // Skip identical values so repeated runs do not mint versions (and therefore new Cloud Run revisions).
      const latest = await invoke(['secrets', 'versions', 'access', 'latest', `--secret=${secret}`, ...common]);
      if (latest === value) {
        result.unchanged++;
        continue;
      }
    } catch (error) {
      // No version yet, or no slot yet: both fall through to the add below, which reports a missing slot.
      if (!(error instanceof ConfigError)) throw error;
    }
    try {
      // Secret resources/IAM must already exist from Terraform. Only add versions here.
      await invoke(['secrets', 'versions', 'add', secret, ...common, '--data-file=-'], value);
      result.added++;
    } catch (error) {
      if (error instanceof ConfigError && error.message.includes('not_found')) result.missingSlots.push(secret);
      else throw error;
    }
  }
  return result;
}
runCli(import.meta.url, async () => {
  if (process.argv.slice(2).join(' ') !== 'production')
    throw new ConfigError(['CLI_OPTIONS'], 'production_argument_required');
  const { added, unchanged, missingSlots } = await pushSecrets(loadDeployConfig());
  console.log(`Published ${added} new engine secret versions, ${unchanged} unchanged; values suppressed.`);
  if (missingSlots.length > 0) {
    console.error(`Missing Secret Manager slots (apply Terraform first): ${missingSlots.join(', ')}`);
    process.exitCode = 1;
  }
});
