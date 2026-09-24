const { test, expect, chromium } = require('@playwright/test');
const { ADMIN_STORAGE_STATE_PATH, getSplunkBaseUrl } = require('../fixtures/auth');
const { appPath } = require('../fixtures/splunk');
const { GrantsPage } = require('../pages/GrantsPage');

const REST_BASE =
  process.env.SPLUNK_MGMT_URL ||
  (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');

const TEST_USER_PASSWORD = 'PlaywrightTest!2026';

test.use({ trace: 'off', video: 'off', actionTimeout: 30_000 });

const TEST_USERS = [
  { name: 'stig_pw_assessor', roles: 'stig_user' },
  { name: 'stig_pw_reviewer', roles: 'stig_user' },
  { name: 'stig_pw_outsider', roles: 'stig_user' },
];

function restAuthHeader() {
  const user = process.env.SPLUNK_ADMIN_USER;
  const password = process.env.SPLUNK_ADMIN_PASSWORD;
  if (!user || !password) {
    return null;
  }
  return {
    Authorization: `Basic ${Buffer.from(`${user}:${password}`).toString('base64')}`,
  };
}

async function waitForCollectionsApi(request, maxWaitMs = 120_000) {
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const headers = restAuthHeader();
    if (!headers) {
      throw new Error('SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD are required');
    }
    try {
      const response = await request.get(
        `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections?output_mode=json`,
        { headers, ignoreHTTPSErrors: true },
      );
      if (response.ok()) {
        return;
      }
    } catch {
      // Splunk may still be starting; retry until deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  throw new Error('stig_collections REST API did not become ready');
}

async function listCollections(request) {
  const headers = restAuthHeader();
  if (!headers) {
    return [];
  }
  const response = await request.get(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections?output_mode=json`,
    { headers, ignoreHTTPSErrors: true },
  );
  if (!response.ok()) {
    return [];
  }
  return response.json();
}

async function createRestrictedWorkspace(request, name) {
  const headers = restAuthHeader();
  if (!headers) {
    throw new Error('SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD are required');
  }
  const response = await request.post(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections?output_mode=json`,
    {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: {
        name,
        description: 'Playwright grants isolated test workspace',
        access_principals: '["user:admin"]',
        is_default: false,
      },
      ignoreHTTPSErrors: true,
    },
  );
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  const row = body._key ? body : (body.entry && body.entry[0] && body.entry[0].content) || body;
  if (row._key) {
    return row._key;
  }
  const collections = await listCollections(request);
  const match = collections.find((c) => c.name === name);
  expect(match?._key).toBeTruthy();
  return match._key;
}

async function deleteWorkspaceByKey(request, key) {
  const headers = restAuthHeader();
  if (!headers || !key) {
    return false;
  }
  try {
    const response = await request.delete(
      `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections/${encodeURIComponent(key)}?output_mode=json&cascade=true`,
      { headers, ignoreHTTPSErrors: true },
    );
    return response.ok();
  } catch {
    return false;
  }
}

async function ensureSplunkUsers(request) {
  const headers = restAuthHeader();
  if (!headers) {
    throw new Error('SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD are required');
  }
  for (const user of TEST_USERS) {
    const response = await request.post(`${REST_BASE}/services/authentication/users`, {
      headers: { ...headers, 'Content-Type': 'application/x-www-form-urlencoded' },
      form: {
        name: user.name,
        password: TEST_USER_PASSWORD,
        roles: user.roles,
      },
      ignoreHTTPSErrors: true,
    });
    if (!response.ok() && response.status() !== 409 && response.status() !== 400) {
      throw new Error(`Failed to ensure user ${user.name}: HTTP ${response.status()}`);
    }
  }
}

async function splunkLogin(page, username) {
  const returnTo = encodeURIComponent('/en-US/app/stigs_in_splunk/stig_editor_ui');
  const loginPath = `/en-US/account/login?return_to=${returnTo}`;
  await page.goto(loginPath, { timeout: 60_000, waitUntil: 'domcontentloaded' });
  const userInput = page.locator('input[name=username]');
  if (!(await userInput.isVisible({ timeout: 5_000 }).catch(() => false))) {
    await page.goto(loginPath, { timeout: 60_000, waitUntil: 'load' });
  }
  await expect(userInput).toBeVisible({ timeout: 30_000 });
  await userInput.fill(username);
  await page.locator('input[name=password]').fill(TEST_USER_PASSWORD);
  const signIn = page.getByRole('button', { name: 'Sign In' });
  if (await signIn.count()) {
    await signIn.click();
  } else {
    await page.locator('input[type=submit].splButton-primary').first().click();
  }
  await page.waitForURL((url) => !url.pathname.includes('/account/login'), {
    timeout: 60_000,
  });
}

async function assertEditorWorkspaceListed(page, workspaceName, shouldOffer) {
  await page.goto(appPath('stig_editor_ui'), {
    timeout: 60_000,
    waitUntil: 'domcontentloaded',
  });
  await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: 60_000 });

  const select = page.getByRole('combobox').first();
  await expect(select).toBeVisible({ timeout: 30_000 });
  await select.click();
  await expect(page.getByRole('option').first()).toBeVisible({ timeout: 30_000 });

  const workspacePattern = new RegExp(workspaceName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const workspaceOffered = async () => {
    const option = page.getByRole('option', { name: workspacePattern });
    return (await option.count()) > 0;
  };

  if (shouldOffer) {
    await expect.poll(workspaceOffered, { timeout: 30_000 }).toBe(true);
  } else {
    expect(await workspaceOffered()).toBe(false);
  }
  await page.keyboard.press('Escape');
}

async function assertEditorWorkspaceAccess(launchedBrowser, username, workspaceName, shouldOffer) {
  const context = await launchedBrowser.newContext({
    baseURL: getSplunkBaseUrl(),
    ignoreHTTPSErrors: true,
  });
  await context.clearCookies();
  const page = await context.newPage();
  try {
    await splunkLogin(page, username);
    await assertEditorWorkspaceListed(page, workspaceName, shouldOffer);
  } finally {
    await context.close().catch(() => {});
  }
}

test.describe('STIG workspace grants', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(300_000);

  test('admin grants workspace access; members see workspace in editor', async ({ request }) => {
    const workspaceName = `pw-grants-${Date.now()}`;
    let workspaceKey = null;
    const adminBrowser = await chromium.launch();

    try {
      await waitForCollectionsApi(request);
      await ensureSplunkUsers(request);
      workspaceKey = await createRestrictedWorkspace(request, workspaceName);

      const adminCtx = await adminBrowser.newContext({
        storageState: ADMIN_STORAGE_STATE_PATH,
        baseURL: getSplunkBaseUrl(),
        ignoreHTTPSErrors: true,
      });
      const adminPage = await adminCtx.newPage();
      const grants = new GrantsPage(adminPage);
      await grants.open();
      await grants.selectWorkspace(workspaceName);

      await grants.openNewGrantForm();
      await grants.saveGrant('user:stig_pw_assessor', 'Member');

      await grants.openNewGrantForm();
      await grants.saveGrant('user:stig_pw_reviewer', 'Manager');

      await grants.expectGrantRow('user:stig_pw_assessor', 'member');
      await grants.expectGrantRow('user:stig_pw_reviewer', 'manager');
      const logoutPage = await adminCtx.newPage();
      await logoutPage
        .goto('/en-US/account/logout', { timeout: 60_000, waitUntil: 'domcontentloaded' })
        .catch(() => {});
      await logoutPage.close();
      await adminCtx.close();

      for (const { username, shouldOffer } of [
        { username: 'stig_pw_assessor', shouldOffer: true },
        { username: 'stig_pw_outsider', shouldOffer: false },
      ]) {
        await new Promise((resolve) => setTimeout(resolve, 2_000));
        const userBrowser = await chromium.launch();
        try {
          await assertEditorWorkspaceAccess(userBrowser, username, workspaceName, shouldOffer);
        } finally {
          await userBrowser.close().catch(() => {});
        }
      }
    } finally {
      await adminBrowser.close().catch(() => {});
      if (workspaceKey) {
        const removed = await deleteWorkspaceByKey(request, workspaceKey);
        if (!removed) {
          test.info().annotations.push({
            type: 'leftover-workspace',
            description: workspaceName,
          });
        }
      }
    }
  });
});
