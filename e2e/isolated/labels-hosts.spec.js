const { test, expect } = require('@playwright/test');
const { HostsPage, SELECTORS: hostsSelectors } = require('../pages/HostsPage');
const { LabelsPage, SELECTORS: labelsSelectors } = require('../pages/LabelsPage');

test.use({ trace: 'off', video: 'off' });

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

async function createWorkspaceByRest(request, name) {
  const headers = restAuthHeader();
  expect(headers).toBeTruthy();
  const response = await request.post(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections?output_mode=json`,
    {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { name, is_default: false },
      ignoreHTTPSErrors: true,
    },
  );
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  if (body && body._key) {
    return body._key;
  }
  const collections = await listCollections(request);
  const match = collections.find((row) => row.name === name);
  expect(match?._key).toBeTruthy();
  return match._key;
}

async function deleteWorkspaceByKey(request, key) {
  const headers = restAuthHeader();
  if (!headers || !key) {
    return false;
  }
  const response = await request.delete(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections/${encodeURIComponent(key)}?output_mode=json&cascade=true`,
    { headers, ignoreHTTPSErrors: true },
  );
  return response.ok();
}

test.describe('Asset labels and hosts', () => {
  test.setTimeout(180_000);

  test('admin assigns a label to a host and filters by label', async ({ page, request }) => {
    const workspaceName = `pw-labels-${Date.now()}`;
    const hostName = 'web-01';
    const otherHostName = 'app-02';
    const labelName = 'web';
    let workspaceKey = '';

    const hosts = new HostsPage(page);
    const labels = new LabelsPage(page);

    try {
      workspaceKey = await createWorkspaceByRest(request, workspaceName);

      await hosts.open();
      await hosts.selectWorkspace(workspaceName);
      await hosts.createHost(hostName);
      await hosts.createHost(otherHostName);

      await labels.open();
      await labels.selectWorkspace(workspaceName);
      await labels.createLabel(labelName);
      await labels.setHostLabelToggle(hostName, labelName, true);
      await labels.filterHostsByLabel(labelName);
      await labels.expectHostInAssignmentTable(hostName);
      await labels.expectHostAbsentFromAssignmentTable(otherHostName);
    } finally {
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

module.exports = {
  hostsSelectors,
  labelsSelectors,
};
