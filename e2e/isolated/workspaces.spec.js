const { test } = require('@playwright/test');
const { WorkspacesPage } = require('../pages/WorkspacesPage');
const { EditorPage } = require('../pages/EditorPage');

const REST_BASE =
  process.env.SPLUNK_MGMT_URL ||
  (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');

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

async function restoreDefaultImportWorkspace(request) {
  const headers = restAuthHeader();
  if (!headers) {
    return;
  }
  const collections = await listCollections(request);
  const builtin = collections.find((row) => row.name === 'Default');
  if (!builtin?._key) {
    return;
  }
  await request.post(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections/${builtin._key}?output_mode=json`,
    {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { is_default: true },
      ignoreHTTPSErrors: true,
    },
  );
}

async function deleteWorkspaceByName(request, name) {
  const headers = restAuthHeader();
  if (!headers) {
    return false;
  }
  const collections = await listCollections(request);
  const match = collections.find((row) => row.name === name);
  if (!match?._key) {
    return true;
  }
  if (match.is_default) {
    await restoreDefaultImportWorkspace(request);
  }
  const response = await request.delete(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections/${match._key}?output_mode=json`,
    { headers, ignoreHTTPSErrors: true },
  );
  return response.ok();
}

test.describe('STIG workspaces', () => {
  test.setTimeout(180_000);

  test('admin creates a default workspace and selects it in the editor', async ({
    page,
    request,
  }) => {
    const name = `pw-ws-${Date.now()}`;
    const workspaces = new WorkspacesPage(page);
    const editor = new EditorPage(page);

    try {
      await workspaces.open();
      await workspaces.createWorkspace({
        name,
        description: 'Playwright isolated workspace test',
        isDefault: true,
      });
      await workspaces.expectRow(name, { isDefault: true });

      await editor.open();
      await editor.selectWorkspace(name);
      await editor.expectWorkspaceSelected(name);
    } finally {
      await restoreDefaultImportWorkspace(request);
      const removed = await deleteWorkspaceByName(request, name);
      if (!removed) {
        test.info().annotations.push({
          type: 'leftover-workspace',
          description: name,
        });
      }
    }
  });
});
