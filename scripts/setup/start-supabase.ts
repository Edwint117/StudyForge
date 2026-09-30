import { command } from '../env/process.js';
import { runCli } from '../env/cli.js';
import { resolve } from 'node:path';
import { ConfigError } from '../../packages/config/src/index.js';

runCli(import.meta.url, async () => {
  if (process.argv.length > 2) throw new ConfigError(['CLI_OPTIONS']);
  console.log('Starting local Supabase; CLI output is suppressed because it includes credentials.');
  const progress = setInterval(
    () => console.log('Supabase startup is still running (image pulls may take several minutes).'),
    45_000,
  );
  try {
    await command(process.execPath, [resolve('node_modules/supabase/dist/supabase.js'), 'start'], undefined, 1_200_000);
    console.log('Local Supabase started. Run pnpm env:sync-local to refresh local credentials.');
  } finally {
    clearInterval(progress);
  }
});
