const { test, expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');
const { appNavScope, expandNavCollection, ensureAppNavExpanded } = require('../helpers/appNav');

const NAV_TIMEOUT_MS = 60_000;
const UI_TIMEOUT_MS = 60_000;

const DOC_SECTION_TITLES = [
  '1. Overview',
  '2. Before you begin',
  '3. Install',
  '4. Access control',
  '5. HTTP Event Collector (HEC)',
  '6. Quick start (about 15 minutes)',
  '7. Import reference',
  '8. Multi-user governance',
  '9. Troubleshooting',
  '10. Further reading (repository)',
];

test.describe('Documentation navigation', () => {
  test.setTimeout(180_000);

  test('Help nav and Workspaces settings remain reachable', async ({ page }) => {
    const reachableViews = [
      { path: 'stig_documentation_ui', probe: () => page.locator('#stig-ui-root') },
      {
        path: 'configuration',
        probe: () => page.getByRole('tab', { name: 'Workspaces' }),
      },
      { path: 'stig_export_ui', probe: () => page.locator('#stig-ui-root') },
      { path: 'stig_library_ui', probe: () => page.locator('#stig-ui-root') },
    ];

    for (const { path, probe } of reachableViews) {
      await page.goto(appPath(path), { timeout: NAV_TIMEOUT_MS });
      await expect(probe()).toBeVisible({ timeout: UI_TIMEOUT_MS });
    }

    await page.goto(appPath('stig_editor_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: UI_TIMEOUT_MS });
    await ensureAppNavExpanded(page);
    const navScope = appNavScope(page);
    const root = (await navScope.count()) > 0 ? navScope : page;
    await expect(root.getByText('Classic', { exact: false })).toHaveCount(0);
  });

  test('editor theme control omits deployment-wide SplunkUI help text', async ({ page }) => {
    await page.goto(appPath('stig_editor_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: UI_TIMEOUT_MS });
    await expect(
      page.getByText('Applies to all SplunkUI pages for this deployment.'),
    ).toHaveCount(0);
    await expect(page.getByRole('combobox', { name: 'Editor color theme' })).toBeVisible({
      timeout: UI_TIMEOUT_MS,
    });
  });

  test('documentation view renders all required sections', async ({ page }) => {
    await page.goto(appPath('stig_documentation_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(page.locator('#stig-ui-root')).toBeVisible({ timeout: UI_TIMEOUT_MS });

    for (const title of DOC_SECTION_TITLES) {
      await expect(page.getByRole('heading', { name: title })).toBeVisible({
        timeout: UI_TIMEOUT_MS,
      });
    }

    await expect(page.getByRole('heading', { name: '6. Quick start (about 15 minutes)' })).toBeVisible();
    const quickStart = page.locator('#quick-start');
    await expect(quickStart.getByText('Import baselines')).toBeVisible();
    await expect(quickStart.getByRole('link', { name: /Reports|Collection dashboard/i })).toBeVisible();
  });

  test('static onboarding.html is served under the app', async ({ page, request }) => {
    const base = process.env.SPLUNK_BASE_URL || 'https://127.0.0.1:8000';
    const locale = 'en-US';
    const staticUrl = `${base}/${locale}/static/app/stigs_in_splunk/docs/onboarding.html`;
    const response = await request.get(staticUrl, { ignoreHTTPSErrors: true });
    test.skip(response.status() === 404, 'Splunk static mount not available in this environment');
    expect(response.ok()).toBeTruthy();
    const body = await response.text();
    expect(body).toContain('6. Quick start');
    expect(body).toContain('stig_findings');
  });
});
