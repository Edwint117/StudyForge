import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { signEngineRequest } from './sign.js';

const rows = z
  .array(
    z
      .object({
        path: z.enum(['/wake', '/rpc/sympy-equivalent', '/rpc/run-code']),
        body: z.string(),
        secret: z.string(),
        timestamp: z.number(),
        nonce: z.string(),
        signature: z.string(),
      })
      .strict(),
  )
  .parse(JSON.parse(readFileSync(new URL('../fixtures/signatures.json', import.meta.url), 'utf8')));

describe('engine wire signatures', () => {
  for (const row of rows)
    it(`matches the Python-shared fixture for ${row.path}`, () => {
      const { signature, ...input } = row;
      const signed = signEngineRequest(input);
      expect(signed.headers['x-engine-signature']).toBe(signature);
      expect(signed.body).toEqual(Buffer.from(row.body, 'utf8'));
      expect(signEngineRequest({ ...input, body: `${input.body} ` }).headers['x-engine-signature']).not.toBe(signature);
      expect(signEngineRequest({ ...input, timestamp: input.timestamp + 1 }).headers['x-engine-signature']).not.toBe(
        signature,
      );
    });
  it('rejects invalid input without exposing credentials or input values', () => {
    const input = { path: '/wake' as const, body: '{}', secret: 'private-value' };
    expect(() => signEngineRequest(input)).toThrow('Invalid engine signing input');
    expect(() => signEngineRequest({ ...input, secret: 'x'.repeat(32), nonce: 'bad' })).toThrow(
      'Invalid engine signing input',
    );
    expect(() => signEngineRequest({ ...input, secret: 'x'.repeat(32), body: 'é'.repeat(524289) })).toThrow(
      'Engine request body too large',
    );
  });
  it('uses a new nonce for each retry', () => {
    const input = { path: '/wake' as const, body: '{}', secret: 'x'.repeat(32) };
    expect(signEngineRequest(input).headers['x-engine-nonce']).not.toBe(
      signEngineRequest(input).headers['x-engine-nonce'],
    );
  });
});
