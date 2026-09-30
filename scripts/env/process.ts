import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { ConfigError } from '../../packages/config/src/index.js';

export function command(command: string, args: string[], input?: string, timeout = 30_000): Promise<string> {
  return new Promise((accept, reject) => {
    // No shell; stdin carries secret material. Neither stream is ever forwarded to the console.
    // nosemgrep: javascript.lang.security.detect-child-process.detect-child-process -- repo-controlled executables, argv array, no shell
    const child = spawn(command, args, { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
    const chunks: Buffer[] = [];
    let size = 0;
    let failed = false;
    let diagnostic = '';
    const fail = () => {
      if (failed) return;
      failed = true;
      child.kill();
      const code = /billing.*disabled|billing.*closed|billing.*not enabled|billing.*not.*active/i.test(diagnostic)
        ? 'billing_not_enabled'
        : /PERMISSION_DENIED|permission denied|does not have permission|HTTPError 403/i.test(diagnostic)
          ? 'permission_denied'
          : /unrecognized arguments|invalid choice|Invalid command|Invalid argument/i.test(diagnostic)
            ? 'invalid_cli_arguments'
            : /SERVICE_DISABLED|has not been used|API.*disabled/i.test(diagnostic)
              ? 'api_disabled'
              : /NOT_FOUND|not found|cannot find/i.test(diagnostic)
                ? 'not_found'
                : 'command_failed';
      reject(new ConfigError(['SUBPROCESS'], code));
    };
    const timer = setTimeout(fail, timeout);
    child.on('error', fail);
    child.stdin.on('error', fail);
    child.stdout.on('data', (chunk: Buffer) => {
      size += chunk.length;
      if (size > 5_000_000) fail();
      else chunks.push(chunk);
    });
    child.stderr.on('data', (chunk: Buffer) => {
      // Retain only for fixed-category classification; never print or propagate vendor text.
      if (diagnostic.length < 16384) diagnostic += chunk.toString('utf8').slice(0, 16384 - diagnostic.length);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) fail();
      else if (!failed) accept(Buffer.concat(chunks).toString('utf8'));
    });
    child.stdin.end(input);
  });
}
export function gcloudCommand(root = process.cwd()): { executable: string; prefix: string[] } {
  const sdk = resolve(root, '.tools/google-cloud-sdk');
  const python = resolve(sdk, 'platform/bundledpython/python.exe');
  if (process.platform === 'win32') {
    if (!existsSync(python)) throw new ConfigError(['GCLOUD_CLI'], 'tool_missing');
    return { executable: python, prefix: [resolve(sdk, 'lib/gcloud.py')] };
  }
  return { executable: 'gcloud', prefix: [] };
}
export async function gcloud(args: string[], input?: string): Promise<string> {
  const binary = gcloudCommand();
  return command(binary.executable, [...binary.prefix, ...args, '--quiet'], input, 120_000);
}
export function supabase(args: string[]): Promise<string> {
  return command(process.execPath, [resolve('node_modules/supabase/dist/supabase.js'), ...args]);
}
