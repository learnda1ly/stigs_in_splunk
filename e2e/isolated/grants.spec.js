const { test, expect, chromium } = require('@playwright/test');
const { ADMIN_STORAGE_STATE_PATH, getSplunkBaseUrl } = require('../fixtures/auth');
const { appPath } = require('../fixtures/splunk');
const { GrantsPage } = require('../pages/GrantsPage');
const REST_BASE =
  process.env.SPLUNK_MGMT_URL ||
  (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');

const TEST_USER_PASSWORD = 'PlaywrightTest!2026';

test.use({ trace: 'off', video: 'off' });

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
  const response = await request.delete(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections/${key}?output_mode=json&cascade=true`,
    { headers, ignoreHTTPSErrors: true },
  );
  return response.ok();
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

async function assertEditorWorkspaceAccess(launchedBrowser, username, workspaceName, shouldOffer) {
  const context = await launchedBrowser.newContext({
    baseURL: getSplunkBaseUrl(),
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();
  try {
    await page.goto('/en-US/account/login', { timeout: 60_000 });
    await page.locator('input[name=username]').fill(username);
    await page.locator('input[name=password]').fill(TEST_USER_PASSWORD);
    await page.locator('input[type=submit].splButton-primary').first().click();
    await page.waitForURL((url) => !url.pathname.includes('/account/login'), {
      timeout: 60_000,
    });
    await expect(page.getByText(username, { exact: true })).toBeVisible({ timeout: 30_000 });

    await page.goto(appPath('stig_editor_ui'), {
      timeout: 60_000,
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: 60_000 });

    const select = page.getByRole('combobox').first();
    await expect(select).toBeVisible({ timeout: 30_000 });
    await select.click();
    await expect(page.getByRole('option').first()).toBeVisible({ timeout: 30_000 });

    const readOffered = async () => {
      const optionTexts = await page.getByRole('option').allTextContents();
      return optionTexts.some((label) => label.includes(workspaceName));
    };

    if (shouldOffer) {
      await expect.poll(readOffered, { timeout: 30_000 }).toBe(true);
    } else {
      expect(await readOffered()).toBe(false);
    }
    await page.keyboard.press('Escape');
  } finally {
    await context.close();
  }
}

test.describe('STIG workspace grants', () => {
  test.setTimeout(180_000);

  test('assessor editor workspace option (debug)', async () => {
    const launchedBrowser = await chromium.launch();
    try {
      await assertEditorWorkspaceAccess(
        launchedBrowser,
        'stig_pw_assessor',
        'pw-grants-debug',
        true,
      );
    } finally {
      await launchedBrowser.close();
    }
  });

  test('admin grants workspace access; members see workspace in editor', async ({ request }) => {
    const workspaceName = `pw-grants-${Date.now()}`;
    let workspaceKey = null;
    const launchedBrowser = await chromium.launch();

    try {
      await ensureSplunkUsers(request);
      workspaceKey = await createRestrictedWorkspace(request, workspaceName);

      const adminCtx = await launchedBrowser.newContext({
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
      await adminCtx.close();

      await assertEditorWorkspaceAccess(launchedBrowser, 'stig_pw_assessor', workspaceName, true);
      await assertEditorWorkspaceAccess(launchedBrowser, 'stig_pw_outsider', workspaceName, false);
    } finally {
      await launchedBrowser.close().catch(() => {});
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
