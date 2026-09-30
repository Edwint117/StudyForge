import { execFileSync, spawn } from 'node:child_process';
import { createWriteStream, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { delimiter, dirname, join, resolve } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { z } from 'zod';
import { ConfigError } from '../../packages/config/src/index.js';

/**
 * Shared pieces of the local delivery pipeline (ADR-0017): the verification report, the guard that decides whether a
 * report still covers a commit, a stage runner that keeps tool output in .cache (never in the report), and small
 * helpers for git, prompts and Terraform.
 */

export const REPORT_JSON = 'docs/verify/latest.json';
export const REPORT_MD = 'docs/verify/latest.md';
export const LOG_DIR = '.cache/verify';
const REPORT_DIR_PREFIX = 'docs/verify/';

export const stageResultSchema = z
  .object({
    id: z.string(),
    title: z.string(),
    // pass/fail/skip are results; `na` means "nothing exists to run yet" and must carry a reason.
    outcome: z.enum(['pass', 'fail', 'skip', 'na']),
    seconds: z.number(),
    note: z.string(),
  })
  .strict();
export const reportSchema = z
  .object({
    schema: z.literal(1),
    kind: z.enum(['verify', 'nightly']),
    commit: z.string().regex(/^[0-9a-f]{40}$/),
    tree: z.string().regex(/^[0-9a-f]{40}$/),
    branch: z.string(),
    dirty: z.boolean(),
    partial: z.boolean(),
    startedAt: z.string(),
    finishedAt: z.string(),
    stages: z.array(stageResultSchema),
  })
  .strict();
export type StageResult = z.infer<typeof stageResultSchema>;
export type Report = z.infer<typeof reportSchema>;

export function overall(report: Pick<Report, 'stages' | 'partial' | 'dirty'>): 'pass' | 'fail' | 'incomplete' {
  if (report.stages.some((s) => s.outcome === 'fail')) return 'fail';
  if (report.partial || report.dirty || report.stages.some((s) => s.outcome === 'skip')) return 'incomplete';
  return 'pass';
}

export interface GuardInput {
  report: Report;
  target: string; // full SHA the merge/deploy would ship
  changedSinceReport: string[]; // files that differ between report.commit and target
  now: Date;
  maxAgeHours?: number;
}

/** A report covers a commit when it passed cleanly for that commit, or for an ancestor differing only in reports. */
export function assessReport({ report, target, changedSinceReport, now, maxAgeHours = 72 }: GuardInput): string[] {
  const problems: string[] = [];
  const state = overall(report);
  if (report.kind !== 'verify') problems.push('the report is not a verify report');
  if (state !== 'pass') problems.push(`verification is ${state}, not pass`);
  if (report.dirty) problems.push('verification ran on a dirty working tree');
  if (report.partial) problems.push('only a subset of stages ran');
  const stray = changedSinceReport.filter((file) => !file.startsWith(REPORT_DIR_PREFIX));
  if (report.commit !== target && stray.length > 0)
    problems.push(`stale: ${stray.length} file(s) changed since the verified commit (first: ${stray[0]})`);
  const age = (now.getTime() - Date.parse(report.finishedAt)) / 3_600_000;
  if (!(age >= -0.1 && age <= maxAgeHours))
    problems.push(`report is older than ${maxAgeHours}h or dated in the future`);
  return problems;
}

export function git(...args: string[]): string {
  return execFileSync('git', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true }).trim();
}
export function gitOk(...args: string[]): boolean {
  try {
    git(...args);
    return true;
  } catch {
    return false;
  }
}
export function headInfo() {
  return {
    commit: git('rev-parse', 'HEAD'),
    tree: git('rev-parse', 'HEAD^{tree}'),
    branch: git('rev-parse', '--abbrev-ref', 'HEAD'),
    // Untracked files count: a stray file can change what a build or test actually exercises.
    dirty: git('status', '--porcelain', '--untracked-files=normal', '--', '.', ':(exclude)docs/verify').length > 0,
  };
}

export function readReport(path = REPORT_JSON): Report {
  if (!existsSync(path)) throw new ConfigError(['VERIFY_REPORT'], 'no_verify_report_run_pnpm_verify');
  const parsed = reportSchema.safeParse(JSON.parse(readFileSync(path, 'utf8')));
  if (!parsed.success) throw new ConfigError(['VERIFY_REPORT'], 'verify_report_malformed');
  return parsed.data;
}

/** Load the committed report, then judge it against `target` (default HEAD). Returns the problems (empty = ok). */
export function guardTarget(target = 'HEAD', source = REPORT_JSON): { problems: string[]; report?: Report } {
  let report: Report;
  try {
    report = readReport(source);
  } catch (error) {
    return { problems: [error instanceof ConfigError ? error.message : 'report_unreadable'] };
  }
  const full = git('rev-parse', target);
  if (!gitOk('cat-file', '-e', `${report.commit}^{commit}`))
    return { problems: ['the verified commit no longer exists in this repository'], report };
  const changed = git('diff', '--name-only', report.commit, full).split('\n').filter(Boolean);
  return { problems: assessReport({ report, target: full, changedSinceReport: changed, now: new Date() }), report };
}

export function renderReport(report: Report): string {
  const state = overall(report);
  const icon = { pass: 'PASS', fail: 'FAIL', skip: 'SKIP', na: 'N/A' } as const;
  const rows = report.stages.map((s) => `| ${s.id} | ${icon[s.outcome]} | ${s.seconds.toFixed(0)}s | ${s.note} |`);
  return [
    `# ${report.kind === 'verify' ? 'Verification' : 'Nightly'} report: ${state.toUpperCase()}`,
    '',
    `- Commit: \`${report.commit}\``,
    `- Tree: \`${report.tree}\``,
    `- Branch: \`${report.branch}\``,
    `- Working tree: ${report.dirty ? 'DIRTY (this report cannot gate a merge)' : 'clean'}`,
    `- Scope: ${report.partial ? 'PARTIAL (only some stages ran; cannot gate a merge)' : 'all stages'}`,
    `- Started: ${report.startedAt}`,
    `- Finished: ${report.finishedAt}`,
    '',
    '| Stage | Result | Time | Note |',
    '|---|---|---|---|',
    ...rows,
    '',
    'Tool output is kept in `.cache/verify/` (ignored by git); this report holds outcomes only.',
    'A report-only commit may follow this run if its diff touches nothing outside `docs/verify/` (ADR-0017).',
    '',
  ].join('\n');
}

export function writeReport(report: Report, jsonPath = REPORT_JSON, mdPath = REPORT_MD): void {
  mkdirSync(dirname(jsonPath), { recursive: true });
  writeFileSync(jsonPath, JSON.stringify(report, null, 2) + '\n');
  writeFileSync(mdPath, renderReport(report));
}

// ---- tools ---------------------------------------------------------------------------------------------------------

const LOCAL_BIN = [
  process.env.USERPROFILE ? join(process.env.USERPROFILE, '.local', 'bin') : '',
  process.env.LOCALAPPDATA
    ? join(process.env.LOCALAPPDATA, 'Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe')
    : '',
  resolve('.tools/uv'),
  resolve('.tools/terraform'),
].filter(Boolean);
/** Environment for child tools: adds the per-user tool directories the desktop shell may not have inherited. */
export function toolEnv(extra: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  const key = Object.keys(process.env).find((k) => k.toUpperCase() === 'PATH') ?? 'PATH';
  return { ...process.env, [key]: [...LOCAL_BIN, process.env[key] ?? ''].join(delimiter), ...extra };
}

export interface RunOptions {
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  timeoutMs?: number;
  log?: string; // file receiving stdout+stderr
  stdin?: string;
  inherit?: boolean; // stream to the console instead (interactive tools, Terraform plans)
}
/** Run one fixed command line through the shell (Windows needs it for .cmd shims). Never interpolate user input. */
export function run(commandLine: string, options: RunOptions = {}): Promise<{ code: number; tail: string }> {
  return new Promise((accept) => {
    // nosemgrep: javascript.lang.security.detect-child-process.detect-child-process, javascript.lang.security.audit.spawn-shell-true.spawn-shell-true -- callers pass fixed command strings from this repo (never user or network input); Windows needs the shell for .cmd shims
    const child = spawn(commandLine, {
      cwd: options.cwd ?? process.cwd(),
      env: options.env ?? toolEnv(),
      shell: true,
      windowsHide: true,
      stdio: [
        options.stdin === undefined ? 'ignore' : 'pipe',
        options.inherit ? 'inherit' : 'pipe',
        options.inherit ? 'inherit' : 'pipe',
      ],
    });
    let tail = '';
    let logStream: ReturnType<typeof createWriteStream> | undefined;
    if (options.log) {
      mkdirSync(dirname(options.log), { recursive: true });
      logStream = createWriteStream(options.log, { flags: 'a' });
    }
    const sink = (chunk: Buffer) => {
      logStream?.write(chunk);
      tail = (tail + chunk.toString('utf8')).slice(-4000);
    };
    child.stdout?.on('data', sink);
    child.stderr?.on('data', sink);
    if (options.stdin !== undefined) child.stdin?.end(options.stdin);
    const timer = setTimeout(() => {
      tail += '\n[timed out]';
      child.kill();
    }, options.timeoutMs ?? 900_000);
    child.on('error', () => {
      clearTimeout(timer);
      logStream?.end();
      accept({ code: 127, tail: 'failed to start' });
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      logStream?.end();
      accept({ code: code ?? 1, tail });
    });
  });
}

export async function haveTool(name: string): Promise<boolean> {
  const finder = process.platform === 'win32' ? 'where' : 'command -v';
  return (await run(`${finder} ${name}`)).code === 0;
}

export type StageOutcome = { outcome: StageResult['outcome']; note: string };
export interface Stage {
  id: string;
  title: string;
  run: (ctx: { log: (name: string) => string }) => Promise<StageOutcome>;
}
export async function runStages(stages: Stage[], say: (line: string) => void = console.log): Promise<StageResult[]> {
  const results: StageResult[] = [];
  for (const stage of stages) {
    const started = Date.now();
    say(`> ${stage.id}: ${stage.title}`);
    let result: StageOutcome;
    try {
      result = await stage.run({ log: (name) => join(LOG_DIR, `${stage.id}-${name}.log`) });
    } catch {
      result = { outcome: 'fail', note: 'stage crashed before finishing' };
    }
    const seconds = (Date.now() - started) / 1000;
    say(`  ${result.outcome.toUpperCase()} (${seconds.toFixed(0)}s) ${result.note}`);
    results.push({ id: stage.id, title: stage.title, seconds, ...result });
  }
  return results;
}
/** Run several commands in order, stopping at the first failure. Logs to .cache; returns a short note. */
export async function sequence(
  steps: { label: string; command: string; cwd?: string; env?: NodeJS.ProcessEnv }[],
  ctx: { log: (name: string) => string },
  timeoutMs = 900_000,
): Promise<StageOutcome> {
  for (const step of steps) {
    const log = ctx.log(step.label.replace(/[^a-z0-9]+/gi, '-'));
    const result = await run(step.command, {
      ...(step.cwd ? { cwd: step.cwd } : {}),
      ...(step.env ? { env: step.env } : {}),
      log,
      timeoutMs,
    });
    if (result.code !== 0) {
      const last = result.tail.trim().split('\n').slice(-3).join(' | ').slice(0, 300);
      return { outcome: 'fail', note: `${step.label} failed (exit ${result.code}); see ${log}. Last output: ${last}` };
    }
  }
  return { outcome: 'pass', note: steps.map((s) => s.label).join(', ') };
}

// ---- prompts and Terraform -----------------------------------------------------------------------------------------

export async function confirmTyped(expected: string, question: string): Promise<boolean> {
  if (!process.stdin.isTTY) return false;
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  try {
    return (await rl.question(`${question}\nType "${expected}" to continue: `)).trim() === expected;
  } finally {
    rl.close();
  }
}

export function terraformBinary(): string {
  return process.platform === 'win32' ? resolve('.tools/terraform/terraform.exe') : 'terraform';
}
export const TF_DIR = 'infra/terraform/envs/prod';
export function terraform(
  args: string[],
  env: NodeJS.ProcessEnv,
  capture = false,
): Promise<{ code: number; tail: string }> {
  return new Promise((accept) => {
    const child = spawn(terraformBinary(), [`-chdir=${TF_DIR}`, ...args], {
      env,
      stdio: ['ignore', capture ? 'pipe' : 'inherit', capture ? 'pipe' : 'inherit'],
      windowsHide: true,
    });
    const chunks: Buffer[] = [];
    child.stdout?.on('data', (c: Buffer) => chunks.push(c));
    child.once('error', () => accept({ code: 127, tail: '' }));
    child.once('close', (code) => accept({ code: code ?? 1, tail: Buffer.concat(chunks).toString('utf8') }));
  });
}
