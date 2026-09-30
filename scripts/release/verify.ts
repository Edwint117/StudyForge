import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { runCli } from '../env/cli.js';
import { ConfigError } from '../../packages/config/src/index.js';
import { buildEngineImage, osvScan, trivyScan } from './images.js';
import {
  git,
  haveTool,
  headInfo,
  LOG_DIR,
  overall,
  renderReport,
  run,
  runStages,
  sequence,
  toolEnv,
  writeReport,
  type Report,
  type Stage,
} from './lib.js';

const ENGINE = 'services/engine';
const HOOK_STAGES = ['lint', 'typecheck', 'unit', 'secrets'];
const TRAILER = 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>';

async function supabaseRunning(): Promise<boolean> {
  return (await run('pnpm exec supabase status', { timeoutMs: 60_000 })).code === 0;
}

export function stages(sha: string): Stage[] {
  const image = `sf-engine:verify-${sha.slice(0, 12)}`;
  return [
    {
      id: 'install',
      title: 'Frozen installs (pnpm, uv)',
      run: (ctx) =>
        sequence(
          [
            { label: 'pnpm install', command: 'pnpm install --frozen-lockfile' },
            { label: 'uv sync', command: 'uv sync --frozen', cwd: ENGINE },
          ],
          ctx,
        ),
    },
    {
      id: 'lint',
      title: 'eslint, prettier, ruff',
      run: (ctx) =>
        sequence(
          [
            { label: 'eslint', command: 'pnpm lint' },
            { label: 'prettier', command: 'pnpm format:check' },
            { label: 'ruff check', command: 'uv run ruff check .', cwd: ENGINE },
            { label: 'ruff format', command: 'uv run ruff format --check .', cwd: ENGINE },
          ],
          ctx,
        ),
    },
    {
      id: 'typecheck',
      title: 'tsc, mypy --strict',
      run: (ctx) =>
        sequence(
          [
            { label: 'tsc', command: 'pnpm typecheck' },
            { label: 'mypy', command: 'uv run mypy engine', cwd: ENGINE },
          ],
          ctx,
        ),
    },
    {
      id: 'unit',
      title: 'Vitest and pytest unit suites',
      run: (ctx) =>
        sequence(
          [
            { label: 'vitest', command: 'pnpm test' },
            { label: 'pytest', command: 'uv run pytest tests -q -p no:cacheprovider', cwd: ENGINE },
          ],
          ctx,
        ),
    },
    {
      id: 'database',
      title: 'Local Supabase, migrations, pgTAP',
      run: async (ctx) => {
        if (!(await supabaseRunning())) {
          const started = await run('pnpm supabase:start', { log: ctx.log('start'), timeoutMs: 600_000 });
          if (started.code !== 0) return { outcome: 'fail', note: 'local Supabase would not start' };
        }
        return sequence(
          [
            { label: 'migration up', command: 'pnpm exec supabase migration up --local' },
            { label: 'pgTAP', command: 'pnpm test:rls' },
          ],
          ctx,
        );
      },
    },
    {
      id: 'integration',
      title: 'Engine integration suite',
      run: async (ctx) =>
        existsSync(`${ENGINE}/integration`)
          ? sequence([{ label: 'integration', command: 'pnpm test:integration' }], ctx)
          : {
              outcome: 'na',
              note: 'services/engine/integration does not exist yet; the job-recovery (heartbeat/VT) test is still owed for the M0 gate',
            },
    },
    {
      id: 'e2e',
      title: 'Playwright (chromium) with axe',
      run: (ctx) => sequence([{ label: 'playwright', command: 'pnpm test:e2e' }], ctx, 1_200_000),
    },
    {
      id: 'semgrep',
      title: 'Semgrep SAST',
      run: async (ctx) =>
        (await haveTool('semgrep'))
          ? sequence(
              [
                {
                  label: 'semgrep',
                  command:
                    'semgrep scan --config p/default --config p/python --config p/typescript --error --quiet --metrics off --disable-version-check --exclude node_modules --exclude .venv --exclude .cache --exclude .tools --exclude .next .',
                  env: toolEnv({ PYTHONUTF8: '1' }),
                },
              ],
              ctx,
            )
          : { outcome: 'skip', note: 'semgrep is not installed' },
    },
    {
      id: 'secrets',
      title: 'gitleaks (staged and full history)',
      run: (ctx) =>
        sequence(
          [
            { label: 'staged', command: 'pnpm secrets:staged' },
            { label: 'history', command: 'pnpm secrets:history' },
          ],
          ctx,
        ),
    },
    {
      id: 'audit',
      title: 'pnpm audit, pip-audit, OSV',
      run: async (ctx) => {
        if (!(await haveTool('pip-audit'))) return { outcome: 'skip', note: 'pip-audit is not installed' };
        const requirements = `${LOG_DIR}/engine-requirements.txt`;
        mkdirSync(LOG_DIR, { recursive: true });
        const steps = await sequence(
          [
            { label: 'pnpm audit', command: 'pnpm audit --audit-level=high' },
            {
              label: 'export lock',
              command: `uv export --frozen --no-hashes --no-emit-project -o ../../${requirements}`,
              cwd: ENGINE,
            },
            { label: 'pip-audit', command: `pip-audit -r ${requirements} --no-deps --disable-pip` },
          ],
          ctx,
        );
        if (steps.outcome !== 'pass') return steps;
        const osv = await osvScan(ctx.log('osv'));
        return osv.outcome === 'pass' ? { outcome: 'pass', note: `${steps.note}, osv-scanner` } : osv;
      },
    },
    {
      id: 'sbom',
      title: 'CycloneDX SBOMs from the lockfiles',
      run: (ctx) => {
        mkdirSync('.cache/release', { recursive: true });
        return sequence(
          [
            { label: 'pnpm sbom', command: 'pnpm sbom --sbom-format cyclonedx > .cache/release/web.cdx.json' },
            {
              label: 'uv sbom',
              command:
                'uv export --frozen --no-emit-project --format cyclonedx1.5 -o ../../.cache/release/engine.cdx.json',
              cwd: ENGINE,
            },
          ],
          ctx,
        );
      },
    },
    {
      id: 'image',
      title: 'Engine image build and Trivy scan',
      run: async (ctx) => {
        if ((await run('docker info', { timeoutMs: 60_000 })).code !== 0)
          return { outcome: 'skip', note: 'Docker is not running' };
        const built = await buildEngineImage(image, ctx.log('build'));
        if (built.code !== 0) return { outcome: 'fail', note: `engine image build failed; see ${ctx.log('build')}` };
        return trivyScan(image, ctx.log('trivy'));
      },
    },
    {
      id: 'evals',
      title: 'Fast eval subset',
      run: async (ctx) =>
        existsSync('evals/run.py')
          ? sequence([{ label: 'evals', command: `${ENGINE}/.venv/Scripts/python.exe evals/run.py` }], ctx)
          : { outcome: 'na', note: 'no labelled eval datasets yet (doc 06 section 7); tracked as open, not passed' },
    },
  ];
}

const FLAGS = ['--fast', '--allow-dirty', '--commit'];

runCli(import.meta.url, async () => {
  const args = process.argv.slice(2);
  const only = args
    .find((a) => a.startsWith('--only='))
    ?.slice('--only='.length)
    .split(',');
  const fast = args.includes('--fast');
  const allowDirty = args.includes('--allow-dirty');
  const commit = args.includes('--commit');
  if (!args.every((a) => a.startsWith('--only=') || FLAGS.includes(a)) || (fast && only))
    throw new ConfigError(['CLI_OPTIONS']);

  const head = headInfo();
  if (head.dirty && !allowDirty)
    throw new ConfigError(
      ['WORKING_TREE'],
      'working_tree_dirty_commit_first_or_pass_--allow-dirty_for_a_non_gating_run',
    );
  const all = stages(head.commit);
  const wanted = fast ? HOOK_STAGES : only;
  if (wanted?.some((id) => !all.some((s) => s.id === id))) throw new ConfigError(['CLI_OPTIONS']);
  const selected = wanted ? all.filter((s) => wanted.includes(s.id)) : all;

  const startedAt = new Date().toISOString();
  const results = await runStages(selected);
  const report: Report = {
    schema: 1,
    kind: 'verify',
    ...head,
    partial: selected.length !== all.length,
    startedAt,
    finishedAt: new Date().toISOString(),
    stages: results,
  };
  const state = overall(report);
  if (report.partial || report.dirty) {
    // Never overwrite the committed, gating report with a run that could not gate anything.
    mkdirSync(LOG_DIR, { recursive: true });
    writeFileSync(`${LOG_DIR}/last-nongating.md`, renderReport(report));
    console.log(`\nverify: ${state.toUpperCase()} (non-gating run; summary in ${LOG_DIR}/last-nongating.md)`);
  } else {
    writeReport(report);
    console.log(`\nverify: ${state.toUpperCase()}; wrote docs/verify/latest.md`);
    if (state === 'pass' && commit) {
      git('add', 'docs/verify');
      git('commit', '-m', `chore(verify): report for ${head.commit.slice(0, 7)}\n\n${TRAILER}`);
      console.log('Committed the report-only commit.');
    } else if (state === 'pass') {
      console.log('Commit the report on its own (only docs/verify/ may change): git add docs/verify && git commit');
    }
  }
  if (state !== 'pass') process.exitCode = 1;
});
