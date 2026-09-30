import { execFileSync, spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { ConfigError } from '../../packages/config/src/index.js';
import { runCli } from '../env/cli.js';

runCli(import.meta.url, () => {
  if (process.argv.length > 2) throw new ConfigError(['CLI_OPTIONS']);
  const directory = mkdtempSync(join(tmpdir(), 'studyforge-hook-test-'));
  const env = { ...process.env, GIT_INDEX_FILE: join(directory, 'index') };
  if (process.platform === 'win32') {
    const paths = Object.entries(env)
      .filter(([key]) => key.toLowerCase() === 'path')
      .map(([, value]) => value ?? '');
    for (const key of Object.keys(env)) if (key.toLowerCase() === 'path') delete env[key as keyof typeof env];
    const gitExec = execFileSync('git', ['--exec-path'], { encoding: 'utf8' }).trim();
    // Git adds its shell for real hooks; direct hook tests must do the same.
    Object.assign(env, { Path: [resolve(gitExec, '../../../bin'), ...paths].join(';') });
  }
  const git = (args: string[], input?: string) =>
    execFileSync('git', args, {
      env,
      encoding: 'utf8',
      input,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    }).trim();
  try {
    // A separate index leaves the user's staging area and checkout untouched.
    git(['read-tree', 'HEAD']);
    const synthetic = 'ghp_' + randomBytes(18).toString('hex');
    const blob = git(['hash-object', '-w', '--stdin'], `const syntheticToken = "${synthetic}";\n`);
    git(['update-index', '--add', '--cacheinfo', `100644,${blob},synthetic-secret-probe.txt`]);
    const result = spawnSync(
      process.execPath,
      [resolve('node_modules/lefthook/bin/index.js'), 'run', 'pre-commit', '--force'],
      { env, encoding: 'utf8', windowsHide: true, timeout: 30_000 },
    );
    const output = (result.stdout ?? '') + (result.stderr ?? '');
    if (result.status !== 1 || !output.includes('secret_detected_or_scanner_failed') || output.includes(synthetic))
      throw new ConfigError(['SECRET_HOOK'], 'negative_test_failed');
    // Prove this wasn't merely a broken scanner by checking the same index without the fixture.
    git(['update-index', '--force-remove', 'synthetic-secret-probe.txt']);
    const clean = spawnSync(
      process.execPath,
      [resolve('node_modules/lefthook/bin/index.js'), 'run', 'pre-commit', '--force'],
      { env, encoding: 'utf8', windowsHide: true, timeout: 30_000 },
    );
    if (clean.status !== 0) throw new ConfigError(['SECRET_HOOK'], 'clean_index_failed');
    console.log('Secret hook passed: synthetic credential rejected, clean index accepted, no credential output.');
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
