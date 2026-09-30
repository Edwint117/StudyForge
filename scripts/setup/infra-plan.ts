import { resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { readEnvFile, ConfigError } from '../../packages/config/src/index.js';
import { gcloud } from '../env/process.js';
import { runCli } from '../env/cli.js';

runCli(import.meta.url, async () => {
  if (process.argv.length !== 2) throw new ConfigError(['CLI_OPTIONS']);
  const config = readEnvFile('.env.production');
  if (!config.TF_STATE_BUCKET) throw new ConfigError(['TF_STATE_BUCKET']);
  const token = (await gcloud(['auth', 'print-access-token'])).trim();
  const env = { ...process.env, GOOGLE_OAUTH_ACCESS_TOKEN: token, TF_IN_AUTOMATION: '1' };
  const binary = process.platform === 'win32' ? resolve('.tools/terraform/terraform.exe') : 'terraform';
  const run = (args: string[]) =>
    new Promise<void>((accept, reject) => {
      const child = spawn(binary, ['-chdir=infra/terraform/envs/prod', ...args], {
        env,
        stdio: 'inherit',
        windowsHide: true,
      });
      child.once('error', () => reject(new ConfigError(['TERRAFORM'])));
      child.once('exit', (code) => (code === 0 ? accept() : reject(new ConfigError(['TERRAFORM']))));
    });
  await run([
    'init',
    '-input=false',
    `-backend-config=bucket=${config.TF_STATE_BUCKET}`,
    '-backend-config=prefix=prod',
  ]);
  await run(['plan', '-input=false', '-var-file=.env.auto.tfvars.json', '-out=foundation.tfplan']);
  console.log('Saved infrastructure plan. No Terraform apply or production runtime deployment performed.');
});
