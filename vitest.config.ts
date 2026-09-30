import { defineConfig } from 'vitest/config';

export default defineConfig({
  // Unit tests use explicit fixtures and must never load operator credentials.
  envDir: false,
  test: { include: ['packages/**/*.test.ts', 'scripts/**/*.test.ts'] },
});
