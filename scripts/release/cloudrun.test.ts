import { describe, expect, it } from 'vitest';
import { canaryUrlFor } from './cloudrun.js';

describe('canary tag URL', () => {
  it('prefixes the service host with the canary tag', () => {
    expect(canaryUrlFor('https://sf-engine-e6kq73zx2a-ue.a.run.app')).toBe(
      'https://canary---sf-engine-e6kq73zx2a-ue.a.run.app',
    );
  });
  it('refuses anything that is not an https run.app origin (no path, port, other host or http)', () => {
    for (const bad of [
      'http://x.a.run.app',
      'https://x.example.com',
      'https://x.a.run.app/health',
      'https://x.a.run.app:8443',
      '',
      'https://evil.com/.a.run.app',
    ])
      expect(canaryUrlFor(bad), bad).toBeUndefined();
  });
});
