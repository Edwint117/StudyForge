import { readFileSync } from 'node:fs';
import { ConfigError, parseEnvText } from '../../packages/config/src/index.js';
import { encodeEnvValue, writePrivateFile } from './files.js';
import { runCli } from './cli.js';

export function writeContainerEnvironment(): void {
  const source = parseEnvText(readFileSync('.env.local', 'utf8'));
  const url = new URL(source.ENGINE_DATABASE_URL ?? 'invalid:');
  if (!['localhost', '127.0.0.1'].includes(url.hostname) || url.port !== '54322' || url.username !== 'engine_worker')
    throw new ConfigError(['ENGINE_DATABASE_URL'], 'local_worker_url_required');
  url.hostname = 'host.docker.internal';
  const values = {
    APP_ENV: 'development',
    ENGINE_DATABASE_URL: url.toString(),
    ENGINE_POLL_MODE: '1',
    ENGINE_RPC_SECRET: source.ENGINE_RPC_SECRET ?? '',
    ENGINE_WAKE_SECRET: source.ENGINE_WAKE_SECRET ?? '',
    ENGINE_RELEASE: 'local',
    // Off when the DSN is unset; the engine reports environment=development so these never mix with production.
    ...(source.NEXT_PUBLIC_SENTRY_DSN ? { SENTRY_DSN: source.NEXT_PUBLIC_SENTRY_DSN } : {}),
  };
  if (values.ENGINE_RPC_SECRET.length < 32 || values.ENGINE_WAKE_SECRET.length < 32)
    throw new ConfigError(['ENGINE_RPC_SECRET', 'ENGINE_WAKE_SECRET']);
  writePrivateFile(
    '.env.engine.local',
    Object.entries(values)
      .map(([key, value]) => `${key}=${encodeEnvValue(value)}`)
      .join('\n') + '\n',
  );
}

runCli(import.meta.url, () => {
  if (process.argv.length !== 2) throw new ConfigError(['CLI_OPTIONS']);
  writeContainerEnvironment();
  console.log('Container environment generated with the minimal engine allowlist; values suppressed.');
});
