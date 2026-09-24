const path = require('path');
const { test, expect } = require('@playwright/test');
const { ImportPage, SELECTORS: importSelectors } = require('../pages/ImportPage');
const { LibraryPage, SELECTORS: librarySelectors } = require('../pages/LibraryPage');

const REST_BASE =
  process.env.SPLUNK_MGMT_URL ||
  (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');

const MINIMAL_BENCHMARK = path.resolve(
  __dirname,
  '../../tests/fixtures/minimal_benchmark.xml',
);

const STIG_ID = 'Example_STIG';
const BENCHMARK_TITLE = 'Example STIG for PoC';

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

async function deleteWorkspaceScopedBaseline(request, workspaceKey) {
  const headers = restAuthHeader();
  if (!headers || !workspaceKey) {
    return;
  }
  const response = await request.get(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_baselines?output_mode=json&stig_collection_id=${encodeURIComponent(workspaceKey)}`,
    { headers, ignoreHTTPSErrors: true },
  );
  if (!response.ok()) {
    return;
  }
  const rows = await response.json();
  if (!Array.isArray(rows)) {
    return;
  }
  for (const row of rows) {
    if (row.stig_id !== STIG_ID || row.stig_collection_id !== workspaceKey || !row._key) {
      continue;
    }
    await request.delete(
      `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_baselines/${encodeURIComponent(row._key)}?output_mode=json`,
      { headers, ignoreHTTPSErrors: true },
    );
  }
}

test.use({ trace: 'off' });

test.describe('Baseline import', () => {
  test.setTimeout(180_000);

  test('admin imports a benchmark XML and sees it in the library', async ({ page, request }) => {
    const workspaceName = `pw-import-${Date.now()}`;
    let workspaceKey = '';

    const importPage = new ImportPage(page);
    const libraryPage = new LibraryPage(page);

    try {
      workspaceKey = await createWorkspaceByRest(request, workspaceName);

      await importPage.open();
      await importPage.openBaselinesTab();
      await importPage.selectWorkspace(workspaceName);
      await importPage.uploadBenchmarkFile(MINIMAL_BENCHMARK);
      await importPage.expectImportSucceeded(BENCHMARK_TITLE);

      await libraryPage.open();
      await libraryPage.selectWorkspaceFilter(workspaceName);
      await libraryPage.expectBenchmarkVisible(STIG_ID, BENCHMARK_TITLE);
    } finally {
      if (workspaceKey) {
        await deleteWorkspaceScopedBaseline(request, workspaceKey);
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
  importSelectors,
  librarySelectors,
};
