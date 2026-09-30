import { readFileSync } from 'node:fs';
import { z } from 'zod';
import { ConfigError, readEnvFile, validateEnvironment } from '../../packages/config/src/index.js';
import { updateEnvText, writePrivateFile } from '../env/files.js';
import { gcloud } from '../env/process.js';
import { runCli } from '../env/cli.js';

runCli(import.meta.url, async () => {
  if (process.argv.length !== 2) throw new ConfigError(['CLI_OPTIONS']);
  const checked = validateEnvironment(readEnvFile('.env.production'), 'production', 'bootstrap');
  if (checked.invalid.length) throw new ConfigError(checked.invalid);
  const config = checked.config;
  const project = config.GCP_PROJECT_ID;
  const principalRows = z
    .array(z.object({ account: z.string().email() }).strict())
    .parse(JSON.parse(await gcloud(['auth', 'list', '--filter=status:ACTIVE', '--format=json(account)'])));
  const principal = principalRows[0]?.account;
  if (!principal || principalRows.length !== 1) throw new ConfigError(['GCLOUD_OPERATOR']);
  const deployer = `sf-deployer@${project}.iam.gserviceaccount.com`;
  const bucket = `${project}-sf-tfstate`;
  console.log('Bootstrap: enabling required control-plane APIs.');
  await gcloud([
    'services',
    'enable',
    'iam.googleapis.com',
    'iamcredentials.googleapis.com',
    'cloudresourcemanager.googleapis.com',
    'storage.googleapis.com',
    'serviceusage.googleapis.com',
    `--project=${project}`,
  ]);
  console.log('Bootstrap: ensuring deployer identity and impersonation.');
  const accounts = z
    .array(z.object({ email: z.string() }).strict())
    .parse(
      JSON.parse(
        await gcloud([
          'iam',
          'service-accounts',
          'list',
          `--project=${project}`,
          `--filter=email:${deployer}`,
          '--format=json(email)',
        ]),
      ),
    );
  if (!accounts.some((a) => a.email === deployer))
    await gcloud([
      'iam',
      'service-accounts',
      'create',
      'sf-deployer',
      `--project=${project}`,
      '--display-name=StudyForge deployer',
    ]);
  await gcloud([
    'iam',
    'service-accounts',
    'add-iam-policy-binding',
    deployer,
    `--project=${project}`,
    `--member=user:${principal}`,
    '--role=roles/iam.serviceAccountTokenCreator',
    '--condition=None',
  ]);
  console.log('Bootstrap: ensuring deployer resource-management grants.');
  const roles = [
    'roles/browser',
    'roles/serviceusage.serviceUsageAdmin',
    'roles/run.admin',
    'roles/artifactregistry.admin',
    'roles/secretmanager.admin',
    'roles/iam.serviceAccountAdmin',
    'roles/logging.configWriter',
    'roles/monitoring.editor',
  ];
  for (const role of roles)
    await gcloud([
      'projects',
      'add-iam-policy-binding',
      project,
      `--member=serviceAccount:${deployer}`,
      `--role=${role}`,
      '--condition=None',
    ]);
  console.log('Bootstrap: ensuring versioned private state bucket.');
  const buckets = z
    .array(z.object({ name: z.string() }).strict())
    .parse(
      JSON.parse(
        await gcloud([
          'storage',
          'buckets',
          'list',
          `--project=${project}`,
          `--filter=name:${bucket}`,
          '--format=json(name)',
        ]),
      ),
    );
  console.log('Bootstrap: creating the state bucket if absent.');
  if (!buckets.some((b) => b.name.replace('gs://', '').replace(/\/$/, '') === bucket))
    await gcloud([
      'storage',
      'buckets',
      'create',
      `gs://${bucket}`,
      `--project=${project}`,
      `--location=${config.GCP_REGION}`,
      '--uniform-bucket-level-access',
      '--public-access-prevention',
    ]);
  console.log('Bootstrap: enabling state versioning and bucket-scoped access.');
  await gcloud(['storage', 'buckets', 'update', `gs://${bucket}`, '--versioning']);
  await gcloud([
    'storage',
    'buckets',
    'add-iam-policy-binding',
    `gs://${bucket}`,
    `--member=serviceAccount:${deployer}`,
    '--role=roles/storage.objectAdmin',
  ]);
  console.log('Bootstrap: checking billing and budget-management permission.');
  const billing = z
    .object({ billingAccountName: z.string().regex(/^billingAccounts\/[A-Z0-9-]+$/), billingEnabled: z.literal(true) })
    .strict()
    .parse(
      JSON.parse(
        await gcloud(['billing', 'projects', 'describe', project, '--format=json(billingAccountName,billingEnabled)']),
      ),
    );
  const account = billing.billingAccountName.split('/')[1]!;
  await gcloud([
    'billing',
    'accounts',
    'add-iam-policy-binding',
    account,
    `--member=serviceAccount:${deployer}`,
    '--role=roles/billing.costsManager',
  ]);
  writePrivateFile(
    '.env.production',
    updateEnvText(readFileSync('.env.production', 'utf8'), {
      GCP_DEPLOY_SERVICE_ACCOUNT: deployer,
      TF_STATE_BUCKET: bucket,
    }),
  );
  writePrivateFile(
    'infra/terraform/envs/prod/.env.auto.tfvars.json',
    JSON.stringify(
      {
        project_id: project,
        region: config.GCP_REGION,
        artifact_repo: config.GCP_ARTIFACT_REPO,
        billing_account: account,
        enable_runtime: false,
      },
      null,
      2,
    ) + '\n',
  );
  console.log(
    'Deployer/state bootstrap completed. Runtime deployment is still disabled. No service-account keys created.',
  );
});
