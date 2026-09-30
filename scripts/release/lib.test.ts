import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { conventionalHeader } from '../setup/check-commit-msg.js';
import { assessReport, overall, renderReport, reportSchema, type Report } from './lib.js';

const sha = 'a'.repeat(40);
const other = 'b'.repeat(40);
const now = new Date('2026-09-28T12:00:00Z');
const base: Report = {
  schema: 1,
  kind: 'verify',
  commit: sha,
  tree: sha,
  branch: 'm0-foundation',
  dirty: false,
  partial: false,
  startedAt: '2026-09-28T10:00:00Z',
  finishedAt: '2026-09-28T11:00:00Z',
  stages: [
    { id: 'lint', title: 'lint', outcome: 'pass', seconds: 3, note: 'ok' },
    { id: 'evals', title: 'evals', outcome: 'na', seconds: 0, note: 'no datasets yet' },
  ],
};
const judge = (report: Report, target = sha, changed: string[] = []) =>
  assessReport({ report, target, changedSinceReport: changed, now });

describe('verification guard', () => {
  it('accepts a clean, complete, fresh report for the exact commit', () => {
    expect(judge(base)).toEqual([]);
    expect(overall(base)).toBe('pass');
  });
  it('refuses failing, skipped, partial and dirty runs', () => {
    const stage = (outcome: 'fail' | 'skip') => ({ ...base, stages: [{ ...base.stages[0]!, outcome }] });
    expect(judge(stage('fail')).join()).toMatch(/fail/);
    expect(judge(stage('skip')).join()).toMatch(/incomplete/);
    expect(judge({ ...base, partial: true }).join()).toMatch(/subset/);
    expect(judge({ ...base, dirty: true }).join()).toMatch(/dirty/);
    expect(judge({ ...base, kind: 'nightly' }).join()).toMatch(/not a verify report/);
  });
  it('is stale when code changed after verification, but tolerates a report-only follow-up commit', () => {
    expect(judge(base, other, ['services/engine/engine/app.py']).join()).toMatch(/stale/);
    expect(judge(base, other, ['docs/verify/latest.md', 'docs/verify/latest.json'])).toEqual([]);
    expect(judge(base, other, ['docs/verify/latest.md', 'README.md']).join()).toMatch(/stale/);
  });
  it('expires old or future-dated reports', () => {
    expect(judge({ ...base, finishedAt: '2026-09-20T00:00:00Z' }).join()).toMatch(/older/);
    expect(judge({ ...base, finishedAt: '2026-09-29T00:00:00Z' }).join()).toMatch(/future/);
  });
  it('round-trips through the schema and renders every stage', () => {
    expect(reportSchema.safeParse(JSON.parse(JSON.stringify(base))).success).toBe(true);
    expect(reportSchema.safeParse({ ...base, extra: 1 }).success).toBe(false);
    expect(renderReport(base)).toContain('| evals | N/A |');
  });
});

describe('conventional commits', () => {
  it('accepts typed headers and git-generated merges', () => {
    for (const ok of [
      'feat(engine): add wake',
      'fix: typo',
      'chore(verify)!: drop x',
      'Merge branch x',
      'merge: m0 (verified abc1234)',
    ])
      expect(conventionalHeader(ok)).toBe(true);
  });
  it('rejects free-form headers', () => {
    for (const bad of [
      'update stuff',
      'Feat: capital',
      'feat(engine):no space',
      'feat:',
      '',
      'fix: add sponsor editor.',
      'chore: wip',
      'fix: changes',
    ])
      expect(conventionalHeader(bad)).toBe(false);
  });
});

describe('engine image trust root', () => {
  it('ships the same Supabase CA the release tooling pins', () => {
    const read = (path: string) => readFileSync(path);
    expect(
      read('services/engine/certs/supabase-prod-ca-2021.crt').equals(read('certificates/supabase-prod-ca-2021.crt')),
    ).toBe(true);
  });
});
