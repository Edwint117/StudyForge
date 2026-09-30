import { request } from 'node:http';
import { z } from 'zod';
import { ConfigError } from '../../packages/config/src/index.js';
import { runCli } from '../env/cli.js';

const containerName = 'supabase_vector_studyforge';
const socketPath = process.platform === 'win32' ? '\\\\.\\pipe\\docker_engine' : '/var/run/docker.sock';

async function docker(method: string, path: string, body?: unknown): Promise<unknown> {
  return new Promise((accept, reject) => {
    const payload = body === undefined ? undefined : JSON.stringify(body);
    const req = request({ socketPath, method, path, headers: { 'content-type': 'application/json' } }, (response) => {
      const chunks: Buffer[] = [];
      let length = 0;
      response.on('data', (chunk: Buffer) => {
        length += chunk.length;
        if (length > 2_000_000) req.destroy(new Error('Docker response too large'));
        else chunks.push(chunk);
      });
      response.on('end', () => {
        if (!response.statusCode || response.statusCode >= 400) {
          reject(new ConfigError(['DOCKER_VECTOR'], 'docker_operation_failed'));
          return;
        }
        try {
          const text = Buffer.concat(chunks).toString('utf8');
          accept(text ? JSON.parse(text) : null);
        } catch {
          reject(new ConfigError(['DOCKER_VECTOR'], 'invalid_docker_response'));
        }
      });
    });
    req.setTimeout(30_000, () => req.destroy(new Error('Docker timeout')));
    req.once('error', () => reject(new ConfigError(['DOCKER_VECTOR'], 'docker_connection_failed')));
    req.end(payload);
  });
}

export async function fixVector(): Promise<void> {
  const raw = z.record(z.string(), z.unknown()).parse(await docker('GET', `/containers/${containerName}/json`));
  const state = z.record(z.string(), z.unknown()).parse(raw.State);
  const config = z.record(z.string(), z.unknown()).parse(raw.Config);
  const image = z.string().parse(config.Image);
  const env = z.array(z.string()).parse(config.Env);
  if (env.includes('DOCKER_HOST=unix:///var/run/docker.sock')) {
    if (state.Running !== true) await docker('POST', `/containers/${containerName}/start`);
    console.log('Vector already uses the local Docker socket.');
    return;
  }
  if (
    !/(supabase|timberio)\/vector[:@]/.test(image) ||
    !env.includes('DOCKER_HOST=http://host.docker.internal:2375') ||
    z.array(z.unknown()).parse(raw.Mounts).length !== 0
  )
    throw new ConfigError(['DOCKER_VECTOR'], 'unexpected_vector_configuration');
  const hosts = z.record(z.string(), z.unknown()).parse(raw.HostConfig);
  const network = z.string().parse(hosts.NetworkMode);
  const backup = `${containerName}_tcp_backup`;
  // Preserve the original container for rollback. No volumes or user data are removed.
  await docker('POST', `/containers/${containerName}/stop?t=10`);
  await docker('POST', `/containers/${containerName}/rename?name=${backup}`);
  try {
    await docker('POST', `/containers/create?name=${containerName}`, {
      Image: image,
      Env: env.filter((item) => !item.startsWith('DOCKER_HOST=')).concat('DOCKER_HOST=unix:///var/run/docker.sock'),
      Cmd: config.Cmd,
      Entrypoint: config.Entrypoint,
      WorkingDir: config.WorkingDir,
      User: config.User,
      Labels: config.Labels,
      Healthcheck: config.Healthcheck,
      HostConfig: {
        NetworkMode: network,
        Binds: ['/var/run/docker.sock:/var/run/docker.sock:ro'],
        RestartPolicy: hosts.RestartPolicy,
        LogConfig: hosts.LogConfig,
      },
    });
    await docker('POST', `/containers/${containerName}/start`);
    console.log('Vector recreated with the Docker socket; original TCP container retained for rollback.');
  } catch {
    // Preserve both containers if creation succeeded; do not delete unknown state automatically.
    console.log('Vector repair incomplete; original container remains in the named TCP backup.');
    throw new ConfigError(['DOCKER_VECTOR'], 'vector_repair_incomplete');
  }
}

runCli(import.meta.url, async () => {
  if (process.argv.length !== 2) throw new ConfigError(['CLI_OPTIONS']);
  await fixVector();
});
