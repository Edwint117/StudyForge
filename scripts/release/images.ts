import { copyFileSync, existsSync, mkdirSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { run, type StageOutcome } from './lib.js';

// Pinned by tag; bump deliberately. Trivy runs in a container so Windows needs no native binary.
export const TRIVY_IMAGE = 'aquasec/trivy:0.71.0';
export const OSV_IMAGE = 'ghcr.io/google/osv-scanner:v2.3.5';
const SCAN_DIR = '.cache/scan';

export function buildEngineImage(tag: string, log: string) {
  return run(`docker build --pull=false -t ${tag} services/engine`, { log, timeoutMs: 1_200_000 });
}

/**
 * Scan a local image with Trivy. The image is exported to a tarball and mounted read-only: the container never gets
 * the Docker socket (a privileged mount the owner declined) or the repository (which holds private .env files).
 */
export async function trivyScan(image: string, log: string): Promise<StageOutcome> {
  mkdirSync(SCAN_DIR, { recursive: true });
  const tar = resolve(SCAN_DIR, 'image.tar');
  const saved = await run(`docker save ${image} -o "${tar}"`, { log, timeoutMs: 600_000 });
  if (saved.code !== 0) return { outcome: 'fail', note: `could not export ${image}` };
  try {
    const scan = await run(
      [
        'docker run --rm',
        `--mount type=bind,source="${tar}",target=/image.tar,readonly`,
        '--mount type=volume,source=sf-trivy-cache,target=/root/.cache',
        TRIVY_IMAGE,
        'image --input /image.tar --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 --no-progress --quiet',
      ].join(' '),
      { log, timeoutMs: 900_000 },
    );
    return scan.code === 0
      ? { outcome: 'pass', note: 'no fixable HIGH/CRITICAL findings' }
      : { outcome: 'fail', note: `Trivy reported fixable HIGH/CRITICAL findings or could not run; see ${log}` };
  } finally {
    rmSync(tar, { force: true });
  }
}

/** OSV over the lockfiles only, copied into a scratch directory so the container never sees the repository. */
export async function osvScan(log: string): Promise<StageOutcome> {
  const dir = resolve(SCAN_DIR, 'lockfiles');
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const copies = [
    ['pnpm-lock.yaml', 'pnpm-lock.yaml'],
    ['services/engine/uv.lock', 'uv.lock'],
  ];
  for (const [from, to] of copies) if (from && to && existsSync(from)) copyFileSync(from, resolve(dir, to));
  const scan = await run(
    `docker run --rm --mount type=bind,source="${dir}",target=/src,readonly ${OSV_IMAGE} scan source -r /src`,
    { log, timeoutMs: 300_000 },
  );
  return scan.code === 0
    ? { outcome: 'pass', note: 'no known vulnerabilities in pnpm-lock.yaml / uv.lock' }
    : { outcome: 'fail', note: `OSV reported vulnerabilities or could not run; see ${log}` };
}
