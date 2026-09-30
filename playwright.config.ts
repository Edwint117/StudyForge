import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './apps/web/e2e',
  fullyParallel: true,
  retries: 0,
  workers: 2,
  use: { baseURL: 'http://127.0.0.1:3100', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm web:fixture',
    url: 'http://127.0.0.1:3100/api/healthz',
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
