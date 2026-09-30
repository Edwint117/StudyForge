import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { ConfigError, loadRuntimeConfig } from '../../packages/config/src/index.js';
import { fixture } from '../../packages/config/src/fixtures.test-helper.js';
import { runCli } from '../env/cli.js';

runCli(import.meta.url, async () => {
  const mode = process.argv[2];
  if (process.argv.length !== 3 || !['dev', 'production', 'fixture'].includes(mode ?? ''))
    throw new ConfigError(['CLI_OPTIONS']);
  const testing = mode === 'fixture';
  const config = testing
    ? fixture()
    : loadRuntimeConfig(
        mode === 'production' ? '.env.production' : '.env.local',
        mode === 'production' ? 'production' : 'local',
      );
  const env = { ...process.env, ...config, NEXT_TELEMETRY_DISABLED: '1' };
  const run = (args: string[]) =>
    new Promise<void>((accept, reject) => {
      const child = spawn(process.execPath, [resolve('apps/web/node_modules/next/dist/bin/next'), ...args], {
        cwd: resolve('apps/web'),
        env,
        stdio: 'inherit',
        windowsHide: true,
      });
      const stop = () => child.kill();
      process.once('SIGINT', stop);
      process.once('SIGTERM', stop);
      child.once('error', () => reject(new ConfigError(['WEB_PROCESS'], 'web_launch_failed')));
      child.once('exit', (code) => {
        process.off('SIGINT', stop);
        process.off('SIGTERM', stop);
        if (code === 0) accept();
        else reject(new ConfigError(['WEB_PROCESS'], 'web_process_failed'));
      });
    });
  if (testing) {
    console.log('Browser-test server uses generated fixtures only; no real environment files are loaded.');
    await run(['build']);
  }
  await run([
    mode === 'dev' ? 'dev' : 'start',
    '--hostname',
    '127.0.0.1',
    '--port',
    testing ? '3100' : String(new URL(config.APP_URL).port || '3000'),
  ]);
});
