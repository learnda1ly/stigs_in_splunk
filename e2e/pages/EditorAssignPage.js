const { expect } = require('@playwright/test');
const { appPath } = require('../fixtures/splunk');
const { selectWorkspaceOption, escapeRegExp } = require('../helpers/workspaceSelect');

const NAV_TIMEOUT_MS = 60_000;
const CONTROL_TIMEOUT_MS = 30_000;

/** @typedef {import('@playwright/test').Page} Page */

class EditorAssignPage {
  /**
   * @param {Page} page
   */
  constructor(page) {
    this.page = page;
  }

  workspaceSelect() {
    return this.page.getByRole('combobox', { name: 'Workspace' });
  }

  hostSelect() {
    return this.page.getByRole('combobox', { name: 'Host' });
  }

  assignBaselineSelect() {
    return this.page.getByRole('combobox', { name: 'Assign STIG' });
  }

  hostActionsButton() {
    return this.page.locator('button').filter({ hasText: 'Host actions' });
  }

  assignToHostButton() {
    return this.page.locator('button').filter({ hasText: 'Assign to host', exact: true });
  }

  findingList() {
    return this.page.locator('button[data-key]');
  }

  async open() {
    this.page.setDefaultTimeout(CONTROL_TIMEOUT_MS);
    await this.page.goto(appPath('stig_editor_ui'), { timeout: NAV_TIMEOUT_MS });
    await expect(this.page.locator('#stig-ui-root')).toBeVisible({
      timeout: NAV_TIMEOUT_MS,
    });
    await expect(this.workspaceSelect()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  /**
   * @param {string} name Workspace collection name (without "(default)" suffix).
   */
  async selectWorkspace(name) {
    await selectWorkspaceOption(this.page, this.workspaceSelect(), name, CONTROL_TIMEOUT_MS);
  }

  async waitForHostOption(hostKey, hostname) {
    const select = this.hostSelect();
    const deadline = Date.now() + CONTROL_TIMEOUT_MS;
    while (Date.now() < deadline) {
      await select.click();
      const option = this.page.locator(`[data-test="option"][data-test-value="${hostKey}"]`);
      if (await option.isVisible().catch(() => false)) {
        await this.page.keyboard.press('Escape');
        return;
      }
      await this.page.keyboard.press('Escape');
      await this.page.waitForTimeout(500);
    }
    throw new Error(`Host ${hostname} not loaded for workspace`);
  }

  /**
   * @param {string} hostname Host label in the Host combobox.
   * @param {string} [hostKey] Host KV `_key` when option labels are unstable in the menu.
   */
  async selectHost(hostname, hostKey) {
    const select = this.hostSelect();
    await expect(select).toBeEnabled({ timeout: CONTROL_TIMEOUT_MS });
    const deadline = Date.now() + CONTROL_TIMEOUT_MS;
    while (Date.now() < deadline) {
      await select.click();
      const option = hostKey
        ? this.page.locator(`[data-test="option"][data-test-value="${hostKey}"]`)
        : this.page.getByRole('option', {
            name: new RegExp(`^${escapeRegExp(hostname)}`),
          });
      if (await option.first().isVisible().catch(() => false)) {
        await option.first().click({ force: true });
        await expect(select).toContainText(hostname, { timeout: CONTROL_TIMEOUT_MS });
        return;
      }
      await this.page.keyboard.press('Escape');
      await this.page.waitForTimeout(500);
    }
    throw new Error(`Host option not found in editor: ${hostname}`);
  }

  async openHostActions() {
    await expect(this.assignBaselineSelect()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await expect(this.assignToHostButton()).toBeVisible();
  }

  /**
   * @param {string} baselineId Workspace baseline KV `_key` from REST import.
   * @param {string} [baselineLabel] Visible label substring for sanity checks.
   */
  async selectAssignBaseline(baselineId, baselineLabel = 'Example_STIG') {
    const select = this.assignBaselineSelect();
    await select.click();
    const option = this.page.locator(
      `[data-test="option"][data-test-value="${baselineId}"]`,
    );
    await expect(option).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await option.click();
    await expect(select).toContainText(baselineLabel, { timeout: CONTROL_TIMEOUT_MS });
  }

  async assignToHost() {
    await this.assignToHostButton().click();
  }

  async expectAssignSuccess() {
    const banner = this.page
      .getByText(/Assigned STIG and created checklist|STIG already assigned/)
      .first();
    await expect(banner).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
  }

  async expectAtLeastOneFindingRow() {
    const row = this.findingList().filter({ hasText: /EX-00-000001|Example rule/ });
    await expect(row.first()).toBeVisible({ timeout: CONTROL_TIMEOUT_MS });
    await expect(this.findingList()).not.toHaveCount(0);
  }
}

module.exports = { EditorAssignPage };
