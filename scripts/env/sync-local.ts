import { readFileSync } from 'node:fs';
import { z } from 'zod';
import { catalog, ConfigError, parseEnvText } from '../../packages/config/src/index.js';
import { updateEnvText, writePrivateFile } from './files.js';
import { supabase } from './process.js';
import { runCli } from './cli.js';

runCli(import.meta.url, async () => {
  if (process.argv.length > 2) throw new ConfigError(['CLI_OPTIONS']);
  const raw = parseEnvText(await supabase(['status', '--output', 'env']));
  const selected = z
    .object({
      API_URL: catalog.NEXT_PUBLIC_SUPABASE_URL.schema,
      ANON_KEY: catalog.NEXT_PUBLIC_SUPABASE_ANON_KEY.schema,
      SERVICE_ROLE_KEY: catalog.SUPABASE_SERVICE_ROLE_KEY.schema,
    })
    .strict()
    .safeParse({ API_URL: raw.API_URL, ANON_KEY: raw.ANON_KEY, SERVICE_ROLE_KEY: raw.SERVICE_ROLE_KEY });
  if (!selected.success || !/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(selected.data.API_URL))
    throw new ConfigError(['LOCAL_SUPABASE'], 'invalid_cli_status');
  const text = updateEnvText(readFileSync('.env.local', 'utf8'), {
    NEXT_PUBLIC_SUPABASE_URL: selected.data.API_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: selected.data.ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY: selected.data.SERVICE_ROLE_KEY,
  });
  writePrivateFile('.env.local', text);
  console.log('Local Supabase credentials synchronized; values suppressed.');
});
