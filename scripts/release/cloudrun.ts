import { z } from 'zod';
import { ConfigError, type Config } from '../../packages/config/src/index.js';
import { gcloud } from '../env/process.js';

/** Cloud Run queries shared by deploy and rollback. All calls impersonate sf-deployer; no key files exist. */
export const SERVICE = 'sf-engine';
type Cfg = Pick<Config, 'GCP_PROJECT_ID' | 'GCP_REGION' | 'GCP_DEPLOY_SERVICE_ACCOUNT'>;

export function scope(config: Cfg): string[] {
  return [
    `--project=${config.GCP_PROJECT_ID}`,
    `--region=${config.GCP_REGION}`,
    `--impersonate-service-account=${config.GCP_DEPLOY_SERVICE_ACCOUNT}`,
  ];
}

const serviceSchema = z
  .object({
    status: z
      .object({
        url: z.string().optional(),
        traffic: z
          .array(
            z.object({
              revisionName: z.string().optional(),
              percent: z.number().optional(),
              tag: z.string().optional(),
            }),
          )
          .default([]),
      })
      .loose(),
  })
  .loose();
export interface Serving {
  url: string | undefined;
  revision: string | undefined; // the revision holding the most traffic
}
export async function serving(config: Cfg): Promise<Serving | undefined> {
  let raw: string;
  try {
    raw = await gcloud(['run', 'services', 'describe', SERVICE, ...scope(config), '--format=json']);
  } catch (error) {
    if (error instanceof ConfigError && error.message.includes('not_found')) return undefined;
    throw error;
  }
  const parsed = serviceSchema.parse(JSON.parse(raw));
  const top = [...parsed.status.traffic].sort((a, b) => (b.percent ?? 0) - (a.percent ?? 0))[0];
  return { url: parsed.status.url, revision: top?.revisionName };
}

const revisionSchema = z
  .object({
    metadata: z.object({ name: z.string(), creationTimestamp: z.string() }).loose(),
    spec: z
      .object({
        containers: z
          .array(
            z
              .object({
                image: z.string(),
                env: z.array(z.object({ name: z.string(), value: z.string().optional() }).loose()).default([]),
              })
              .loose(),
          )
          .min(1),
      })
      .loose(),
    status: z
      .object({ conditions: z.array(z.object({ type: z.string(), status: z.string() }).loose()).default([]) })
      .loose(),
  })
  .loose();
export interface Revision {
  name: string;
  created: string;
  image: string;
  release: string | undefined; // ENGINE_RELEASE the revision was deployed with
  ready: boolean;
}
export async function revisions(config: Cfg): Promise<Revision[]> {
  const raw = await gcloud(['run', 'revisions', 'list', `--service=${SERVICE}`, ...scope(config), '--format=json']);
  return z
    .array(revisionSchema)
    .parse(JSON.parse(raw))
    .map((r) => ({
      name: r.metadata.name,
      created: r.metadata.creationTimestamp,
      image: r.spec.containers[0]?.image ?? '',
      release: r.spec.containers[0]?.env.find((e) => e.name === 'ENGINE_RELEASE')?.value,
      ready: r.status.conditions.some((c) => c.type === 'Ready' && c.status === 'True'),
    }))
    .sort((a, b) => b.created.localeCompare(a.created));
}

/** The tagged-revision URL Cloud Run gives `canary`: `https://canary---<service host>`. Undefined for anything that is not a run.app origin. */
export function canaryUrlFor(serviceUrl: string): string | undefined {
  const match = /^https:\/\/([a-z0-9-]+\.a\.run\.app|[a-z0-9-]+\.run\.app)$/.exec(serviceUrl);
  return match?.[1] ? `https://canary---${match[1]}` : undefined;
}

/** Poll /health (never /healthz: Cloud Run reserves it) until it answers 200 `count` times in a row (spaced by `gapMs`), or give up. */
export async function healthy(baseUrl: string, count = 3, gapMs = 4000, attempts = 24): Promise<boolean> {
  let streak = 0;
  for (let i = 0; i < attempts && streak < count; i++) {
    try {
      const response = await fetch(`${baseUrl}/health`, { redirect: 'manual', signal: AbortSignal.timeout(15_000) });
      const body = (await response.json().catch(() => ({}))) as { status?: string };
      streak = response.status === 200 && body.status === 'ok' ? streak + 1 : 0;
    } catch {
      streak = 0;
    }
    if (streak < count) await new Promise((r) => setTimeout(r, gapMs));
  }
  return streak >= count;
}
