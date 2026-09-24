const path = require('path');
const { test, expect } = require('@playwright/test');
const { WorkspacesPage } = require('../pages/WorkspacesPage');
const { GrantsPage } = require('../pages/GrantsPage');
const { LabelsPage } = require('../pages/LabelsPage');
const { HostsPage } = require('../pages/HostsPage');
const { ImportPage } = require('../pages/ImportPage');
const { EditorAssignPage } = require('../pages/EditorAssignPage');
const { ReviewPage } = require('../pages/ReviewPage');
const { CollectionDashboardPage } = require('../pages/CollectionDashboardPage');
const { MetaDashboardPage } = require('../pages/MetaDashboardPage');
const { ExportPage } = require('../pages/ExportPage');
const {
  ASSESSOR_USER,
  REVIEWER_USER,
  splunkLogin,
  splunkLoginAdmin,
  ensureSplunkUsers,
  findCollectionIdByName,
  findHostId,
  deleteWorkspaceCascade,
  expectDownloadContainsHost,
} = require('./helpers');

const MINIMAL_BENCHMARK = path.resolve(
  __dirname,
  '../../tests/fixtures/minimal_benchmark.xml',
);

const HOSTNAME = 'dmz-01';
const LABEL_NAME = 'dmz';
const RULE_VERSION = 'EX-00-000001';
const BASELINE_LABEL = 'Example_STIG';
const BENCHMARK_TITLE = 'Example STIG for PoC';

/** @type {{ workspaceName: string, collectionId: string, hostId: string, baselineId: string, rejectFeedback: string }} */
const journey = {
  workspaceName: `org-sim-${Date.now()}`,
  collectionId: '',
  hostId: '',
  baselineId: '',
  rejectFeedback: '',
};

test.use({ trace: 'off', video: 'off', navigationTimeout: 60_000 });

test.describe('Organization workspace journey', () => {
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(600_000);

  test.beforeAll(async ({ request }) => {
    await ensureSplunkUsers(request);
    journey.rejectFeedback = `Org journey reject ${Date.now()}`;
  });

  test.afterAll(async ({ request }) => {
    if (journey.collectionId) {
      const removed = await deleteWorkspaceCascade(request, journey.collectionId);
      if (!removed) {
        test.info().annotations.push({
          type: 'leftover-workspace',
          description: journey.workspaceName,
        });
      }
    }
  });

  test('1. admin creates workspace', async ({ page, request }) => {
    await splunkLoginAdmin(page);
    const workspaces = new WorkspacesPage(page);
    await workspaces.open();
    await workspaces.createWorkspace({
      name: journey.workspaceName,
      description: 'Playwright organization serial journey',
      isDefault: false,
    });
    journey.collectionId = await findCollectionIdByName(request, journey.workspaceName);
    expect(journey.collectionId).toBeTruthy();
  });

  test('2. admin grants assessor member and reviewer manager', async ({ page }) => {
    await splunkLoginAdmin(page);
    const grants = new GrantsPage(page);
    await grants.open();
    await grants.selectWorkspace(journey.workspaceName);
    await grants.openNewGrantForm();
    await grants.saveGrant(`user:${ASSESSOR_USER}`, 'Member');
    await grants.expectGrantRow(`user:${ASSESSOR_USER}`, 'member');
    await grants.openNewGrantForm();
    await grants.saveGrant(`user:${REVIEWER_USER}`, 'Manager');
    await grants.expectGrantRow(`user:${REVIEWER_USER}`, 'manager');
  });

  test('3. admin creates label dmz and host dmz-01', async ({ page, request }) => {
    await splunkLoginAdmin(page);
    const hosts = new HostsPage(page);
    await hosts.open();
    await hosts.selectWorkspace(journey.workspaceName);
    await hosts.createHost(HOSTNAME);

    const labels = new LabelsPage(page);
    await labels.open();
    await labels.selectWorkspace(journey.workspaceName);
    await labels.createLabel(LABEL_NAME);
    await labels.setHostLabelToggle(HOSTNAME, LABEL_NAME, true);
    await labels.filterHostsByLabel(LABEL_NAME);
    await labels.expectHostInAssignmentTable(HOSTNAME);

    journey.hostId = await findHostId(request, journey.collectionId, HOSTNAME);
  });

  test('4. admin imports minimal benchmark', async ({ page }) => {
    await splunkLoginAdmin(page);
    const importPage = new ImportPage(page);
    await importPage.open();
    await importPage.openBaselinesTab();
    await importPage.selectWorkspace(journey.workspaceName);
    const importResponse = page.waitForResponse(
      (response) =>
        response.url().includes('stig_baselines/import') && response.status() === 200,
    );
    await importPage.uploadBenchmarkFile(MINIMAL_BENCHMARK);
    const importBody = await (await importResponse).json();
    journey.baselineId =
      importBody._key ||
      importBody.baseline_id ||
      (importBody.baselines &&
        importBody.baselines[0] &&
        importBody.baselines[0].record &&
        importBody.baselines[0].record._key);
    expect(journey.baselineId).toBeTruthy();
    await importPage.expectImportSucceeded(BENCHMARK_TITLE);
  });

  test('5. admin assigns baseline to dmz-01', async ({ page }) => {
    expect(journey.baselineId).toBeTruthy();
    await splunkLoginAdmin(page);
    const editor = new EditorAssignPage(page);
    await editor.open();
    await editor.selectWorkspace(journey.workspaceName);
    await editor.selectHost(HOSTNAME);
    await editor.openHostActions();
    await editor.selectAssignBaseline(journey.baselineId, BASELINE_LABEL);
    await editor.assignToHost();
    await editor.expectAssignSuccess();
    await editor.expectAtLeastOneFindingRow();
  });

  test('6. assessor completes one rule, Write, Submit', async ({ page }) => {
    await splunkLogin(page, ASSESSOR_USER);
    const review = new ReviewPage(page);
    const query = `stig_collection_id=${journey.collectionId}&host_id=${journey.hostId}`;
    await review.open(query);
    await review.expectWorkspaceSelected(journey.workspaceName);
    await review.expectHostSelected(HOSTNAME);
    await review.selectFinding(RULE_VERSION);
    await review.fillFinding('Organization journey initial finding details.');
    await review.fillComments('Assessor first submission.');
    await review.clickWrite();
    await review.clickSubmit();
  });

  test('7. reviewer rejects with a comment', async ({ page }) => {
    await splunkLogin(page, REVIEWER_USER);
    const review = new ReviewPage(page);
    const query = `stig_collection_id=${journey.collectionId}&host_id=${journey.hostId}`;
    await review.open(query);
    await review.selectFinding(RULE_VERSION);
    await review.fillRejectFeedback(journey.rejectFeedback);
    await review.clickReject();
  });

  test('8. assessor addresses comment, Write, Submit', async ({ page }) => {
    await splunkLogin(page, ASSESSOR_USER);
    const review = new ReviewPage(page);
    const query = `stig_collection_id=${journey.collectionId}&host_id=${journey.hostId}`;
    await review.open(query);
    await review.selectFinding(RULE_VERSION);
    await review.expectRejectFeedbackVisible(journey.rejectFeedback);
    await review.fillFinding('Organization journey revised finding after reject feedback.');
    await review.fillComments('Assessor resubmission after reject.');
    await review.clickWrite();
    await review.clickSubmit();
  });

  test('9. reviewer accepts', async ({ page }) => {
    await splunkLogin(page, REVIEWER_USER);
    const review = new ReviewPage(page);
    const query = `stig_collection_id=${journey.collectionId}&host_id=${journey.hostId}`;
    await review.open(query);
    await review.selectFinding(RULE_VERSION);
    await review.clickAccept();
  });

  test('10. admin dashboards and export contain the host', async ({ page }) => {
    await splunkLoginAdmin(page);

    const collectionDashboard = new CollectionDashboardPage(page);
    await collectionDashboard.open();
    await collectionDashboard.selectWorkspace(journey.workspaceName);
    await collectionDashboard.expectWorkspaceSelected(journey.workspaceName);
    await collectionDashboard.expectWorkspaceDataVisible();

    const metaDashboard = new MetaDashboardPage(page);
    await metaDashboard.open();
    await metaDashboard.expectWorkspaceListed(journey.workspaceName);

    const exportPage = new ExportPage(page);
    await exportPage.open();
    await exportPage.selectWorkspace(journey.workspaceName);
    await exportPage.selectFormat('cklb');
    const download = await exportPage.downloadAllInView();
    await expectDownloadContainsHost(download, HOSTNAME);
  });
});
