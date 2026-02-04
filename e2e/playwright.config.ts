import { defineConfig } from '@playwright/test';

export default defineConfig({
  retries: 1,
  timeout: 30_000,
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:5000',
    trace: 'on-first-retry',
    headless: true,
  },
  globalSetup: require.resolve('./global-setup'),
  globalTeardown: require.resolve('./global-teardown'),
});
