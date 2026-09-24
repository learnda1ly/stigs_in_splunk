const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { ReviewRequirementsPage } = require('../pages/ReviewRequirementsPage');
const { EditorRequirementsProbe } = require('../pages/EditorRequirementsProbe');

const REST_BASE =
  process.env.SPLUNK_MGMT_URL ||
  (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');

const FIXTURE_XCCDF = path.join(
  __dirname,
  '../../tests/fixtures/minimal_benchmark.xml',
);

function restAuthHeader() {
  const user = process.env.SPLUNK_ADMIN_USER;
  const password = process.env.SPLUNK_ADMIN_PASSWORD;
  if (!user || !password) {
    throw new Error('SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD are required for REST setup');
  }
  return {
    Authorization: `Basic ${Buffer.from(`${user}:${password}`).toString('base64')}`,
  };
}

async function restJson(request, method, urlPath, { data, body } = {}) {
  const headers = restAuthHeader();
  const url = `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/${urlPath}${
    urlPath.includes('?') ? '&' : '?'
  }output_mode=json`;
  const opts = { headers, ignoreHTTPSErrors: true };
  let response;
  if (method === 'GET') {
    response = await request.get(url, opts);
  } else if (method === 'POST') {
    response = await request.post(url, { ...opts, data: data ?? body });
  } else if (method === 'DELETE') {
    response = await request.delete(url, opts);
  } else {
    throw new Error(`Unsupported method ${method}`);
  }
  if (!response.ok()) {
    const text = await response.text();
    throw new Error(`${method} ${urlPath} failed ${response.status()}: ${text.slice(0, 500)}`);
  }
  const contentType = response.headers()['content-type'] || '';
  if (contentType.includes('json')) {
    return response.json();
  }
  return null;
}

async function createTestWorkspace(request, name) {
  return restJson(request, 'POST', 'stig_collections', {
    body: {
      name,
      description: 'Playwright review requirements isolated test',
      is_default: false,
    },
  });
}

async function importMinimalBaseline(request) {
  const xml = fs.readFileSync(FIXTURE_XCCDF);
  const headers = {
    ...restAuthHeader(),
    'Content-Type': 'application/xml',
  };
  const url = `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_baselines/import?output_mode=json&format=xccdf&source_uri=minimal_benchmark.xml`;
  const response = await request.post(url, {
    headers,
    data: xml,
    ignoreHTTPSErrors: true,
  });
  if (!response.ok()) {
    const text = await response.text();
    throw new Error(`baseline import failed ${response.status()}: ${text.slice(0, 500)}`);
  }
  return response.json();
}

async function createHost(request, collectionId, hostname) {
  return restJson(request, 'POST', 'stig_hosts', {
    body: {
      stig_collection_id: collectionId,
      hostname,
      ip_address: '10.99.0.2',
    },
  });
}

async function assignBaselineChecklist(request, collectionId, hostId, baselineId) {
  return restJson(request, 'POST', 'stig_checklists', {
    body: {
      stig_collection_id: collectionId,
      host_id: hostId,
      baseline_id: baselineId,
      title: 'Playwright review requirements checklist',
    },
  });
}

async function deleteWorkspaceCascade(request, collectionId) {
  const headers = restAuthHeader();
  const url = `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections/${collectionId}?output_mode=json&cascade=true`;
  const response = await request.delete(url, { headers, ignoreHTTPSErrors: true });
  return response.ok();
}

async function patchReviewRequirementsRoute(page) {
  await page.route('**/review_requirements**', async (route) => {
    const req = route.request();
    if (req.method() === 'PATCH') {
      await route.continue({
        method: 'POST',
        postData: req.postData(),
        headers: req.headers(),
      });
      return;
    }
    await route.continue();
  });
}

test.use({ trace: 'off', video: 'off' });

test.describe('Workspace review requirements', () => {
  test.setTimeout(180_000);

  test.beforeAll(() => {
    const resultsDir = path.join(__dirname, '../test-results');
    try {
      fs.rmSync(resultsDir, { recursive: true, force: true });
    } catch {
      // ignore missing results dir
    }
  });

  test('policy in review requirements UI gates editor submit until finding details meet minimum length', async ({
    page,
    request,
  }) => {
    const workspaceName = `pw-req-${Date.now()}`;
    let collectionId = null;

    await patchReviewRequirementsRoute(page);

    try {
      const collection = await createTestWorkspace(request, workspaceName);
      collectionId = collection._key;
      expect(collectionId).toBeTruthy();

      const baseline = await importMinimalBaseline(request);
      expect(baseline._key).toBeTruthy();

      const host = await createHost(request, collectionId, 'web-01');
      expect(host._key).toBeTruthy();

      const checklist = await assignBaselineChecklist(
        request,
        collectionId,
        host._key,
        baseline._key,
      );
      expect(checklist._key).toBeTruthy();

      const requirements = new ReviewRequirementsPage(page);
      await requirements.open();
      await requirements.selectWorkspace(workspaceName);
      await requirements.setRequireFindingDetails(true);
      await requirements.setMinFindingDetailsLength(20);
      await requirements.save();
      await requirements.expectRequireFindingDetailsOn(true, 20);

      const editor = new EditorRequirementsProbe(page);
      await editor.open();
      await editor.selectWorkspace(workspaceName);
      await editor.selectHost('web-01');
      await editor.selectFirstFinding();

      await editor.fillFindingDetails('too short');
      await editor.expectReviewIncomplete();

      const longDetails = 'Playwright finding details meeting minimum length requirement.';
      await editor.fillFindingDetails(longDetails);
      await editor.clickWrite();
      await editor.expectReviewComplete();
    } finally {
      if (collectionId) {
        const removed = await deleteWorkspaceCascade(request, collectionId);
        if (!removed) {
          test.info().annotations.push({
            type: 'leftover-workspace',
            description: `${workspaceName} (${collectionId})`,
          });
        }
      }
    }
  });
});
