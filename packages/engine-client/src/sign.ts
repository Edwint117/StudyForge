import { createHmac, randomUUID } from 'node:crypto';
import { z } from 'zod';

const inputSchema = z
  .object({
    path: z.enum(['/wake', '/rpc/sympy-equivalent', '/rpc/run-code']),
    body: z.string(),
    secret: z.string().min(32),
    timestamp: z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER),
    nonce: z.uuid().regex(/^[0-9a-f-]+$/),
  })
  .strict();

/** Server-only: send the returned body bytes unchanged; never reserialize them. */
export function signEngineRequest(input: {
  path: '/wake' | '/rpc/sympy-equivalent' | '/rpc/run-code';
  body: string;
  secret: string;
  timestamp?: number;
  nonce?: string;
}) {
  const parsed = inputSchema.safeParse({
    timestamp: Math.floor(Date.now() / 1000),
    nonce: randomUUID(),
    ...input,
  });
  // Zod issues could contain secret material: expose only a fixed diagnostic.
  if (!parsed.success) throw new Error('Invalid engine signing input');
  const { path, body, secret, timestamp, nonce } = parsed.data;
  const bytes = Buffer.from(body, 'utf8');
  if (bytes.length > 1_048_576) throw new Error('Engine request body too large');
  const scope = path === '/wake' ? 'wake' : 'rpc';
  const prefix = `studyforge-engine-v1\n${scope}\nPOST\n${path}\n${timestamp}\n${nonce}\n`;
  const signature = createHmac('sha256', secret).update(prefix).update(bytes).digest('hex');
  return {
    body: bytes,
    headers: {
      'content-type': 'application/json',
      'x-engine-timestamp': String(timestamp),
      'x-engine-nonce': nonce,
      'x-engine-signature': `v1=${signature}`,
    },
  };
}
