// @ts-check
const { defineConfig } = require('@playwright/test');
const { ADMIN_STORAGE_STATE_PATH, getSplunkBaseUrl } = require('./fixtures/auth');

module.exports = defineConfig({
  testDir: '.',
  fullyParallel: true,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  outputDir: 'test-results',
  timeout: 240_000,
  expect: {
    timeout: 60_000,
  },
  use: {
    ignoreHTTPSErrors: true,
    baseURL: getSplunkBaseUrl(),
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 60_000,
    navigationTimeout: 60_000,
  },
  globalSetup: require.resolve('./global-setup.js'),
  projects: [
    {
      name: 'isolated',
      testIgnore: '**/org/**',
      use: {
        storageState: ADMIN_STORAGE_STATE_PATH,
      },
    },
    {
      name: 'org',
      testMatch: '**/org/**/*.spec.js',
      fullyParallel: false,
      workers: 1,
    },
  ],
});
