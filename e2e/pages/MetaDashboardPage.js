const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const ROW_TIMEOUT_MS = 30_000;

class MetaDashboardPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  async open() {
    const metricsReady = this.page.waitForResponse(
      (response) =>
        response.url().includes('stig_collections/meta/metrics') && response.status() === 200,
      { timeout: NAV_TIMEOUT_MS },
    );
    await this.page.goto(appPath('stig_meta_collection_dashboard_ui'), {
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.page.getByRole('heading', { name: 'All workspaces' })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await metricsReady;
    await this.waitForWorkspaceTable();
  }

  async waitForWorkspaceTable() {
    await expect(this.page.getByRole('heading', { name: 'By workspace' })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
  }

  /**
   * @param {string} workspaceName
   */
  async expectWorkspaceListed(workspaceName) {
    await this.waitForWorkspaceTable();
    const row = this.page.getByRole('row', { name: new RegExp(escapeRegExp(workspaceName)) });
    await expect(row.first()).toBeVisible({ timeout: ROW_TIMEOUT_MS });
    await expect(row.first()).toContainText(workspaceName);
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { MetaDashboardPage };
