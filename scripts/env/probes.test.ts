import { describe, expect, it, vi } from 'vitest';
import { connectivity } from './probes.js';
import { ProbeError, readOnlyGet } from './http.js';
import { ConfigError } from '../../packages/config/src/index.js';
import { fixture } from '../../packages/config/src/fixtures.test-helper.js';
import { pushSecrets } from './push-secrets.js';

describe('read-only service validation', () => {
  it('never follows a redirect or prints an error response containing credentials', async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response('sensitive-body', { status: 302, headers: { Location: 'https://untrusted.invalid' } }),
      );
    await expect(readOnlyGet('https://api.anthropic.com/v1/models', {}, fetcher)).rejects.toThrow('redirect_rejected');
    expect(fetcher.mock.calls[0]?.[1]?.method).toBe('GET');
    expect(fetcher.mock.calls[0]?.[1]?.redirect).toBe('manual');
    fetcher.mockResolvedValue(new Response('secret-token-response', { status: 401 }));
    await expect(readOnlyGet('https://api.anthropic.com/v1/models', {}, fetcher)).rejects.toThrow(/^auth_rejected$/);
  });
  it('bounds response size and redacts transport errors', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('x'.repeat(1_000_001)));
    await expect(readOnlyGet('https://api.anthropic.com/v1/models', {}, fetcher)).rejects.toThrow('response_too_large');
    fetcher.mockRejectedValue(new Error('credentials echoed here'));
    await expect(readOnlyGet('https://api.anthropic.com/v1/models', {}, fetcher)).rejects.toThrow(/^network_or_tls$/);
  });
  it('checks project key pairing without sending events, rejects wrong keys, and skips invalid hosts', async () => {
    const config = fixture();
    const get = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('posthog')) return { id: 1, api_token: 'wrong-key' };
      if (url.includes('langfuse')) return { data: [{}] };
      if (url.includes('anthropic')) return { data: [{ id: 'fixture' }] };
      return {};
    });
    const rows = await connectivity(config, 'local', ['LANGFUSE_HOST'], { get });
    expect(rows.find((r) => r.check.startsWith('PostHog'))?.detail).toBe('auth_rejected');
    expect(get.mock.calls.some(([url]) => String(url).includes('langfuse'))).toBe(false);
    expect(JSON.stringify(rows)).not.toContain(config.ANTHROPIC_API_KEY);
  });
  it('rejects malicious DB hosts before passing passwords to a database driver', async () => {
    const config = fixture('production');
    const database = vi.fn();
    const get = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/pooler'))
        return [
          {
            db_host: 'attacker.invalid',
            db_port: 5432,
            db_user: `postgres.${config.SUPABASE_PROJECT_REF}`,
            db_name: 'postgres',
            pool_mode: 'session',
          },
        ];
      throw new ProbeError('service_error');
    });
    const rows = await connectivity(config, 'production', [], {
      get,
      database,
      cloud: vi.fn().mockRejectedValue(new Error('hidden')),
    });
    expect(database).not.toHaveBeenCalled();
    expect(rows.find((r) => r.check === 'Supabase DB password / TLS')?.detail).toBe('invalid_response');
  });
  it('passes secrets through stdin only and excludes operator credentials from cloud upload', async () => {
    const config = fixture('production');
    const invoke = vi.fn().mockResolvedValue('suppressed');
    const result = await pushSecrets(config, invoke);
    expect(result.added).toBeGreaterThan(5);
    const adds = invoke.mock.calls.filter(([args]) => (args as string[]).includes('add'));
    expect(adds.length).toBe(result.added);
    for (const [args, stdin] of adds) {
      expect(args).toContain('--data-file=-');
      expect(args.join(' ')).not.toContain(stdin);
    }
    for (const [args] of invoke.mock.calls) {
      expect(args.join(' ')).not.toContain('sf-supabase-access-token');
      expect(args.join(' ')).not.toContain('sf-supabase-db-password');
    }
  });
  it('does not mint a new version when the latest one already matches, and reports missing slots', async () => {
    const config = fixture('production');
    const same = vi
      .fn()
      .mockImplementation(async (args: string[]) => (args.includes('access') ? config.ENGINE_RPC_SECRET : ''));
    expect((await pushSecrets(config, same)).unchanged).toBeGreaterThanOrEqual(1);
    const noSlot = vi.fn().mockImplementation(async (args: string[]) => {
      if (args.includes('add') && args.includes('sf-sentry-dsn')) throw new ConfigError(['SUBPROCESS'], 'not_found');
      return 'other';
    });
    expect((await pushSecrets(config, noSlot)).missingSlots).toEqual(['sf-sentry-dsn']);
  });
});
