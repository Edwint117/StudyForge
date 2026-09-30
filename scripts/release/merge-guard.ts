import { mkdirSync, writeFileSync } from 'node:fs';
import { runCli } from '../env/cli.js';
import { ConfigError } from '../../packages/config/src/index.js';
import { git, gitOk, guardTarget, LOG_DIR } from './lib.js';

/**
 * Refuse to merge (or deploy) code that verification does not cover.
 *   merge-guard.ts                 check HEAD
 *   merge-guard.ts --branch <b>    check the tip of <b>
 *   merge-guard.ts --merge <b>     guard, then switch to main and merge <b> with --no-ff
 *   merge-guard.ts --hook          git pre-merge-commit: when merging into main, check MERGE_HEAD
 * The report is always read from the commit being judged, so a merge cannot smuggle in a rewritten report.
 */
function refuse(problems: string[], subject: string): boolean {
  if (problems.length === 0) return false;
  console.error(`Refusing: ${subject} is not covered by a passing verification report:`);
  for (const problem of problems) console.error(`  - ${problem}`);
  console.error('Run `pnpm verify` on a clean tree, commit docs/verify (report-only), then retry.');
  process.exitCode = 1;
  return true;
}

function judgeCommit(commit: string, subject: string): boolean {
  const spec = `${commit}:docs/verify/latest.json`;
  if (!gitOk('cat-file', '-e', spec)) return refuse(['that commit carries no docs/verify/latest.json'], subject);
  mkdirSync(LOG_DIR, { recursive: true });
  const copy = `${LOG_DIR}/judged-report.json`;
  writeFileSync(copy, git('show', spec));
  return refuse(guardTarget(commit, copy).problems, subject);
}

runCli(import.meta.url, () => {
  const [mode, value] = process.argv.slice(2);
  if (mode === undefined) {
    if (!refuse(guardTarget('HEAD').problems, 'HEAD'))
      console.log('Guard passed: HEAD is covered by a passing report.');
    return;
  }
  if (mode === '--hook') {
    if (git('rev-parse', '--abbrev-ref', 'HEAD') !== 'main') return; // only merges into main are guarded
    if (!gitOk('rev-parse', '-q', '--verify', 'MERGE_HEAD')) return;
    const incoming = git('rev-parse', 'MERGE_HEAD');
    judgeCommit(incoming, `merge of ${incoming.slice(0, 7)} into main`);
    return;
  }
  if ((mode === '--branch' || mode === '--merge') && value && /^[\w./-]+$/.test(value)) {
    const tip = git('rev-parse', value);
    if (judgeCommit(tip, `${value} (${tip.slice(0, 7)})`) || mode === '--branch') return;
    if (git('status', '--porcelain', '--untracked-files=no').length > 0)
      throw new ConfigError(['WORKING_TREE'], 'tracked_changes_present');
    git('switch', 'main');
    git('merge', '--no-ff', '-m', `merge: ${value} (verified ${tip.slice(0, 7)})`, tip);
    console.log(`Merged ${value} into main; nothing has been deployed or tagged.`);
    return;
  }
  throw new ConfigError(['CLI_OPTIONS']);
});
