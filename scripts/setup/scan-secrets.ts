import { resolve } from 'node:path';
import { command } from '../env/process.js';
import { runCli } from '../env/cli.js';
import { ConfigError } from '../../packages/config/src/index.js';

runCli(import.meta.url, async () => {
  const mode = process.argv[2];
  if (process.argv.length !== 3 || !['staged', 'history'].includes(mode ?? '')) throw new ConfigError(['CLI_OPTIONS']);
  const executable = process.platform === 'win32' ? resolve('.tools/gitleaks/gitleaks.exe') : 'gitleaks';
  const args = ['git', '--redact=100', '--no-banner', '--no-color', '--ignore-gitleaks-allow'];
  if (mode === 'staged') args.push('--pre-commit', '--staged');
  else args.push('--log-opts=--all');
  try {
    await command(executable, args, undefined, 120_000);
    console.log(`Secret scan passed (${mode}); scanner output suppressed.`);
  } catch {
    throw new ConfigError(['SECRET_SCAN'], 'secret_detected_or_scanner_failed');
  }
});
