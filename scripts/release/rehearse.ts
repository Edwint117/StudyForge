import { randomBytes } from 'node:crypto';
import { readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import postgres from 'postgres';
import { runCli } from '../env/cli.js';
import { ConfigError } from '../../packages/config/src/index.js';
import { applyMigrations, classify, listMigrations, pending, appliedVersions } from './migrations.js';
import { LOG_DIR, run, type StageOutcome } from './lib.js';
import { withProdDatabase, loadDeployConfig } from './prod.js';

/**
 * Pre-deploy rehearsal (ADR-0017/0018/0019). A disposable Postgres, built from the same Supabase image as local dev,
 * is put into the state production is in (the migrations production has already applied), then the pending
 * migrations run on top of it and the pgTAP suite runs against the result. It is schema-only: it proves the pending
 * migrations apply cleanly in order, not that production data survives. Nothing here touches the production database
 * except the one read-only query for applied versions.
 */
const NAME = 'sf-rehearsal-db';
const PORT = 54399;
// Same image family as `supabase start`; taken from the running local database so the two cannot drift apart.
async function localDbImage(): Promise<string> {
  const inspected = await run('docker inspect supabase_db_studyforge --format {{.Config.Image}}');
  const image = inspected.tail.trim();
  if (inspected.code !== 0 || !/^[\w./:-]+$/.test(image))
    throw new ConfigError(['DOCKER'], 'local_supabase_db_image_unknown_run_pnpm_supabase_start');
  return image;
}

export type AppliedSource = 'prod' | 'none' | 'all';

async function waitReady(password: string): Promise<postgres.Sql> {
  for (let i = 0; i < 60; i++) {
    const sql = postgres({
      host: '127.0.0.1',
      port: PORT,
      database: 'postgres',
      username: 'postgres',
      password,
      max: 1,
      connect_timeout: 3,
      onnotice: () => undefined,
    });
    try {
      await sql`select 1`;
      return sql;
    } catch {
      await sql.end({ timeout: 1 }).catch(() => undefined);
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  throw new ConfigError(['REHEARSAL_DB'], 'disposable_database_did_not_start');
}

export async function rehearse(source: AppliedSource): Promise<StageOutcome> {
  const all = listMigrations();
  const bad = all.filter((m) => classify(m) === 'unmarked-contract');
  if (bad.length > 0)
    return {
      outcome: 'fail',
      note: `destructive SQL without a "-- @contract" marker in ${bad.map((m) => m.file).join(', ')}`,
    };

  let applied: Set<string>;
  if (source === 'none') applied = new Set();
  else if (source === 'all') applied = new Set(all.map((m) => m.version));
  else {
    const config = loadDeployConfig();
    applied = await withProdDatabase(config, (sql) => appliedVersions(sql));
  }
  const todo = pending(all, applied);
  const password = randomBytes(24).toString('hex');
  const log = `${LOG_DIR}/rehearse.log`;
  await run(`docker rm -f ${NAME}`, { log });
  const started = await run(
    `docker run -d --name ${NAME} -e POSTGRES_PASSWORD=${password} -p 127.0.0.1:${PORT}:5432 ${await localDbImage()}`,
    { log },
  );
  if (started.code !== 0) return { outcome: 'fail', note: 'could not start the disposable database container' };
  try {
    const sql = await waitReady(password);
    try {
      const base = all.filter((m) => applied.has(m.version));
      await applyMigrations(sql, base);
      const done = await applyMigrations(sql, todo);
      await sql`create extension if not exists pgtap with schema extensions`;
      const tests = resolve('supabase/tests');
      const files = readdirSync('supabase/tests')
        .filter((f) => f.endsWith('.test.sql'))
        .map((f) => `/tests/${f}`)
        .join(' ');
      const proved = await run(
        [
          'docker run --rm',
          `--network container:${NAME}`,
          `--mount type=bind,source="${tests}",target=/tests,readonly`,
          `-e PGPASSWORD=${password}`,
          'public.ecr.aws/supabase/pg_prove:3.36',
          `pg_prove -h 127.0.0.1 -p 5432 -U postgres -d postgres ${files}`,
        ].join(' '),
        { log, timeoutMs: 300_000 },
      );
      if (proved.code !== 0) return { outcome: 'fail', note: `pgTAP failed on the rehearsed schema; see ${log}` };
      return {
        outcome: 'pass',
        note: `replayed ${base.length} applied + ${done.length} pending migration(s) on a disposable database; pgTAP green; schema only, no production data restored`,
      };
    } finally {
      await sql.end({ timeout: 3 });
    }
  } catch (error) {
    return { outcome: 'fail', note: error instanceof ConfigError ? error.message : `rehearsal crashed; see ${log}` };
  } finally {
    await run(`docker rm -f ${NAME}`, { log });
  }
}

runCli(import.meta.url, async () => {
  const flag = process.argv[2]?.replace('--applied=', '') ?? 'prod';
  if (process.argv.length > 3 || !['prod', 'none', 'all'].includes(flag)) throw new ConfigError(['CLI_OPTIONS']);
  const result = await rehearse(flag as AppliedSource);
  console.log(`rehearsal: ${result.outcome.toUpperCase()} - ${result.note}`);
  if (result.outcome !== 'pass') process.exitCode = 1;
});
