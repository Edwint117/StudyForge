import { supabase } from '../env/process.js';
import { runCli } from '../env/cli.js';
import { ConfigError } from '../../packages/config/src/index.js';
import { provisionLocalEngine } from '../env/provision-local-engine.js';

runCli(import.meta.url, async () => {
  if (process.argv.length !== 2) throw new ConfigError(['CLI_OPTIONS']);
  await supabase(['migration', 'up', '--local']);
  console.log('Local migrations applied through the scripted pipeline.');
  await provisionLocalEngine();
});
