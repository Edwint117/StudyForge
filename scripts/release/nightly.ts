import { existsSync } from 'node:fs';
import { runCli } from '../env/cli.js';
import { haveTool, headInfo, overall, runStages, sequence, writeReport, type Report, type Stage } from './lib.js';
import { rehearse } from './rehearse.js';

/**
 * pnpm nightly (run weekly, or before each milestone gate; doc 02 section 6). Slower and broader than verify, and it
 * never gates a merge: full suites again, dependency freshness, the rehearsal pipeline against an empty production,
 * and the k6 load test against the *local* build when k6 and a script exist (never against the cloud).
 */
const stages: Stage[] = [
  {
    id: 'suites',
    title: 'Full Vitest and pytest suites',
    run: (ctx) =>
      sequence(
        [
          { label: 'vitest', command: 'pnpm test' },
          { label: 'pytest', command: 'uv run pytest tests -q -p no:cacheprovider', cwd: 'services/engine' },
        ],
        ctx,
        1_800_000,
      ),
  },
  {
    id: 'database',
    title: 'pgTAP against local Supabase',
    run: (ctx) => sequence([{ label: 'pgTAP', command: 'pnpm test:rls' }], ctx),
  },
  {
    id: 'deps',
    title: 'Dependency audit and freshness (deps:check)',
    run: async (ctx) => {
      const audited = await sequence([{ label: 'pnpm audit', command: 'pnpm audit --audit-level=high' }], ctx);
      if (audited.outcome !== 'pass') return audited;
      // Freshness is informational: `outdated` exits non-zero when anything is behind, which is not a failure.
      await sequence([{ label: 'pnpm outdated', command: 'pnpm outdated' }], ctx).catch(() => undefined);
      await sequence(
        [{ label: 'uv outdated', command: 'uv tree --outdated --depth 1', cwd: 'services/engine' }],
        ctx,
      ).catch(() => undefined);
      return { outcome: 'pass', note: 'no high-severity advisories; outdated lists are in .cache/verify/deps-*.log' };
    },
  },
  {
    id: 'rehearsal',
    title: 'Migration rehearsal on a fresh disposable database',
    run: () => rehearse('none'),
  },
  {
    id: 'evals',
    title: 'Full eval suite',
    run: async () =>
      existsSync('evals')
        ? { outcome: 'skip', note: 'evals/ exists but no runner is wired yet' }
        : { outcome: 'na', note: 'no labelled eval datasets yet (doc 06 section 7)' },
  },
  {
    id: 'load',
    title: 'k6 load test against the local production build',
    run: async (ctx) => {
      if (!(await haveTool('k6'))) return { outcome: 'skip', note: 'k6 is not installed' };
      if (!existsSync('tests/load/smoke.js')) return { outcome: 'na', note: 'no k6 script yet (tests/load/smoke.js)' };
      return sequence([{ label: 'k6', command: 'k6 run tests/load/smoke.js' }], ctx);
    },
  },
];

runCli(import.meta.url, async () => {
  if (process.argv.length !== 2) throw new Error('nightly takes no arguments');
  const head = headInfo();
  const startedAt = new Date().toISOString();
  const results = await runStages(stages);
  const report: Report = {
    schema: 1,
    kind: 'nightly',
    ...head,
    partial: false,
    startedAt,
    finishedAt: new Date().toISOString(),
    stages: results,
  };
  writeReport(report, 'docs/verify/nightly.json', 'docs/verify/nightly.md');
  console.log(`\nnightly: ${overall(report).toUpperCase()}; wrote docs/verify/nightly.md`);
  if (overall(report) === 'fail') process.exitCode = 1;
});
