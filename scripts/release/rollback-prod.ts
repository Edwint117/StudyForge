import { runCli } from '../env/cli.js';
import { gcloud } from '../env/process.js';
import { ConfigError } from '../../packages/config/src/index.js';
import { healthy, revisions, scope, SERVICE, serving } from './cloudrun.js';
import { confirmTyped } from './lib.js';
import { loadDeployConfig } from './prod.js';

/**
 * pnpm rollback:prod: send the engine back to the previous Ready Cloud Run revision (and repoint the long-job image
 * at the same code). Images are immutable digests and secrets are pinned to numeric versions, so a revision is
 * reproducible. This restores application code only: it cannot restore deleted or corrupted data (ADR-0018), and
 * migrations are expand-only so the previous code keeps working against the migrated schema.
 *   --dry-run      show what would change (read-only queries)
 *   --to=<name>    roll to a specific revision instead of the previous one
 *   --confirm=rollback
 */
const JOB = 'sf-engine-long';

runCli(import.meta.url, async () => {
  const args = process.argv.slice(2);
  const dry = args.includes('--dry-run');
  const to = args.find((a) => a.startsWith('--to='))?.slice(5);
  if (!args.every((a) => a === '--dry-run' || a === '--confirm=rollback' || a.startsWith('--to=')))
    throw new ConfigError(['CLI_OPTIONS']);
  if (to !== undefined && !/^sf-engine-[a-z0-9-]+$/.test(to)) throw new ConfigError(['CLI_OPTIONS']);
  const config = loadDeployConfig();

  const current = await serving(config);
  if (!current?.revision || !current.url)
    throw new ConfigError(['ROLLBACK'], 'no_serving_revision_nothing_to_roll_back');
  const history = await revisions(config);
  const at = history.findIndex((r) => r.name === current.revision);
  const target = to ? history.find((r) => r.name === to && r.ready) : history.slice(at + 1).find((r) => r.ready);
  if (!target) throw new ConfigError(['ROLLBACK'], 'no_ready_previous_revision');
  const now = history[at];
  console.log(`Serving:   ${current.revision} (release ${now?.release ?? 'unknown'})`);
  console.log(`Roll to:   ${target.name} (release ${target.release ?? 'unknown'}, ${target.created})`);
  console.log(`Job image: ${JOB} -> the same image as ${target.name}`);
  if (dry) return void console.log('Dry run: nothing changed.');

  if (
    !args.includes('--confirm=rollback') &&
    !(await confirmTyped('rollback', `Roll production back to ${target.name}?`))
  )
    throw new ConfigError(['ROLLBACK'], 'not_confirmed');

  await gcloud(['run', 'services', 'update-traffic', SERVICE, `--to-revisions=${target.name}=100`, ...scope(config)]);
  const jobArgs = ['run', 'jobs', 'update', JOB, `--image=${target.image}`, ...scope(config)];
  if (target.release && /^[0-9a-f]{7,40}$/.test(target.release))
    jobArgs.push(`--update-env-vars=ENGINE_RELEASE=${target.release}`);
  await gcloud(jobArgs);

  const ok = await healthy(current.url, 3, 3000, 20);
  console.log(
    ok
      ? `Rolled back to ${target.name}; /health is green.`
      : `Traffic moved to ${target.name} but /health is NOT green: investigate now.`,
  );
  console.log(
    'Terraform state still records the newer release; the next pnpm deploy:prod re-syncs it. Data was not restored.',
  );
  if (!ok) process.exitCode = 1;
});
