import {
  closeSync,
  existsSync,
  lstatSync,
  openSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
  chmodSync,
} from 'node:fs';
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import { catalog, ConfigError, parseEnvText } from '../../packages/config/src/index.js';
import type { EnvKey } from '../../packages/config/src/index.js';

export function restrictFile(path: string): void {
  if (lstatSync(path).isSymbolicLink()) throw new ConfigError(['ENV_FILE'], 'symlink_not_allowed');
  try {
    if (process.platform !== 'win32') {
      chmodSync(path, 0o600);
      return;
    }
    // Windows PowerShell inherits PowerShell 7's incompatible module path in desktop sessions.
    // Use the framework ACL API directly instead of auto-loading Set-Acl's module.
    const script =
      '$ErrorActionPreference = "Stop"; $acl = [System.Security.AccessControl.FileSecurity]::new(); $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User; $acl.SetOwner($sid); $acl.SetAccessRuleProtection($true,$false); $rule = [System.Security.AccessControl.FileSystemAccessRule]::new($sid,"FullControl","Allow"); $acl.AddAccessRule($rule); [System.IO.File]::SetAccessControl($env:SF_ENV_ACL_PATH,$acl)';
    execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], {
      env: { ...process.env, SF_ENV_ACL_PATH: resolve(path) },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
      timeout: 15_000,
    });
  } catch {
    throw new ConfigError(['ENV_FILE'], 'owner_only_permissions_failed');
  }
}

export function encodeEnvValue(value: string): string {
  if (/[\r\n\0]/.test(value)) throw new ConfigError(['ENV_FILE'], 'multiline_value_not_allowed');
  if (/^[A-Za-z0-9_:/?@.%=+,-]*$/.test(value)) return value;
  if (!value.includes("'")) return `'${value}'`;
  if (!value.includes('"') && !value.includes('\\')) return `"${value}"`;
  if (!value.includes('`')) return '`' + value + '`';
  throw new ConfigError(['ENV_FILE'], 'unrepresentable_env_value');
}
export function updateEnvText(text: string, changes: Partial<Record<EnvKey, string>>): string {
  parseEnvText(text); // reject duplicate/malformed assignments before changing anything
  const remaining = new Map(Object.entries(changes));
  const lines = text
    .replace(/\r\n/g, '\n')
    .trimEnd()
    .split('\n')
    .map((line) => {
      const key = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=/.exec(line)?.[1];
      if (!key || !remaining.has(key)) return line;
      const value = remaining.get(key) ?? '';
      remaining.delete(key);
      return `${key}=${encodeEnvValue(value)}`;
    });
  for (const [key, value] of remaining) lines.push(`${key}=${encodeEnvValue(value)}`);
  const output = lines.join('\n') + '\n';
  const values = parseEnvText(output);
  for (const [key, value] of Object.entries(changes))
    if (values[key] !== value) throw new ConfigError(['ENV_FILE'], 'env_roundtrip_failed');
  return output;
}
export function writePrivateFile(path: string, text: string): boolean {
  let temp: string | undefined;
  try {
    if (existsSync(path)) {
      restrictFile(path);
      if (readFileSync(path, 'utf8') === text) return false;
    }
    temp = `${path}.${randomUUID()}.tmp`;
    closeSync(openSync(temp, 'wx', 0o600));
    restrictFile(temp);
    writeFileSync(temp, text, { encoding: 'utf8', mode: 0o600 });
    renameSync(temp, path);
    temp = undefined;
    return true;
  } catch (error) {
    if (error instanceof ConfigError) throw error;
    throw new ConfigError(['ENV_FILE'], 'private_write_failed');
  } finally {
    if (temp && existsSync(temp)) rmSync(temp);
  }
}
export function knownKeyNames(values: Record<string, string>): void {
  if (Object.keys(values).some((key) => !(key in catalog))) throw new ConfigError(['UNKNOWN_VARIABLE']);
}
