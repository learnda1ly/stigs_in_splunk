const { test, expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');
const {
  ensureAppNavExpanded,
  expandNavCollection,
  expectNavLabelVisible,
} = require('../helpers/appNav');

const NAV_TIMEOUT_MS = 60_000;
const UI_TIMEOUT_MS = 60_000;

test.describe('UX3 app navigation', () => {
  test.setTimeout(180_000);

  test('skip link is present on Assess', async ({ page }) => {
    await page.goto(appPath('stig_editor_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(page.locator('#stig-skip-link')).toHaveAttribute('href', '#stig-main-content');
  });

  test('Assess default view shows primary nav labels', async ({ page }) => {
    await page.goto(appPath('stig_editor_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: UI_TIMEOUT_MS });
    await expect(page.getByRole('heading', { name: 'Assess', level: 2 })).toBeVisible({
      timeout: UI_TIMEOUT_MS,
    });

    await ensureAppNavExpanded(page);
    for (const label of ['Overview', 'Assess', 'Review', 'Reports', 'Help']) {
      await expectNavLabelVisible(page, label);
    }

    await expandNavCollection(page, 'Content');
    for (const label of ['Import results', 'Export checklists', 'STIG library']) {
      await expectNavLabelVisible(page, label);
    }

    await expandNavCollection(page, 'Workspace');
    for (const label of ['Hosts', 'Labels', 'Access']) {
      await expectNavLabelVisible(page, label);
    }
  });

  test('Hosts honors stig_collection_id query param', async ({ page, request }) => {
    const { restAuthHeader, loadAdminCredentials } = require('../fixtures/credentials');
    const REST_BASE =
      process.env.SPLUNK_MGMT_URL ||
      (process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000').replace(':8000', ':8089');

    if (!loadAdminCredentials().password) {
      test.skip();
    }

    const headers = restAuthHeader();
    const listRes = await request.get(
      `${REST_BASE}/servicesNS/nobody/stigs_in_splunk/stig_collections?output_mode=json`,
      { headers, ignoreHTTPSErrors: true },
    );
    test.skip(!listRes.ok(), 'REST unavailable');
    const collections = await listRes.json();
    const defaultWs =
      collections.find((row) => row.is_default) || collections.find((row) => row.name === 'Default');
    test.skip(!defaultWs?._key, 'No default workspace');

    const url = `${appPath('stig_hosts_ui')}?stig_collection_id=${encodeURIComponent(defaultWs._key)}`;
    await page.goto(url, { timeout: NAV_TIMEOUT_MS });
    await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: UI_TIMEOUT_MS });
    const select = page.getByRole('combobox', { name: 'Workspace' });
    await expect(select).toContainText(defaultWs.name, { timeout: UI_TIMEOUT_MS });
  });

  test('legacy stage nav labels are absent', async ({ page }) => {
    await page.goto(appPath('stig_editor_ui'), { timeout: NAV_TIMEOUT_MS });
    await ensureAppNavExpanded(page);
    for (const legacy of ['Get started', 'Work', 'STIG Editor', 'Collection review']) {
      await expect(page.getByRole('link', { name: legacy })).toHaveCount(0);
    }
  });
});
