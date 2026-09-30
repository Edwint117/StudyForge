import { describe, expect, it } from 'vitest';
import { parseEnvText, humanKeyMapping } from '../../packages/config/src/index.js';
import { updateEnvText, writePrivateFile } from './files.js';
import { mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { mergeKeyTexts } from './merge-keys.js';
import { prepareText, renderExample } from './prepare.js';
import { fixture } from '../../packages/config/src/fixtures.test-helper.js';

const toEnv = (input: Record<string, string>) =>
  Object.entries(input)
    .map(([key, value]) => updateEnvText('', { [key]: value }).trim())
    .join('\n');
describe('credential file transformations', () => {
  it('writes atomically with owner-only permissions and leaves identical content untouched', () => {
    const directory = mkdtempSync(join(tmpdir(), 'studyforge-env-test-'));
    const path = join(directory, 'synthetic.env');
    try {
      expect(writePrivateFile(path, 'SYNTHETIC=value\n')).toBe(true);
      const modified = statSync(path).mtimeMs;
      expect(writePrivateFile(path, 'SYNTHETIC=value\n')).toBe(false);
      expect(statSync(path).mtimeMs).toBe(modified);
      expect(readFileSync(path, 'utf8')).toBe('SYNTHETIC=value\n');
      if (process.platform === 'win32') {
        const script =
          '$acl=[System.IO.File]::GetAccessControl($env:SF_ENV_ACL_PATH); $sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User; $rules=$acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]); if (-not $acl.AreAccessRulesProtected -or $rules.Count -ne 1 -or $rules[0].IdentityReference -ne $sid -or $rules[0].AccessControlType -ne "Allow") { exit 1 }; "owner-only"';
        const output = execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], {
          env: { ...process.env, SF_ENV_ACL_PATH: path },
          encoding: 'utf8',
          windowsHide: true,
        });
        expect(output.trim()).toBe('owner-only');
      } else expect(statSync(path).mode & 0o777).toBe(0o600);
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
  it('preserves spaces, hashes, equals, quotes, backslashes and shell metacharacters exactly', () => {
    for (const value of [
      'space # equals=a',
      "single'quote",
      'double"quote',
      'back\\slash',
      '$(never-execute) `x`',
      'a\'b"c\\d',
    ]) {
      expect(
        parseEnvText(updateEnvText('SUPABASE_DB_PASSWORD=old\n', { SUPABASE_DB_PASSWORD: value })).SUPABASE_DB_PASSWORD,
      ).toBe(value);
    }
  });
  it('merges exact mappings, preserves local DB and generated secrets, and is idempotent', () => {
    const keys = Object.fromEntries(Object.keys(humanKeyMapping).map((key) => [key, `fixture-${key}`]));
    const local = fixture();
    const prod = fixture('production');
    const once = mergeKeyTexts(toEnv(keys), toEnv(local), toEnv(prod));
    const twice = mergeKeyTexts(toEnv(keys), once.local, once.production);
    expect(twice).toEqual(once);
    const l = parseEnvText(once.local);
    const p = parseEnvText(once.production);
    expect(l.SUPABASE_SERVICE_ROLE_KEY).toBe(local.SUPABASE_SERVICE_ROLE_KEY);
    expect(l.NEXT_PUBLIC_SUPABASE_URL).toBe(local.NEXT_PUBLIC_SUPABASE_URL);
    expect(p.NEXT_PUBLIC_SUPABASE_URL).toBe(keys.SUPABASE_URL);
    expect(l.NEXT_PUBLIC_SENTRY_DSN).toBe(keys.SENTRY_DSN);
    expect(p.CSRF_SECRET).toBe(prod.CSRF_SECRET);
    expect(l.ANTHROPIC_API_KEY).toBe(keys.ANTHROPIC_API_KEY);
    expect(l.BETTERSTACK_API_TOKEN).toBe(local.BETTERSTACK_API_TOKEN);
  });
  it('clears stale required values but leaves blank optional credentials untouched', () => {
    const local = { ...fixture(), DEEPGRAM_API_KEY: 'keep-optional' };
    const result = mergeKeyTexts('ANTHROPIC_API_KEY=\nDEEPGRAM_API_KEY=\n', toEnv(local), toEnv(fixture('production')));
    expect(parseEnvText(result.local).ANTHROPIC_API_KEY).toBe('');
    expect(parseEnvText(result.local).DEEPGRAM_API_KEY).toBe('keep-optional');
    expect(result.missing).toContain('ANTHROPIC_API_KEY');
  });
  it('rejects duplicates and unknown key names before changing either target', () => {
    expect(() => mergeKeyTexts('UNRECOGNIZED=hidden', '', '')).toThrow('invalid_key_names');
    expect(() => mergeKeyTexts('ANTHROPIC_API_KEY=a\nANTHROPIC_API_KEY=b', '', '')).toThrow('duplicate_assignment');
  });
  it('preparation preserves credentials and creates independent secrets once per environment', () => {
    const local = prepareText(renderExample(), 'local');
    const prod = prepareText(renderExample(), 'production');
    expect(prepareText(local, 'local')).toBe(local);
    expect(prepareText(prod, 'production')).toBe(prod);
    expect(parseEnvText(local).CSRF_SECRET).not.toBe(parseEnvText(prod).CSRF_SECRET);
    expect(parseEnvText(prod).ENGINE_URL).toBe('');
    expect(parseEnvText(prod).APP_URL).toBe('http://localhost:3001');
    expect(() => prepareText('VAPID_PRIVATE_KEY=only-one-half', 'local')).toThrow('incomplete_vapid_pair');
  });
});
