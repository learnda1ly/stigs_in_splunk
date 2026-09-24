const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

class CollectionDashboardPage {
  /**
   * @param {import('@playwright/test').Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceSelect() {
    return this.page.getByRole('combobox').first();
  }

  async open() {
    await this.page.goto(appPath('stig_collection_dashboard_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.getByRole('heading', { name: 'Collection dashboard' })).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.workspaceSelect()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} name Workspace collection name (without the "(default)" suffix).
   */
  async selectWorkspace(name) {
    const metricsReady = this.page.waitForResponse(
      (response) =>
        response.url().includes('/stig_collections/') &&
        response.url().includes('/metrics') &&
        response.status() === 200,
      { timeout: CONTROL_TIMEOUT_MS },
    );
    const select = this.workspaceSelect();
    await select.click();
    const option = this.page.getByRole('option', { name: new RegExp(escapeRegExp(name)) });
    await expect(option.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.first().click();
    await expect(select).toContainText(name, { timeout: CONTROL_TIMEOUT_MS });
    await metricsReady;
    await expect(this.page.getByRole('heading', { name: 'Completion' })).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  /**
   * @param {string} name
   */
  async expectWorkspaceSelected(name) {
    await expect(this.workspaceSelect()).toContainText(name, {
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  async expectWorkspaceDataVisible() {
    await expect(this.page.getByText('Hosts', { exact: true }).first()).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
    const hostsCard = this.page
      .getByText('Hosts', { exact: true })
      .first()
      .locator('xpath=preceding-sibling::*[1]');
    await expect(hostsCard).toHaveText(/[1-9]/, { timeout: CONTROL_TIMEOUT_MS });
    await expect(this.page.getByText('Reviews', { exact: true }).first()).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

module.exports = { CollectionDashboardPage };
