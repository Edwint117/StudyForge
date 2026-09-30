import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runCli } from '../env/cli.js';
import { gcloud } from '../env/process.js';
import { ConfigError, type Config } from '../../packages/config/src/index.js';
import { signEngineRequest } from '../../packages/engine-client/src/sign.js';
import { updateEnvText, writePrivateFile } from '../env/files.js';
import { engineSecretKeys } from '../env/push-secrets.js';
import { canaryUrlFor, healthy, scope, serving } from './cloudrun.js';
import { buildEngineImage, trivyScan } from './images.js';
import { confirmTyped, git, guardTarget, headInfo, LOG_DIR, run, terraform, TF_DIR } from './lib.js';
import { applyMigrations, appliedVersions, classify, listMigrations, pending } from './migrations.js';
import { withProdDatabase, loadDeployConfig } from './prod.js';
import { rehearse } from './rehearse.js';

/**
 * pnpm deploy:prod  (doc 02 section 6, ADR-0017/0019)
 *
 *   guard -> typed confirmation -> rehearsal -> build + Trivy -> push by digest (SBOM + provenance attached)
 *   -> expand-only migrations -> Terraform canary (10% behind a tag) -> health -> promote to 100% -> wake config
 *   -> smoke -> ZAP baseline
 *
 * Every step that changes production sits after the confirmation. `--dry-run` runs only the local, side-effect-free
 * steps (guard report, rehearsal on a disposable database, image build and scan) and prints the rest.
 */
const REQUIRED_SECRETS = ['ENGINE_DATABASE_URL', 'ENGINE_RPC_SECRET', 'ENGINE_WAKE_SECRET'] as const;
const CANARY_PERCENT = 10;
const OPTIONS = ['--dry-run', '--allow-contract', '--skip-zap', '--allow-destroy'];

function say(step: string, text = '') {
  console.log(`\n== ${step}${text ? `: ${text}` : ''}`);
}
function fail(message: string): never {
  throw new ConfigError(['DEPLOY'], message);
}

async function latestSecretVersions(config: Config): Promise<Record<string, string>> {
  const versions: Record<string, string> = {};
  for (const name of engineSecretKeys) {
    const required = (REQUIRED_SECRETS as readonly string[]).includes(name);
    let out = '';
    try {
      out = await gcloud([
        'secrets',
        'versions',
        'list',
        `sf-${name.toLowerCase().replaceAll('_', '-')}`,
        `--project=${config.GCP_PROJECT_ID}`,
        `--impersonate-service-account=${config.GCP_DEPLOY_SERVICE_ACCOUNT}`,
        '--filter=state=enabled',
        '--sort-by=~name',
        '--limit=1',
        '--format=value(name.basename())',
      ]);
    } catch (error) {
      // An optional secret whose slot Terraform has not created yet is simply absent.
      if (required || !(error instanceof ConfigError) || !error.message.includes('not_found')) throw error;
    }
    const version = out.trim();
    if (/^[1-9][0-9]*$/.test(version)) versions[name] = version;
    else if (required) fail(`secret_missing: ${name} has no enabled version; run pnpm env:push-secrets`);
  }
  return versions;
}

async function pushImage(config: Config, sha: string): Promise<{ ref: string; digest: string }> {
  const host = `${config.GCP_REGION}-docker.pkg.dev`;
  const repository = `${host}/${config.GCP_PROJECT_ID}/${config.GCP_ARTIFACT_REPO}/sf-engine`;
  const token = (
    await gcloud(['auth', 'print-access-token', `--impersonate-service-account=${config.GCP_DEPLOY_SERVICE_ACCOUNT}`])
  ).trim();
  const login = await run(`docker login -u oauth2accesstoken --password-stdin ${host}`, { stdin: token });
  if (login.code !== 0) fail('registry_login_failed');
  const dir = resolve('.cache/release', sha);
  mkdirSync(dir, { recursive: true });
  const meta = resolve(dir, 'build-metadata.json');
  const log = `${LOG_DIR}/deploy-push.log`;
  const pushed = await run(
    [
      'docker buildx build --platform linux/amd64 --provenance=mode=max --sbom=true --push',
      `--label org.opencontainers.image.revision=${sha}`,
      `--metadata-file "${meta}"`,
      `-t ${repository}:${sha}`,
      'services/engine',
    ].join(' '),
    { log, timeoutMs: 1_800_000 },
  );
  if (pushed.code !== 0) fail(`image_push_failed; see ${log}`);
  const digest = (JSON.parse(readFileSync(meta, 'utf8')) as Record<string, unknown>)['containerimage.digest'];
  if (typeof digest !== 'string' || !/^sha256:[0-9a-f]{64}$/.test(digest)) fail('image_digest_missing');
  return { ref: `${repository}@${digest}`, digest };
}

async function terraformRun(config: Config, sha: string, image: string, secrets: Record<string, string>) {
  const token = (await gcloud(['auth', 'print-access-token'])).trim();
  const env = { ...process.env, GOOGLE_OAUTH_ACCESS_TOKEN: token, TF_IN_AUTOMATION: '1' };
  const varFile = resolve(TF_DIR, '.env.deploy.tfvars.json'); // ignored by git (.env.*)
  const init = await terraform(
    ['init', '-input=false', `-backend-config=bucket=${config.TF_STATE_BUCKET}`, '-backend-config=prefix=prod'],
    env,
  );
  if (init.code !== 0) fail('terraform_init_failed');
  const apply = async (extra: Record<string, unknown>, label: string) => {
    writeFileSync(
      varFile,
      JSON.stringify({
        enable_runtime: true,
        engine_image: image,
        engine_release: sha,
        engine_secret_versions: secrets,
        ...extra,
      }),
    );
    const planFile = `${label}.tfplan`;
    const plan = await terraform(
      [
        'plan',
        '-input=false',
        '-var-file=.env.auto.tfvars.json',
        '-var-file=.env.deploy.tfvars.json',
        `-out=${planFile}`,
      ],
      env,
    );
    if (plan.code !== 0) fail('terraform_plan_failed');
    const shown = await terraform(['show', '-json', planFile], env, true);
    const changes =
      (JSON.parse(shown.tail) as { resource_changes?: { address: string; change: { actions: string[] } }[] })
        .resource_changes ?? [];
    const destroys = changes.filter((c) => c.change.actions.includes('delete')).map((c) => c.address);
    if (destroys.length > 0 && !process.argv.includes('--allow-destroy'))
      fail(`plan_destroys_resources: ${destroys.join(', ')}; review, then rerun with --allow-destroy`);
    const applied = await terraform(['apply', '-input=false', planFile], env);
    if (applied.code !== 0) fail('terraform_apply_failed');
  };
  const output = async (name: string) => {
    const out = await terraform(['output', '-raw', name], env, true);
    return out.code === 0 ? out.tail.trim() : undefined;
  };
  return { apply, output };
}

/** Point the database's pg_net wake trigger at the engine (Vault entries the wake migration reads). */
async function configureWake(config: Config, engineUrl: string) {
  await withProdDatabase(config, async (sql) => {
    for (const [name, value] of [
      ['engine_url', engineUrl],
      ['engine_wake_secret', config.ENGINE_WAKE_SECRET],
    ] as const) {
      const rows = await sql<{ id: string }[]>`select id from vault.secrets where name = ${name}`;
      if (rows[0]) await sql`select vault.update_secret(${rows[0].id}::uuid, ${value}, ${name})`;
      else await sql`select vault.create_secret(${value}, ${name})`;
    }
  });
}

async function smoke(config: Config, url: string): Promise<boolean> {
  if (!(await healthy(url, 2, 2000, 6))) return false;
  const body = JSON.stringify({ queue: 'maintenance' });
  const signed = signEngineRequest({ path: '/wake', body, secret: config.ENGINE_WAKE_SECRET });
  const response = await fetch(`${url}/wake`, {
    method: 'POST',
    headers: signed.headers,
    body: signed.body,
    signal: AbortSignal.timeout(60_000),
  });
  return response.status === 200; // exercises the signature check, replay store and database path
}

runCli(import.meta.url, async () => {
  const args = process.argv.slice(2);
  if (!args.every((a) => OPTIONS.includes(a) || a.startsWith('--confirm='))) throw new ConfigError(['CLI_OPTIONS']);
  const dry = args.includes('--dry-run');
  const head = headInfo();
  const sha = head.commit;

  say('1 preflight');
  const guard = guardTarget('HEAD');
  const problems = [...guard.problems];
  if (head.branch !== 'main') problems.push(`on branch ${head.branch}, production deploys come from main`);
  if (head.dirty) problems.push('working tree is not clean');
  if (problems.length > 0) {
    for (const p of problems) console.error(`  - ${p}`);
    if (!dry) fail('preflight_failed');
    console.error('  (dry run: continuing, nothing will be deployed)');
  }
  const config = loadDeployConfig();
  if (!dry) {
    const short = sha.slice(0, 7);
    const typed = args.find((a) => a.startsWith('--confirm='))?.slice('--confirm='.length);
    const ok = typed === short || (typed === undefined && (await confirmTyped(short, `Deploy ${sha} to PRODUCTION?`)));
    if (!ok) fail('not_confirmed');
  }

  say('2 rehearsal', 'disposable database, schema only');
  const rehearsal = await rehearse(dry ? 'none' : 'prod');
  console.log(`  ${rehearsal.outcome.toUpperCase()}: ${rehearsal.note}`);
  if (rehearsal.outcome !== 'pass') fail('rehearsal_failed');

  say('3 build', `sf-engine:${sha.slice(0, 12)}`);
  const local = `sf-engine:deploy-${sha.slice(0, 12)}`;
  if ((await buildEngineImage(local, `${LOG_DIR}/deploy-build.log`)).code !== 0) fail('image_build_failed');
  const scan = await trivyScan(local, `${LOG_DIR}/deploy-trivy.log`);
  console.log(`  Trivy ${scan.outcome.toUpperCase()}: ${scan.note}`);
  if (scan.outcome !== 'pass') fail('image_scan_failed');

  const all = listMigrations();
  const contract = all.filter((m) => classify(m) !== 'expand');
  if (dry) {
    say('dry run complete', 'the remaining steps would run against production');
    console.log(
      [
        '  4 push image by digest with SBOM + provenance to Artifact Registry',
        `  5 apply pending migrations (${all.length} known; contract-phase: ${contract.length})`,
        `  6 terraform: canary at ${CANARY_PERCENT}% behind tag "canary", health checks, promote to 100%`,
        '  7 point the pg_net wake trigger at the engine (Vault)',
        '  8 smoke (/health + signed /wake) and ZAP baseline',
      ].join('\n'),
    );
    return;
  }

  say('4 push', 'Artifact Registry, by digest');
  const secrets = await latestSecretVersions(config);
  const image = await pushImage(config, sha);
  console.log(`  pushed ${image.digest}`);

  say('5 migrations');
  const target = await withProdDatabase(config, async (sql) => pending(all, await appliedVersions(sql)));
  const gated = target.filter((m) => classify(m) !== 'expand');
  if (gated.length > 0) {
    const unmarked = gated.filter((m) => classify(m) === 'unmarked-contract');
    if (unmarked.length > 0) fail(`destructive_sql_without_marker: ${unmarked.map((m) => m.file).join(', ')}`);
    if (!args.includes('--allow-contract'))
      fail(
        `contract_migrations_pending: ${gated.map((m) => m.file).join(', ')}; rerun with --allow-contract after review`,
      );
    if (!(await confirmTyped('contract', `${gated.length} contract-phase migration(s) will run against production.`)))
      fail('contract_not_confirmed');
  }
  const done = await withProdDatabase(config, (sql) => applyMigrations(sql, target));
  console.log(`  applied ${done.length} migration(s)`);

  say('6 terraform', 'canary');
  const tf = await terraformRun(config, sha, image.ref, secrets);
  const before = await serving(config);
  const previous = before?.revision;
  if (previous) {
    await tf.apply({ engine_canary_previous_revision: previous, engine_canary_percent: CANARY_PERCENT }, 'canary');
    // The Terraform output can be empty right after the apply (tag statuses lag), and a failed lookup once aborted a
    // healthy canary. The tag URL has a fixed shape, so derive it from the service URL and fall back to the output.
    const canaryUrl = (before.url ? canaryUrlFor(before.url) : undefined) ?? (await tf.output('engine_canary_url'));
    console.log(`  checking the canary revision on its tag URL (${canaryUrl ? 'resolved' : 'NOT resolved'})`);
    if (!canaryUrl || !(await healthy(canaryUrl, 5, 4000, 30))) {
      await tf.apply({ engine_canary_previous_revision: previous, engine_canary_percent: 0 }, 'abort');
      console.error(
        `  canary unhealthy; traffic held on ${previous}. The new revision is not promoted; inspect it, then rerun or roll back.`,
      );
      fail('canary_unhealthy');
    }
    console.log(`  canary healthy at ${CANARY_PERCENT}%; promoting`);
  } else console.log('  first deployment: no previous revision to protect');
  await tf.apply({}, 'promote');

  const url = (await tf.output('engine_url')) ?? fail('engine_url_missing');
  say('7 wake config');
  await configureWake(config, url);

  if (config.ENGINE_URL !== url) {
    writePrivateFile('.env.production', updateEnvText(readFileSync('.env.production', 'utf8'), { ENGINE_URL: url }));
    console.log('  ENGINE_URL written to .env.production (value suppressed)');
  }

  say('8 smoke');
  if (!(await smoke(config, url))) {
    console.error(
      `  smoke failed. Roll back with: pnpm rollback:prod (previous revision ${previous ?? 'none: first deploy'})`,
    );
    fail('smoke_failed');
  }
  console.log(`  ${url}/health and a signed /wake both answered`);

  const record = { sha, digest: image.digest, previousRevision: previous ?? null, at: new Date().toISOString() };
  mkdirSync('.cache/release', { recursive: true });
  writeFileSync('.cache/release/last-deploy.json', JSON.stringify(record, null, 2));

  if (!args.includes('--skip-zap')) {
    say('9 ZAP baseline', 'reported, never blocks: traffic is already promoted');
    const zap = await run(`docker run --rm ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t ${url} -I`, {
      log: `${LOG_DIR}/deploy-zap.log`,
      timeoutMs: 900_000,
    });
    console.log(
      zap.code === 0 ? '  no alerts' : `  ZAP finished with exit ${zap.code}; read ${LOG_DIR}/deploy-zap.log`,
    );
  }
  console.log(
    `\nDeployed ${sha.slice(0, 7)} (${scope(config)[0]?.split('=')[1]}). Git: ${git('rev-parse', '--short', 'HEAD')}.`,
  );
});
