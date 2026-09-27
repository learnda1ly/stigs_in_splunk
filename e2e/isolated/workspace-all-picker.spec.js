const { test, expect } = require('@playwright/test');
const { EditorPage } = require('../pages/EditorPage');
const {
  workspaceCombobox,
  expectAllWorkspacesOptionListed,
  ALL_WORKSPACES_LABEL,
} = require('../helpers/workspaceSelect');

const REST_BASE =
  process.env.SPLUNK_MGMT_URL ||
  (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');

function restAuthHeader() {
  const user = process.env.SPLUNK_ADMIN_USER;
  const password = process.env.SPLUNK_ADMIN_PASSWORD;
  if (!user || !password) {
    throw new Error('SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD are required');
  }
  return {
    Authorization: `Basic ${Buffer.from(`${user}:${password}`).toString('base64')}`,
  };
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} collectionId
 */
async function deleteWorkspaceCascade(request, collectionId) {
  const response = await request.delete(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections/${collectionId}?cascade=true&output_mode=json`,
    { headers: restAuthHeader(), ignoreHTTPSErrors: true },
  );
  return response.ok();
}

test.use({ trace: 'off', video: 'off' });

test.describe('Workspace All picker', () => {
  test.setTimeout(120_000);

  test('editor offers All workspaces when multiple collections are visible', async ({
    page,
    request,
  }) => {
    const name = `pw-all-${Date.now()}`;
    let collectionId = null;

    try {
      const createRes = await request.post(
        `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections?output_mode=json`,
        {
          headers: { ...restAuthHeader(), 'Content-Type': 'application/json' },
          data: { name, description: 'Playwright All workspaces picker' },
          ignoreHTTPSErrors: true,
        },
      );
      expect(createRes.ok()).toBeTruthy();
      const body = await createRes.json();
      collectionId = body._key;

      const editor = new EditorPage(page);
      await editor.open();
      const select = workspaceCombobox(page);
      await expectAllWorkspacesOptionListed(page, select);

      await select.click();
      await page.getByRole('option', { name: ALL_WORKSPACES_LABEL, exact: true }).click();
      await expect(select).toContainText(ALL_WORKSPACES_LABEL, { timeout: 30_000 });
    } finally {
      if (collectionId) {
        await deleteWorkspaceCascade(request, collectionId);
      }
    }
  });
});
