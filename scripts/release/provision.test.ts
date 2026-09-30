import { describe, expect, it } from 'vitest';
import { validateEnvironment } from '../../packages/config/src/index.js';
import { fixture } from '../../packages/config/src/fixtures.test-helper.js';
import { engineUrl, IMAGE_CA_PATH } from './provision-prod-engine.js';

describe('production engine connection string', () => {
  const password = 'a'.repeat(72);
  const url = engineUrl('abcdefghijklmnopqrst', 'aws-0-us-east-2.pooler.supabase.com', password);
  it('uses the worker role on the session pooler with verify-full and the pinned CA', () => {
    const parsed = new URL(url);
    expect(parsed.username).toBe('engine_worker.abcdefghijklmnopqrst');
    expect(parsed.port).toBe('5432');
    expect(parsed.searchParams.get('sslmode')).toBe('verify-full');
    expect(parsed.searchParams.get('sslrootcert')).toBe(IMAGE_CA_PATH);
  });
  it('passes the config catalog validation for production', () => {
    const base = fixture('production');
    const result = validateEnvironment({ ...base, ENGINE_DATABASE_URL: url }, 'production');
    expect(result.invalid).not.toContain('ENGINE_DATABASE_URL');
  });
});
