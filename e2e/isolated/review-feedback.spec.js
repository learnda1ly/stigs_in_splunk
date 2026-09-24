const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { ReviewPage } = require('../pages/ReviewPage');
const { CollectionReviewPage } = require('../pages/CollectionReviewPage');
const { getSplunkBaseUrl } = require('../fixtures/auth');

const REST_MGMT =
  process.env.SPLUNK_MGMT_URL ||
  (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');
const REST_BASE = `${REST_MGMT.replace(/\/$/, '')}/servicesNS/nobody/stigs_in_splunk`;
const AUTH_USERS_URL = 'https://127.0.0.1:8089/services/authentication/users';
const TEST_PASSWORD = 'PlaywrightTest!2026';
const ASSESSOR_USER = 'stig_pw_assessor';
const REVIEWER_USER = 'stig_pw_reviewer';
const HOSTNAME = 'web-01';
const RULE_VERSION = 'EX-00-000001';
const BASELINE_LABEL = 'Example_STIG';
const BENCHMARK_XML = path.join(
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
    throw new Error('SPLUNK_ADMIN_USER and SPLUNK_ADMIN_PASSWORD are required.');
  }
  return {
    Authorization: `Basic ${Buffer.from(`${user}:${password}`).toString('base64')}`,
  };
}

async function ensureSplunkUsers(request) {
  const headers = restAuthHeader();
  for (const name of [ASSESSOR_USER, REVIEWER_USER]) {
    const response = await request.post(AUTH_USERS_URL, {
      headers: { ...headers, 'Content-Type': 'application/x-www-form-urlencoded' },
      form: {
        name,
        password: TEST_PASSWORD,
        roles: 'stig_user',
      },
      ignoreHTTPSErrors: true,
    });
    if (!response.ok() && response.status() !== 409 && response.status() !== 400) {
      throw new Error(`Failed to ensure user ${name}: HTTP ${response.status()}`);
    }
  }
}

async function createReviewWorkspace(request) {
  const headers = restAuthHeader();
  const name = `pw-review-${Date.now()}`;
  const collectionResponse = await request.post(
    `${REST_BASE}/stig_collections?output_mode=json`,
    {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: {
        name,
        access_principals: JSON.stringify([
          'user:admin',
          `user:${ASSESSOR_USER}`,
          `user:${REVIEWER_USER}`,
        ]),
        is_default: false,
      },
      ignoreHTTPSErrors: true,
    },
  );
  const collectionRaw = await collectionResponse.text();
  let collectionBody;
  try {
    collectionBody = JSON.parse(collectionRaw);
  } catch {
    throw new Error(
      `create collection HTTP ${collectionResponse.status()} from ${REST_BASE}/stig_collections: ${collectionRaw.slice(0, 240)}`,
    );
  }
  expect(
    collectionResponse.ok(),
    `create collection HTTP ${collectionResponse.status()}: ${collectionRaw}`,
  ).toBeTruthy();
  const collectionId = collectionBody._key;
  expect(collectionId).toBeTruthy();

  for (const [principal, grant_role] of [
    [`user:${ASSESSOR_USER}`, 'member'],
    [`user:${REVIEWER_USER}`, 'manager'],
  ]) {
    const grantResponse = await request.post(
      `${REST_BASE}/stig_collections/${collectionId}/grants?output_mode=json`,
      {
        headers: { ...headers, 'Content-Type': 'application/json' },
        data: { principal, grant_role },
        ignoreHTTPSErrors: true,
      },
    );
    expect(grantResponse.ok()).toBeTruthy();
  }

  const hostResponse = await request.post(`${REST_BASE}/stig_hosts?output_mode=json`, {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: { hostname: HOSTNAME, stig_collection_id: collectionId },
    ignoreHTTPSErrors: true,
  });
  expect(hostResponse.ok()).toBeTruthy();
  const hostBody = await hostResponse.json();
  const hostId = hostBody._key;

  const xml = fs.readFileSync(BENCHMARK_XML);
  const importResponse = await request.post(
    `${REST_BASE}/stig_baselines/import?format=xccdf&stig_collection_id=${collectionId}&output_mode=json`,
    {
      headers: { ...headers, 'Content-Type': 'application/xml' },
      data: xml,
      ignoreHTTPSErrors: true,
    },
  );
  expect(importResponse.ok()).toBeTruthy();
  const importBody = await importResponse.json();
  const baselineId =
    importBody._key ||
    (importBody.baselines &&
      importBody.baselines[0] &&
      importBody.baselines[0].record &&
      importBody.baselines[0].record._key);
  expect(baselineId).toBeTruthy();

  const assignResponse = await request.post(
    `${REST_BASE}/stig_hosts/${hostId}/stigs?output_mode=json`,
    {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: { baseline_id: baselineId },
      ignoreHTTPSErrors: true,
    },
  );
  expect(assignResponse.ok()).toBeTruthy();

  return { collectionId, collectionName: name, hostId, baselineId };
}

async function deleteCollection(request, collectionId) {
  if (!collectionId) {
    return;
  }
  const headers = restAuthHeader();
  await request.delete(
    `${REST_BASE}/stig_collections/${collectionId}?cascade=true&output_mode=json`,
    { headers, ignoreHTTPSErrors: true },
  );
}

async function splunkLogin(page, username) {
  await page.goto('/en-US/account/login', { timeout: 60_000 });
  await page.locator('input[name=username]').fill(username);
  await page.locator('input[name=password]').fill(TEST_PASSWORD);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.waitForURL((url) => !url.pathname.includes('/account/login'), {
    timeout: 60_000,
  });
}

async function loginAs(browser, username) {
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    baseURL: getSplunkBaseUrl(),
  });
  const page = await context.newPage();
  await splunkLogin(page, username);
  return { context, page };
}

async function openEditorWithDeepLink(reviewPage, { collectionName, hostId, collectionId }) {
  const editorQuery = `stig_collection_id=${collectionId}&host_id=${hostId}`;
  await reviewPage.open(editorQuery);
  await reviewPage.expectWorkspaceSelected(collectionName);
  await reviewPage.expectHostSelected(HOSTNAME);
}

test.describe('review feedback loop', () => {
  test.setTimeout(240_000);

  test('assessor submit, reviewer reject with feedback, resubmit, accept', async ({
    browser,
    request,
  }) => {
    const rejectFeedback = `PW reject feedback ${Date.now()}`;
    let collectionId;

    try {
      await ensureSplunkUsers(request);

      const workspace = await createReviewWorkspace(request);
      collectionId = workspace.collectionId;
      const { collectionName, hostId } = workspace;

      const assessorCtx = await loginAs(browser, ASSESSOR_USER);
      const assessor = new ReviewPage(assessorCtx.page);

      await openEditorWithDeepLink(assessor, {
        collectionName,
        hostId,
        collectionId,
      });
      await assessor.selectFinding(RULE_VERSION);
      await assessor.fillFinding('Initial finding details for Playwright review flow.');
      await assessor.fillComments('Assessor comments v1.');
      await assessor.clickWrite();
      await assessor.clickSubmit();

      const reviewerCtx = await loginAs(browser, REVIEWER_USER);
      const reviewer = new ReviewPage(reviewerCtx.page);

      await openEditorWithDeepLink(reviewer, {
        collectionName,
        hostId,
        collectionId,
      });
      await reviewer.selectFinding(RULE_VERSION);
      await reviewer.fillRejectFeedback(rejectFeedback);
      await reviewer.clickReject();

      await openEditorWithDeepLink(assessor, {
        collectionName,
        hostId,
        collectionId,
      });
      await assessor.selectFinding(RULE_VERSION);
      await assessor.expectRejectFeedbackVisible(rejectFeedback);
      await assessor.fillFinding(
        'Revised finding details after reviewer feedback for Playwright.',
      );
      await assessor.fillComments('Assessor comments v2 after reject.');
      await assessor.clickWrite();
      await assessor.clickSubmit();

      await openEditorWithDeepLink(reviewer, {
        collectionName,
        hostId,
        collectionId,
      });
      await reviewer.selectFinding(RULE_VERSION);
      await reviewer.clickAccept();

      await assessorCtx.context.close();

      const collectionReview = new CollectionReviewPage(reviewer.page);

      await collectionReview.open();
      await collectionReview.selectWorkspace(collectionName);
      await collectionReview.selectBaseline(BASELINE_LABEL);
      await collectionReview.selectRule(RULE_VERSION);
      await collectionReview.expectWorkflowAcceptedForHost(HOSTNAME);

      await reviewerCtx.context.close();
    } finally {
      await deleteCollection(request, collectionId);
    }
  });
});
