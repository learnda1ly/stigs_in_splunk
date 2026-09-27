const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');
const {
  workspaceCombobox,
  selectWorkspaceOption,
  expectWorkspaceOptionSelected,
} = require('../helpers/workspaceSelect');

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
    return workspaceCombobox(this.page);
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
    await selectWorkspaceOption(this.page, select, name, CONTROL_TIMEOUT_MS);
    await metricsReady;
    await expect(this.page.getByRole('heading', { name: 'Completion' })).toBeVisible({
      timeout: CONTROL_TIMEOUT_MS,
    });
  }

  /**
   * @param {string} name
   */
  async expectWorkspaceSelected(name) {
    await expectWorkspaceOptionSelected(this.workspaceSelect(), name, CONTROL_TIMEOUT_MS);
  }

  /** Status breakdown uses pills only (no duplicate label text in the same cell). */
  async expectByStatusUsesStatusPills() {
    const section = this.page.getByRole('heading', { name: 'By status', exact: true });
    await expect(section).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    const table = section.locator('xpath=following::table[1]');
    await expect(table).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    const statusCell = table.locator('tbody tr').first().locator('td').first();
    await expect(statusCell).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    const cellText = (await statusCell.innerText()).trim();
    const occurrences = (cellText.match(/Open/gi) || []).length;
    expect(occurrences).toBeLessThanOrEqual(1);
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

module.exports = { CollectionDashboardPage };
