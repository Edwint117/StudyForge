import { describe, expect, it } from 'vitest';
import { desiredAuth, drift } from './supabase-settings.js';

describe('supabase settings drift', () => {
  const wanted = desiredAuth({
    APP_URL: 'https://app.example.test',
    ALLOWED_ORIGINS: 'https://app.example.test, http://localhost:3001',
  });
  it('derives redirect allow-list entries from the allowed origins', () => {
    expect(wanted.site_url).toBe('https://app.example.test');
    expect(wanted.uri_allow_list).toBe('https://app.example.test/**,http://localhost:3001/**');
  });
  it('reports differing keys, and keys the project does not expose, separately', () => {
    const result = drift(
      { site_url: 'https://app.example.test', password_min_length: 6 },
      { site_url: 'https://app.example.test', password_min_length: 8, hibp: true },
    );
    expect(result.differing).toEqual([['password_min_length', 8]]);
    expect(result.unknownKeys).toEqual(['hibp']);
  });
  it('never asks for weaker auth than the spec', () => {
    expect(wanted.password_min_length).toBe(8);
    expect(wanted.mailer_autoconfirm).toBe(false);
    expect(wanted.mfa_totp_enroll_enabled).toBe(true);
    expect(wanted.refresh_token_rotation_enabled).toBe(true);
  });
});
