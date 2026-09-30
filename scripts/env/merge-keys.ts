import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { z } from 'zod';
import { catalog, ConfigError, humanKeyMapping, parseEnvText } from '../../packages/config/src/index.js';
import type { Environment, EnvKey } from '../../packages/config/src/index.js';
import { knownKeyNames, restrictFile, updateEnvText, writePrivateFile } from './files.js';
import { runCli } from './cli.js';

const keySchema = z
  .object(Object.fromEntries(Object.keys(humanKeyMapping).map((key) => [key, z.string().optional()])))
  .strict();
export function mergeKeyTexts(keysText: string, localText: string, productionText: string) {
  const input = keySchema.safeParse(parseEnvText(keysText));
  if (!input.success) throw new ConfigError(['KEYS_FILE'], 'invalid_key_names');
  const inputs = { local: localText, production: productionText };
  for (const text of Object.values(inputs)) knownKeyNames(parseEnvText(text));
  const changes: Record<Environment, Partial<Record<EnvKey, string>>> = { local: {}, production: {} };
  const missing: string[] = [];
  for (const [source, [destination, scope]] of Object.entries(humanKeyMapping)) {
    const value = input.data[source] ?? '';
    if (!value && catalog[destination].optional) continue; // blank optional key never erases an operator value
    if (!value) missing.push(source);
    // Required blanks deliberately clear stale credentials: .env.keys is authoritative.
    changes.production[destination] = value;
    if (scope === 'both') changes.local[destination] = value;
  }
  return {
    local: updateEnvText(localText, changes.local),
    production: updateEnvText(productionText, changes.production),
    missing,
  };
}
export function mergeKeys(root = process.cwd()): string[] {
  const keyPath = resolve(root, '.env.keys');
  if (!existsSync(keyPath)) throw new ConfigError(['KEYS_FILE'], 'keys_file_missing');
  restrictFile(keyPath);
  const local = resolve(root, '.env.local');
  const production = resolve(root, '.env.production');
  // Validate and construct both results before writing either file.
  const output = mergeKeyTexts(
    readFileSync(keyPath, 'utf8'),
    readFileSync(local, 'utf8'),
    readFileSync(production, 'utf8'),
  );
  writePrivateFile(local, output.local);
  writePrivateFile(production, output.production);
  return output.missing;
}
runCli(import.meta.url, () => {
  if (process.argv.length > 2) throw new ConfigError(['CLI_OPTIONS']);
  const missing = mergeKeys();
  console.log('Environment key merge completed; values suppressed.');
  if (missing.length) {
    console.log(`Missing owner keys: ${missing.join(', ')}`);
    process.exitCode = 1;
  }
});
