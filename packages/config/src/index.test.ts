import { describe, expect, it } from 'vitest';
import { ConfigError, parseEnvText, validateEnvironment } from './index.js';
import { fixture } from './fixtures.test-helper.js';

describe('strict environment contract', () => {
  it.each(['local', 'production'] as const)('accepts the complete %s fixture', (environment) => {
    expect(validateEnvironment(fixture(environment), environment).invalid).toEqual([]);
  });
  it('accepts an empty SANDBOX_URL in production (ADR-0020 defers the sandbox; this is real production state)', () => {
    expect(validateEnvironment({ ...fixture('production'), SANDBOX_URL: '' }, 'production').invalid).toEqual([]);
  });
  it('distinguishes incomplete bootstrap provisioning from invalid human credentials', () => {
    const input = {
      ...fixture('production'),
      ENGINE_DATABASE_URL: '',
      ENGINE_URL: '',
      GCP_DEPLOY_SERVICE_ACCOUNT: '',
      ANTHROPIC_API_KEY: '',
    };
    const bootstrap = validateEnvironment(input, 'production', 'bootstrap');
    expect(bootstrap.pending).toEqual(
      expect.arrayContaining(['ENGINE_DATABASE_URL', 'ENGINE_URL', 'GCP_DEPLOY_SERVICE_ACCOUNT']),
    );
    expect(bootstrap.invalid).toEqual(['ANTHROPIC_API_KEY']);
    expect(validateEnvironment(input, 'production').invalid).toEqual(
      expect.arrayContaining(['ENGINE_DATABASE_URL', 'ENGINE_URL', 'GCP_DEPLOY_SERVICE_ACCOUNT']),
    );
  });
  it('rejects unknown fields without reflecting attacker-controlled names', () => {
    expect(() => validateEnvironment({ ...fixture(), 'secret-valued-unknown-name': 'hidden' }, 'local')).toThrow(
      'UNKNOWN_VARIABLE',
    );
    try {
      validateEnvironment({ ...fixture(), 'secret-valued-unknown-name': 'hidden' }, 'local');
    } catch (e) {
      expect(String(e)).not.toContain('secret-valued');
    }
  });
  it('forbids production Supabase in local configuration and weak cloud DB TLS', () => {
    expect(
      validateEnvironment({ ...fixture(), NEXT_PUBLIC_SUPABASE_URL: 'https://example.supabase.co' }, 'local').invalid,
    ).toContain('NEXT_PUBLIC_SUPABASE_URL');
    const prod = fixture('production');
    expect(
      validateEnvironment(
        { ...prod, ENGINE_DATABASE_URL: prod.ENGINE_DATABASE_URL.replace('verify-full', 'require') },
        'production',
      ).invalid,
    ).toContain('ENGINE_DATABASE_URL');
  });
  it('rejects cloud poll mode, public push on localhost, and mismatched VAPID pair', () => {
    expect(validateEnvironment({ ...fixture('production'), ENGINE_POLL_MODE: '1' }, 'production').invalid).toContain(
      'ENGINE_POLL_MODE',
    );
    expect(validateEnvironment({ ...fixture(), CALENDAR_PUSH_ENABLED: 'true' }, 'local').invalid).toContain(
      'CALENDAR_PUSH_ENABLED',
    );
    expect(
      validateEnvironment({ ...fixture(), VAPID_PRIVATE_KEY: fixture().VAPID_PRIVATE_KEY }, 'local').invalid,
    ).toContain('NEXT_PUBLIC_VAPID_PUBLIC_KEY');
  });
  it('rejects credential-bearing API URLs, swapped Supabase roles and missing sourcemap org', () => {
    const jwt = [
      'eyJ0ZXN0Ijp0cnVlfQ',
      Buffer.from(JSON.stringify({ role: 'service_role' })).toString('base64url'),
      'fixture',
    ].join('.');
    const invalid = validateEnvironment(
      {
        ...fixture(),
        NEXT_PUBLIC_SUPABASE_ANON_KEY: jwt,
        SENTRY_AUTH_TOKEN: 'fixture',
        NEXT_PUBLIC_SUPABASE_URL: 'http://secret@127.0.0.1:54321',
      },
      'local',
    ).invalid;
    expect(invalid).toEqual(
      expect.arrayContaining(['NEXT_PUBLIC_SUPABASE_ANON_KEY', 'NEXT_PUBLIC_SUPABASE_URL', 'SENTRY_ORG']),
    );
  });
  it('does not execute shell expansions and rejects duplicate/malformed/multiline entries', () => {
    expect(parseEnvText('VALUE="$(whoami) `echo nothing`"').VALUE).toBe('$(whoami) `echo nothing`');
    expect(() => parseEnvText('X=first\nX=second')).toThrow(ConfigError);
    expect(() => parseEnvText('not an assignment')).toThrow(ConfigError);
    expect(() => parseEnvText('X="line\\nsecond"')).toThrow(ConfigError);
  });
});
