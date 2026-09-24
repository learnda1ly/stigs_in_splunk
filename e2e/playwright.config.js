// @ts-check
const { defineConfig } = require('@playwright/test');
const { ADMIN_STORAGE_STATE_PATH, getSplunkBaseUrl } = require('./fixtures/auth');

module.exports = defineConfig({
  testDir: '.',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  outputDir: 'test-results',
  use: {
    ignoreHTTPSErrors: true,
    baseURL: getSplunkBaseUrl(),
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  globalSetup: require.resolve('./global-setup.js'),
  projects: [
    {
      name: 'isolated',
      use: {
        storageState: ADMIN_STORAGE_STATE_PATH,
      },
    },
  ],
});
