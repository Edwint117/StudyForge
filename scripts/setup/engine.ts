import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { loadRuntimeConfig, ConfigError } from '../../packages/config/src/index.js';
import { runCli } from '../env/cli.js';

runCli(import.meta.url, async () => {
  const mode = process.argv[2];
  if (process.argv.length !== 3 || !['dev', 'test', 'integration'].includes(mode ?? ''))
    throw new ConfigError(['CLI_OPTIONS']);
  const env = { ...process.env };
  if (mode !== 'test') {
    const config = loadRuntimeConfig('.env.local', 'local');
    for (const key of [
      'APP_ENV',
      'ENGINE_DATABASE_URL',
      'ENGINE_RPC_SECRET',
      'ENGINE_WAKE_SECRET',
      'ENGINE_POLL_MODE',
    ] as const)
      env[key] = config[key];
  }
  const args =
    mode === 'dev'
      ? [
          '-m',
          'uvicorn',
          'engine.runtime:build_app',
          '--factory',
          '--host',
          '127.0.0.1',
          '--port',
          '8080',
          '--no-access-log',
          '--loop',
          'asyncio:SelectorEventLoop',
        ]
      : ['-m', 'pytest', ...(mode === 'integration' ? ['integration'] : ['tests'])];
  await new Promise<void>((accept, reject) => {
    const executable = resolve(
      `services/engine/.venv/${process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'}`,
    );
    const child = spawn(executable, args, {
      cwd: resolve('services/engine'),
      env,
      stdio: 'inherit',
      windowsHide: true,
    });
    const stop = () => child.kill();
    process.once('SIGINT', stop);
    process.once('SIGTERM', stop);
    child.once('error', () => reject(new ConfigError(['ENGINE_PROCESS'])));
    child.once('exit', (code) => {
      process.off('SIGINT', stop);
      process.off('SIGTERM', stop);
      if (code === 0) accept();
      else reject(new ConfigError(['ENGINE_PROCESS']));
    });
  });
});
