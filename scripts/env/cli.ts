import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { z } from 'zod';
import { ConfigError } from '../../packages/config/src/index.js';

const optionsSchema = z
  .object({ environment: z.enum(['local', 'production']), bootstrap: z.boolean(), offline: z.boolean() })
  .strict();
export function options(args = process.argv.slice(2)) {
  let environment = 'local';
  let bootstrap = false;
  let offline = false;
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--environment' || arg === '--env') environment = args[++i] ?? '';
    else if (arg === '--bootstrap') bootstrap = true;
    else if (arg === '--offline') offline = true;
    else throw new ConfigError(['CLI_OPTIONS']);
  }
  const result = optionsSchema.safeParse({ environment, bootstrap, offline });
  if (!result.success) throw new ConfigError(['CLI_OPTIONS']);
  return result.data;
}
export function runCli(url: string, main: () => void | Promise<void>): void {
  if (!process.argv[1] || pathToFileURL(resolve(process.argv[1])).href !== url) return;
  void Promise.resolve()
    .then(main)
    .catch((error: unknown) => {
      // Never stringify vendor errors, Zod issues, subprocess stderr or raw config objects.
      console.error(error instanceof ConfigError ? error.message : 'Operation failed; diagnostic values suppressed.');
      process.exitCode = 1;
    });
}
