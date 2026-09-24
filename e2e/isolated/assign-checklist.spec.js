const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { EditorAssignPage } = require('../pages/EditorAssignPage');

const REST_BASE =
  'https://127.0.0.1:8089/servicesNS/nobody/stigs_in_splunk';

const MINIMAL_BENCHMARK = path.resolve(
  __dirname,
  '../../tests/fixtures/minimal_benchmark.xml',
);

const BASELINE_LABEL = 'Example_STIG';
const HOSTNAME = 'web-01';

test.use({ trace: 'off', video: 'off' });

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
 */
async function createAssignFixture(request) {
  const headers = restAuthHeader();
  const workspaceName = `pw-assign-${Date.now()}`;

  const collectionRes = await request.post(
    `${REST_BASE}/stig_collections?output_mode=json`,
    {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { name: workspaceName, description: 'playwright' },
      ignoreHTTPSErrors: true,
    },
  );
  expect(collectionRes.ok()).toBeTruthy();
  const collection = await collectionRes.json();
  const collectionId = collection._key;
  expect(collectionId).toBeTruthy();

  const hostRes = await request.post(`${REST_BASE}/stig_hosts?output_mode=json`, {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: { hostname: HOSTNAME, stig_collection_id: collectionId },
    ignoreHTTPSErrors: true,
  });
  expect(hostRes.ok()).toBeTruthy();

  const xmlBody = fs.readFileSync(MINIMAL_BENCHMARK);
  const importRes = await request.post(
    `${REST_BASE}/stig_baselines/import?format=xccdf&stig_collection_id=${collectionId}&output_mode=json`,
    {
      headers: { ...headers, 'Content-Type': 'application/xml' },
      data: xmlBody,
      ignoreHTTPSErrors: true,
    },
  );
  expect(importRes.ok()).toBeTruthy();
  const imported = await importRes.json();
  expect(imported.created).toBeTruthy();
  const baselineId = imported._key || imported.baselines?.[0]?._key;
  expect(baselineId).toBeTruthy();

  const defaultRes = await request.post(
    `${REST_BASE}/stig_collections/${collectionId}/baseline_defaults?output_mode=json`,
    {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { stig_id: BASELINE_LABEL, baseline_id: baselineId },
      ignoreHTTPSErrors: true,
    },
  );
  expect(defaultRes.ok()).toBeTruthy();

  return { workspaceName, collectionId, baselineId };
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} collectionId
 */
async function deleteCollectionCascade(request, collectionId) {
  const headers = restAuthHeader();
  const response = await request.delete(
    `${REST_BASE}/stig_collections/${collectionId}?cascade=true&output_mode=json`,
    { headers, ignoreHTTPSErrors: true },
  );
  expect(response.ok()).toBeTruthy();
}

test.describe('STIG editor host assign', () => {
  test.setTimeout(180_000);

  test('assign baseline to host shows checklist rules in the editor', async ({
    page,
    request,
  }) => {
    const editor = new EditorAssignPage(page);
    let collectionId;

    try {
      const fixture = await createAssignFixture(request);
      collectionId = fixture.collectionId;

      await editor.open();
      await editor.selectWorkspace(fixture.workspaceName);
      await editor.selectHost(HOSTNAME);
      await editor.openHostActions();
      await editor.selectAssignBaseline(fixture.baselineId, BASELINE_LABEL);
      await editor.assignToHost();

      try {
        await editor.expectAssignSuccess();
      } catch {
        await editor.expectAtLeastOneFindingRow();
      }
      await editor.expectAtLeastOneFindingRow();
    } finally {
      if (collectionId) {
        await deleteCollectionCascade(request, collectionId);
      }
    }
  });
});
