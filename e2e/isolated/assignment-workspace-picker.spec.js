const { test, expect } = require('@playwright/test');
const { restAuthHeader, loadAdminCredentials } = require('../fixtures/credentials');
const { appPath } = require('../fixtures/splunk');
const {
  workspaceCombobox,
  expectAllWorkspacesOptionListed,
  expectAllWorkspacesOptionAbsent,
} = require('../helpers/workspaceSelect');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

const REST_BASE =
  process.env.SPLUNK_MGMT_URL ||
  (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');


async function deleteWorkspaceCascade(request, collectionId) {
  const response = await request.delete(
    `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections/${collectionId}?cascade=true&output_mode=json`,
    { headers: restAuthHeader(), ignoreHTTPSErrors: true },
  );
  return response.ok();
}

test.use({ trace: 'off', video: 'off' });

test.describe('Assignment workspace pickers', () => {
  test.setTimeout(120_000);

  test('toolbar workspace includes All; rule target workspace does not', async ({
    page,
    request,
  }) => {
    const name = `pw-assign-all-${Date.now()}`;
    let collectionId = null;

    try {
      const createRes = await request.post(
        `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections?output_mode=json`,
        {
          headers: { ...restAuthHeader(), 'Content-Type': 'application/json' },
          data: { name, description: 'Playwright assignment All picker' },
          ignoreHTTPSErrors: true,
        },
      );
      expect(createRes.ok()).toBeTruthy();
      collectionId = (await createRes.json())._key;

      await page.goto(appPath('stig_assignment_ui'), { timeout: NAV_TIMEOUT_MS });
      await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: NAV_TIMEOUT_MS });

      const toolbarWorkspace = workspaceCombobox(page);
      await expectAllWorkspacesOptionListed(page, toolbarWorkspace);

      await page.getByRole('button', { name: 'Add rule', exact: true }).click();
      const rulePanel = page.getByRole('heading', { name: 'New rule', exact: true }).locator('..');
      const targetWorkspace = rulePanel.getByRole('combobox', { name: 'Workspace' });
      await expect(targetWorkspace).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
      await expectAllWorkspacesOptionAbsent(page, targetWorkspace);
    } finally {
      if (collectionId) {
        await deleteWorkspaceCascade(request, collectionId);
      }
    }
  });
});
