import { readEnvFile, validateEnvironment, ownerKey } from '../../packages/config/src/index.js';
import { options, runCli } from './cli.js';
import { connectivity } from './probes.js';
import type { ProbeRow } from './probes.js';

runCli(import.meta.url, async () => {
  const args = options();
  const result = validateEnvironment(
    readEnvFile(`.env.${args.environment}`),
    args.environment,
    args.bootstrap ? 'bootstrap' : 'runtime',
  );
  const rows: ProbeRow[] = [
    {
      check: 'Configuration schema',
      status: result.invalid.length ? 'FAIL' : 'PASS',
      detail: result.invalid.length ? 'invalid_or_missing_fields' : 'formats_valid',
      fields: result.invalid.map(ownerKey),
    },
    ...result.pending.map((key): ProbeRow => ({
      check: key,
      status: 'PENDING',
      detail: 'agent_provisions_in_M0',
      fields: [key],
    })),
  ];
  if (!args.offline) rows.push(...(await connectivity(result.config, args.environment, result.invalid)));
  console.log(
    `Environment: ${args.environment}; mode: ${args.bootstrap ? 'bootstrap (not deployment-ready)' : 'runtime'}; checks: ${args.offline ? 'formats only' : 'read-only connectivity'}`,
  );
  for (const row of rows)
    console.log(
      `${row.status.padEnd(7)} ${row.check} — ${row.detail}${row.status === 'FAIL' || (row.status === 'SKIP' && row.detail === 'required_fields_not_ready') ? ` [${row.fields.join(', ')}]` : ''}`,
    );
  if (rows.some((row) => row.status === 'FAIL')) process.exitCode = 1;
  else if (args.offline) console.log('Format checks passed; live connectivity was not tested.');
  else if (args.bootstrap) console.log('Bootstrap checks passed; pending agent provisioning is not a passed M0 gate.');
  else
    console.log(
      'Environment validation passed. Format-only OAuth/Sentry checks are not end-to-end authentication tests.',
    );
});
