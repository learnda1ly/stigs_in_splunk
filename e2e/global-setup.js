const fs = require('fs');
const path = require('path');
const { chromium } = require('@playwright/test');
const { ADMIN_STORAGE_STATE_PATH, getSplunkBaseUrl } = require('./fixtures/auth');

async function globalSetup() {
  const baseURL = getSplunkBaseUrl();
  const username = process.env.SPLUNK_ADMIN_USER;
  const password = process.env.SPLUNK_ADMIN_PASSWORD;

  if (!username || !password) {
    throw new Error(
      'SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD must be set for global setup.',
    );
  }

  const authDir = path.dirname(ADMIN_STORAGE_STATE_PATH);
  fs.mkdirSync(authDir, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  const loginPath = '/en-US/account/login';
  await page.goto(`${baseURL}${loginPath}`);

  const usernameInput = page.locator('input[name="username"]');
  const passwordInput = page.locator('input[name="password"]');
  const submitButton = page.locator('input[type="submit"].splButton-primary').first();

  await usernameInput.waitFor({ state: 'visible', timeout: 60_000 });
  await usernameInput.fill(username);
  await passwordInput.fill(password);
  await submitButton.click();

  await page.waitForURL(
    (url) => !url.pathname.includes('/account/login'),
    { timeout: 60_000 },
  );

  await context.storageState({ path: ADMIN_STORAGE_STATE_PATH });
  await browser.close();
}

module.exports = globalSetup;
