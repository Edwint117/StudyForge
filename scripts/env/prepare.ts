import { createECDH, randomBytes } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { catalog, ConfigError, envKeys, parseEnvText } from '../../packages/config/src/index.js';
import type { Environment, EnvKey } from '../../packages/config/src/index.js';
import { knownKeyNames, updateEnvText, writePrivateFile } from './files.js';
import { runCli } from './cli.js';

export function renderExample(): string {
  let text =
    '# StudyForge — complete environment contract for M0–M11\n# Generated from packages/config/src/catalog.ts; never put real credentials here.\n# Owner fills .env.keys once; pnpm env:prepare preserves existing values, then pnpm env:merge-keys.\n# See docs/setup/ENV_SETUP.md. Blank agent values are filled during M0. Runtime validation never permits pending values.\n';
  let group = '';
  for (const key of envKeys) {
    const spec = catalog[key];
    if (spec.group !== group) {
      group = spec.group;
      text += `\n# ---------- ${group} ----------\n`;
    }
    text += `# [${spec.optional ? 'OPTIONAL' : 'REQUIRED'}] [${spec.secret ? 'secret' : 'public'}] [${spec.milestone}] [${spec.environments.join(' + ')}] — ${spec.purpose}\n# Source: ${spec.source}\n`;
    text += updateEnvText('', { [key]: spec.initial }).trimStart();
  }
  return text;
}
export function prepareText(text: string, environment: Environment): string {
  const values = parseEnvText(text);
  knownKeyNames(values);
  const changes: Partial<Record<EnvKey, string>> = {};
  for (const key of envKeys) if (!(key in values)) changes[key] = catalog[key].initial;
  for (const key of [
    'ENGINE_RPC_SECRET',
    'ENGINE_WAKE_SECRET',
    'CSRF_SECRET',
    'MOCK_BILLING_WEBHOOK_SECRET',
    'OAUTH_STATE_SECRET',
  ] as const) {
    if (!values[key]) changes[key] = randomBytes(48).toString('base64');
  }
  const pub = values.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  const priv = values.VAPID_PRIVATE_KEY;
  if (!!pub !== !!priv)
    throw new ConfigError(['NEXT_PUBLIC_VAPID_PUBLIC_KEY', 'VAPID_PRIVATE_KEY'], 'incomplete_vapid_pair');
  if (!pub && !priv) {
    const ecdh = createECDH('prime256v1');
    ecdh.generateKeys();
    // Node's ECDH.getPrivateKey() does not left-pad: a private key with a leading zero byte (~1/256 of keys on
    // this curve) comes back short. setPrivateKey() then reads it as a different, smaller integer, which fails
    // the round-trip check in packages/config/src/index.ts. Left-pad to the curve's fixed 32-byte scalar size.
    changes.NEXT_PUBLIC_VAPID_PUBLIC_KEY = ecdh.getPublicKey().toString('base64url');
    changes.VAPID_PRIVATE_KEY = Buffer.from(ecdh.getPrivateKey().toString('hex').padStart(64, '0'), 'hex').toString(
      'base64url',
    );
  }
  if (environment === 'production') {
    if (!values.APP_ENV || values.APP_ENV === 'development') changes.APP_ENV = 'production';
    if (!values.APP_URL || values.APP_URL === 'http://localhost:3000') changes.APP_URL = 'http://localhost:3001';
    if (!values.ALLOWED_ORIGINS || values.ALLOWED_ORIGINS === 'http://localhost:3000')
      changes.ALLOWED_ORIGINS = changes.APP_URL ?? values.APP_URL ?? 'http://localhost:3001';
    changes.ENGINE_POLL_MODE = '0';
    for (const key of ['ENGINE_URL', 'SANDBOX_URL'] as const)
      if (!values[key] || values[key] === catalog[key].initial) changes[key] = '';
  }
  return updateEnvText(text, changes);
}
runCli(import.meta.url, () => {
  if (process.argv.length > 2) throw new ConfigError(['CLI_OPTIONS']);
  const root = process.cwd();
  const example = renderExample();
  // All secret file transformations succeed before any writes; no existing secret is regenerated.
  const prepared = (['local', 'production'] as const).map((environment) => {
    const path = resolve(root, `.env.${environment}`);
    return { path, text: prepareText(existsSync(path) ? readFileSync(path, 'utf8') : example, environment) };
  });
  writeFileSync(resolve(root, '.env.example'), example, 'utf8');
  for (const file of prepared) writePrivateFile(file.path, file.text);
  console.log('Environment defaults prepared; existing credentials preserved; values suppressed.');
});
