import { describe, expect, it } from 'vitest';
import { parseEnvText, validateEnvironment } from '../../packages/config/src/index.js';
import { prepareText } from './prepare.js';

describe('generated VAPID keypair round-trips through validation', () => {
  it('never rejects the generated pair, even when the private key has a leading zero byte (~1/256 of keys)', () => {
    // A short loop is not enough to reliably hit the ~1/256 chance of a leading zero byte on this curve; 300
    // iterations makes the odds of never hitting it (255/256)^300 ≈ 0.0000... effectively zero, so this test
    // would have caught the real bug (getPrivateKey() not left-padding) essentially every time it ran.
    for (let i = 0; i < 300; i++) {
      const values = parseEnvText(prepareText('', 'local'));
      const result = validateEnvironment(values, 'local', 'bootstrap');
      expect(result.invalid, `iteration ${i}`).not.toContain('VAPID_PRIVATE_KEY');
      expect(result.invalid, `iteration ${i}`).not.toContain('NEXT_PUBLIC_VAPID_PUBLIC_KEY');
    }
  });
});
