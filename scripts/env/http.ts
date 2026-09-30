import { z } from 'zod';

export class ProbeError extends Error {
  constructor(
    public readonly code:
      | 'auth_rejected'
      | 'permission_denied'
      | 'rate_limited'
      | 'service_error'
      | 'network_or_tls'
      | 'redirect_rejected'
      | 'invalid_response'
      | 'response_too_large'
      | 'database_certificate_rejected'
      | 'database_unreachable'
      | 'database_connection_failed',
  ) {
    super(code);
  }
}
export async function readOnlyGet(
  url: string,
  headers: Record<string, string> = {},
  fetcher: typeof fetch = fetch,
): Promise<unknown> {
  try {
    const response = await fetcher(url, {
      method: 'GET',
      headers,
      redirect: 'manual',
      signal: AbortSignal.timeout(12_000),
    });
    if (response.status >= 300 && response.status < 400) throw new ProbeError('redirect_rejected');
    if (response.status === 401) throw new ProbeError('auth_rejected');
    if (response.status === 403) throw new ProbeError('permission_denied');
    if (response.status === 429) throw new ProbeError('rate_limited');
    if (!response.ok) throw new ProbeError('service_error');
    const chunks: Uint8Array[] = [];
    let length = 0;
    if (!response.body) throw new ProbeError('invalid_response');
    const reader = response.body.getReader();
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      length += next.value.length;
      if (length > 1_000_000) {
        await reader.cancel();
        throw new ProbeError('response_too_large');
      }
      chunks.push(next.value);
    }
    try {
      return JSON.parse(Buffer.concat(chunks).toString('utf8')) as unknown;
    } catch {
      throw new ProbeError('invalid_response');
    }
  } catch (error) {
    if (error instanceof ProbeError) throw error;
    throw new ProbeError('network_or_tls');
  }
}
export function project<T>(input: unknown, schema: z.ZodType<T>, keys: readonly string[]): T {
  // Vendor metadata contains unrelated fields. Project only named fields, then apply a strict schema.
  if (typeof input !== 'object' || input === null || Array.isArray(input)) throw new ProbeError('invalid_response');
  const object = input as Record<string, unknown>;
  const result = schema.safeParse(
    Object.fromEntries(keys.filter((key) => key in object).map((key) => [key, object[key]])),
  );
  if (!result.success) throw new ProbeError('invalid_response');
  return result.data;
}
