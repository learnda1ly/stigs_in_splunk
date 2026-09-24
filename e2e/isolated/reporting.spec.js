const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { CollectionDashboardPage } = require('../pages/CollectionDashboardPage');
const { MetaDashboardPage } = require('../pages/MetaDashboardPage');
const { ExportPage } = require('../pages/ExportPage');

const REST_BASE =
  process.env.SPLUNK_MGMT_URL ||
  (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');

const FIXTURE_XCCDF = path.join(
  __dirname,
  '..',
  '..',
  'tests',
  'fixtures',
  'minimal_benchmark.xml',
);

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

function restUrl(resourcePath, query = {}) {
  const params = new URLSearchParams({ output_mode: 'json', ...query });
  return `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/${resourcePath}?${params}`;
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} method
 * @param {string} resourcePath
 * @param {{ data?: unknown, query?: Record<string, string>, contentType?: string }} [opts]
 */
async function restCall(request, method, resourcePath, opts = {}) {
  const headers = { ...restAuthHeader() };
  if (opts.contentType) {
    headers['Content-Type'] = opts.contentType;
  } else if (opts.data !== undefined && !(opts.data instanceof Buffer)) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await request.fetch(restUrl(resourcePath, opts.query), {
    method,
    headers,
    data: opts.data,
    ignoreHTTPSErrors: true,
  });
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok()) {
    throw new Error(
      `${method} ${resourcePath} failed (${response.status()}): ${typeof body === 'string' ? body : JSON.stringify(body)}`,
    );
  }
  return body;
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} collectionId
 */
async function deleteWorkspaceCascade(request, collectionId) {
  const response = await request.delete(
    restUrl(`stig_collections/${collectionId}`, { cascade: 'true' }),
    { headers: restAuthHeader(), ignoreHTTPSErrors: true },
  );
  return response.ok();
}

/**
 * @param {import('@playwright/test').APIRequestContext} request
 */
async function seedReportingWorkspace(request) {
  const workspaceName = `pw-report-${Date.now()}`;
  const hostname = 'web-01';

  const collection = await restCall(request, 'POST', 'stig_collections', {
    data: {
      name: workspaceName,
      description: 'Playwright reporting and export isolated test',
      is_default: false,
    },
  });

  const host = await restCall(request, 'POST', 'stig_hosts', {
    data: {
      stig_collection_id: collection._key,
      hostname,
    },
  });

  const xmlBytes = fs.readFileSync(FIXTURE_XCCDF);
  const importBody = await restCall(request, 'POST', 'stig_baselines/import', {
    data: xmlBytes,
    contentType: 'application/xml',
    query: {
      format: 'xccdf',
      source_uri: 'minimal_benchmark.xml',
      stig_collection_id: collection._key,
    },
  });

  await restCall(request, 'POST', `stig_hosts/${host._key}/stigs`, {
    data: { baseline_id: importBody._key },
  });

  const reviewRows = await restCall(request, 'GET', 'stig_reviews', {
    query: { stig_collection_id: collection._key },
  });
  if (!Array.isArray(reviewRows) || !reviewRows.length) {
    throw new Error(`expected reviews for workspace: ${JSON.stringify(reviewRows)}`);
  }
  const reviewId = reviewRows[0]._key;

  await restCall(request, 'POST', `stig_reviews/${reviewId}`, {
    data: {
      status: 'open',
      finding_details: 'Playwright reporting fixture finding',
      comments: 'Playwright reporting fixture comment',
    },
  });
  await restCall(request, 'POST', `stig_reviews/${reviewId}/submit`, { data: {} });
  await restCall(request, 'POST', `stig_reviews/${reviewId}/accept`, { data: {} });

  return {
    workspaceName,
    collectionId: collection._key,
    hostname,
  };
}

test.use({ trace: 'off', video: 'off' });

test.describe('STIG reporting and export', () => {
  test.setTimeout(180_000);

  test('collection dashboard, meta dashboard, and CKLB export', async ({ page, request }) => {
    let collectionId = null;
    let workspaceName = '';

    try {
      const seed = await seedReportingWorkspace(request);
      collectionId = seed.collectionId;
      workspaceName = seed.workspaceName;

      const collectionDashboard = new CollectionDashboardPage(page);
      await collectionDashboard.open();
      await collectionDashboard.selectWorkspace(workspaceName);
      await collectionDashboard.expectWorkspaceSelected(workspaceName);
      await collectionDashboard.expectWorkspaceDataVisible();

      const metaDashboard = new MetaDashboardPage(page);
      await metaDashboard.open();
      await metaDashboard.expectWorkspaceListed(workspaceName);

      const exportPage = new ExportPage(page);
      await exportPage.open();
      await exportPage.selectWorkspace(workspaceName);
      await exportPage.selectFormat('cklb');
      const download = await exportPage.downloadAllInView();
      expect(download.suggestedFilename().length).toBeGreaterThan(0);
    } finally {
      if (collectionId) {
        const removed = await deleteWorkspaceCascade(request, collectionId);
        if (!removed) {
          test.info().annotations.push({
            type: 'leftover-workspace',
            description: workspaceName || collectionId,
          });
        }
      }
    }
  });
});
