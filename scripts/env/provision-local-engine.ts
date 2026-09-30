import { randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { z } from 'zod';
import { ConfigError, parseEnvText } from '../../packages/config/src/index.js';
import { updateEnvText, writePrivateFile } from './files.js';
import { command, supabase } from './process.js';

export async function provisionLocalEngine(): Promise<void> {
  const status = parseEnvText(await supabase(['status', '--output', 'env']));
  const admin = new URL(status.DB_URL ?? 'invalid:');
  if (admin.hostname !== '127.0.0.1' || admin.port !== '54322' || admin.pathname !== '/postgres')
    throw new ConfigError(['LOCAL_DATABASE'], 'local_database_required');
  const current = readFileSync('.env.local', 'utf8');
  const existing = parseEnvText(current).ENGINE_DATABASE_URL;
  const worker = new URL(admin);
  worker.username = 'engine_worker';
  worker.password = existing ? new URL(existing).password : randomBytes(36).toString('hex');
  const output = await command(
    resolve('services/engine/.venv/Scripts/python.exe'),
    [resolve('services/engine/engine/ops/provision_local.py')],
    JSON.stringify({ admin_url: admin.toString(), password: decodeURIComponent(worker.password) }),
  );
  const result = z
    .object({ ok: z.boolean(), code: z.enum(['ok', 'database_error', 'configuration_error']) })
    .strict()
    .parse(JSON.parse(output));
  if (!result.ok) throw new ConfigError(['LOCAL_ENGINE_ROLE'], result.code);
  writePrivateFile('.env.local', updateEnvText(current, { ENGINE_DATABASE_URL: worker.toString() }));
  console.log('Local engine role provisioned; credentials suppressed.');
}
